"""Coverage for NotificationService — previously zero tests on this module."""

import uuid

import pytest

import app.register_models  # noqa: F401
from app.core.exceptions.errors import NotFoundError
from app.modules.notifications.models import NotificationType
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.service import NotificationService
from app.modules.organizations.models import Organization
from app.modules.users.models import User, UserStatus
from app.shared.schemas.pagination import PaginationParams

pytestmark = pytest.mark.asyncio

ORG_ID = uuid.UUID("22222222-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("22222222-0000-0000-0000-000000000002")
OTHER_USER_ID = uuid.UUID("22222222-0000-0000-0000-000000000003")


async def _seed(session):
    session.add(
        Organization(
            id=ORG_ID,
            name="Notif Test Org",
            slug=f"notif-{uuid.uuid4().hex[:8]}",
            schema_name=f"notif_{uuid.uuid4().hex[:8]}",
            country="India",
        )
    )
    for uid in (USER_ID, OTHER_USER_ID):
        session.add(
            User(
                id=uid,
                organization_id=ORG_ID,
                email=f"notif-{uuid.uuid4().hex[:8]}@solidcare.test",
                hashed_password="x",
                first_name="Notif",
                last_name="User",
                status=UserStatus.ACTIVE,
            )
        )
    await session.flush()


def _svc(session):
    return NotificationService(NotificationRepository(session))


async def test_create_in_app_and_unread_count(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    assert await svc.unread_count(ORG_ID, USER_ID) == 0

    await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Reminder", "Your appt is tomorrow")
    await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Reminder 2", "Another one")

    assert await svc.unread_count(ORG_ID, USER_ID) == 2


async def test_unread_count_scoped_per_user(setup_database, db_session):
    """A notification created for one user must not count against another."""
    await _seed(db_session)
    svc = _svc(db_session)

    await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "For user 1", "body")

    assert await svc.unread_count(ORG_ID, USER_ID) == 1
    assert await svc.unread_count(ORG_ID, OTHER_USER_ID) == 0


async def test_mark_read_reduces_unread_count(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    n = await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Sub", "body")
    assert await svc.unread_count(ORG_ID, USER_ID) == 1

    await svc.mark_read(n.id, USER_ID)

    assert await svc.unread_count(ORG_ID, USER_ID) == 0


async def test_mark_read_unknown_notification_raises_not_found(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    with pytest.raises(NotFoundError):
        await svc.mark_read(uuid.uuid4(), USER_ID)


async def test_mark_read_by_wrong_user_raises_not_found(setup_database, db_session):
    """A user must not be able to mark another user's notification as read."""
    await _seed(db_session)
    svc = _svc(db_session)

    n = await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Sub", "body")

    with pytest.raises(NotFoundError):
        await svc.mark_read(n.id, OTHER_USER_ID)

    # Original owner's unread count is unaffected by the failed attempt.
    assert await svc.unread_count(ORG_ID, USER_ID) == 1


async def test_mark_all_read(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    for i in range(3):
        await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, f"Sub {i}", "body")
    await svc.create_in_app(ORG_ID, OTHER_USER_ID, NotificationType.APPOINTMENT_REMINDER, "Other", "body")

    marked = await svc.mark_all_read(ORG_ID, USER_ID)

    assert marked == 3
    assert await svc.unread_count(ORG_ID, USER_ID) == 0
    # Other user's notification untouched.
    assert await svc.unread_count(ORG_ID, OTHER_USER_ID) == 1


async def test_list_for_user_filters_by_is_read(setup_database, db_session):
    await _seed(db_session)
    svc = _svc(db_session)

    n1 = await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Unread", "body")
    n2 = await svc.create_in_app(ORG_ID, USER_ID, NotificationType.APPOINTMENT_REMINDER, "Will be read", "body")
    await svc.mark_read(n2.id, USER_ID)

    params = PaginationParams(page=1, page_size=20)
    unread_only = await svc.list_for_user(ORG_ID, USER_ID, params, is_read=False)

    ids = {item.id for item in unread_only.items}
    assert n1.id in ids
    assert n2.id not in ids
