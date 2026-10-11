"""Coverage for F2: org-scoped auth resolution and org-switching.

The core risk this file guards against: a user who holds roles in TWO different
organizations must never have one org's permissions leak into a session that is
active in the other org. Before this change, `get_user_permissions`/`get_user_roles`
had no org filter at all — harmless only because every user belonged to exactly one
org. F1 (memberships) made multi-org membership possible; this suite proves the
permission resolution was tightened to match before that possibility is exploitable.
"""

import uuid

import pytest

import app.register_models  # noqa: F401
from app.core.exceptions.errors import ForbiddenError, UnauthorizedError
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService
from app.modules.organizations.models import Membership, MembershipStatus, Organization
from app.modules.users.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    UserStatus,
)

pytestmark = pytest.mark.asyncio

ORG_A = uuid.UUID("55555555-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("55555555-0000-0000-0000-00000000000b")
ORG_C = uuid.UUID("55555555-0000-0000-0000-00000000000c")  # user is NOT a member here
USER_ID = uuid.UUID("55555555-0000-0000-0000-000000000001")
# Unique per run: the RBAC seed migration already creates "patient:read" etc., and slugs are unique.
PERM_A = f"patient:read-{uuid.uuid4().hex[:6]}"
PERM_B = f"billing:read-{uuid.uuid4().hex[:6]}"


async def _seed_two_org_user(session):
    """One user with ACTIVE memberships in Org A and Org B, distinct roles in each.

    Org A → permission PERM_A ("patient:read-<suffix>")
    Org B → permission PERM_B ("billing:read-<suffix>")
    A third org, Org C, exists but the user has no membership there.
    """
    for org_id, name in ((ORG_A, "Org A"), (ORG_B, "Org B"), (ORG_C, "Org C")):
        session.add(
            Organization(
                id=org_id,
                name=name,
                slug=f"org-{org_id}",
                schema_name=f"schema_{org_id.hex}",
                country="India",
            )
        )
    session.add(
        User(
            id=USER_ID,
            organization_id=ORG_A,  # "home" org — unaffected by this migration
            email=f"multiorg-{uuid.uuid4().hex[:8]}@solidcare.test",
            hashed_password="x",
            first_name="Multi",
            last_name="Org",
            status=UserStatus.ACTIVE,
        )
    )
    await session.flush()

    # Memberships: A (default) and B. Deliberately none for C.
    session.add(Membership(user_id=USER_ID, organization_id=ORG_A, status=MembershipStatus.ACTIVE, is_default=True))
    session.add(Membership(user_id=USER_ID, organization_id=ORG_B, status=MembershipStatus.ACTIVE, is_default=False))
    await session.flush()

    perm_a = Permission(id=uuid.uuid4(), name="Read Patient", slug=PERM_A, resource="patient", action="read")
    perm_b = Permission(id=uuid.uuid4(), name="Read Billing", slug=PERM_B, resource="billing", action="read")
    session.add_all([perm_a, perm_b])
    await session.flush()

    role_a = Role(id=uuid.uuid4(), organization_id=ORG_A, name="Org A Role", slug="org-a-role")
    role_b = Role(id=uuid.uuid4(), organization_id=ORG_B, name="Org B Role", slug="org-b-role")
    session.add_all([role_a, role_b])
    await session.flush()

    session.add(RolePermission(id=uuid.uuid4(), role_id=role_a.id, permission_id=perm_a.id))
    session.add(RolePermission(id=uuid.uuid4(), role_id=role_b.id, permission_id=perm_b.id))
    session.add(UserRole(id=uuid.uuid4(), user_id=USER_ID, role_id=role_a.id))
    session.add(UserRole(id=uuid.uuid4(), user_id=USER_ID, role_id=role_b.id))
    await session.flush()


def _svc(session):
    return AuthService(AuthRepository(session))


# ---------------------------------------------------------------------------
# The core security property: org-scoped permission resolution
# ---------------------------------------------------------------------------


async def test_permissions_scoped_to_org_a_exclude_org_b(setup_database, db_session):
    await _seed_two_org_user(db_session)
    repo = AuthRepository(db_session)

    perms = await repo.get_user_permissions(USER_ID, ORG_A)

    assert PERM_A in perms
    assert PERM_B not in perms, "Org B's permission leaked into an Org A-scoped query"


async def test_permissions_scoped_to_org_b_exclude_org_a(setup_database, db_session):
    await _seed_two_org_user(db_session)
    repo = AuthRepository(db_session)

    perms = await repo.get_user_permissions(USER_ID, ORG_B)

    assert PERM_B in perms
    assert PERM_A not in perms, "Org A's permission leaked into an Org B-scoped query"


async def test_permissions_unscoped_call_returns_union(setup_database, db_session):
    """Legacy call sites that don't pass org_id keep the pre-F2 (union) behavior.

    This is intentionally still available for backward compatibility, but every
    request-scoped call site (_issue_tokens) now always passes org_id.
    """
    await _seed_two_org_user(db_session)
    repo = AuthRepository(db_session)

    perms = await repo.get_user_permissions(USER_ID)  # no org_id

    assert PERM_A in perms
    assert PERM_B in perms


async def test_roles_scoped_to_org_match_permissions_scoping(setup_database, db_session):
    await _seed_two_org_user(db_session)
    repo = AuthRepository(db_session)

    roles_a = await repo.get_user_roles(USER_ID, ORG_A)
    roles_b = await repo.get_user_roles(USER_ID, ORG_B)

    assert roles_a == ["org-a-role"]
    assert roles_b == ["org-b-role"]


# ---------------------------------------------------------------------------
# switch_org — the only gate between a client and a different org's session
# ---------------------------------------------------------------------------


async def test_switch_org_to_active_membership_issues_scoped_token(setup_database, db_session):
    await _seed_two_org_user(db_session)
    svc = _svc(db_session)

    tokens = await svc.switch_org(USER_ID, ORG_B)

    import jwt as pyjwt
    payload = pyjwt.decode(tokens.access_token, options={"verify_signature": False})
    assert payload["org_id"] == str(ORG_B)
    assert payload["active_org_id"] == str(ORG_B)
    assert PERM_B in payload["permissions"]
    assert PERM_A not in payload["permissions"]


async def test_switch_org_rejects_non_member_org(setup_database, db_session):
    await _seed_two_org_user(db_session)
    svc = _svc(db_session)

    with pytest.raises(ForbiddenError):
        await svc.switch_org(USER_ID, ORG_C)


async def test_switch_org_rejects_unknown_org(setup_database, db_session):
    """A random UUID with no Organization row at all must also be rejected, not 500."""
    await _seed_two_org_user(db_session)
    svc = _svc(db_session)

    with pytest.raises(ForbiddenError):
        await svc.switch_org(USER_ID, uuid.uuid4())


async def test_switch_org_unknown_user_raises_unauthorized(setup_database, db_session):
    await _seed_two_org_user(db_session)
    svc = _svc(db_session)

    with pytest.raises(UnauthorizedError):
        await svc.switch_org(uuid.uuid4(), ORG_A)


async def test_switch_org_membership_carries_both_orgs_in_token(setup_database, db_session):
    """After switching, the token's membership list still reflects ALL memberships,
    not just the newly-active one — this is what lets a workspace switcher render
    every org the user could switch to next, without a fresh login."""
    await _seed_two_org_user(db_session)
    svc = _svc(db_session)

    tokens = await svc.switch_org(USER_ID, ORG_B)

    import jwt as pyjwt
    payload = pyjwt.decode(tokens.access_token, options={"verify_signature": False})
    org_ids_in_token = {m["org_id"] for m in payload["memberships"]}
    assert org_ids_in_token == {str(ORG_A), str(ORG_B)}
