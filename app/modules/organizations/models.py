import uuid
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models.base import BaseModel


class SubscriptionPlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"


class OrganizationStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    INACTIVE = "inactive"


class Organization(BaseModel):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    gstin: Mapped[str | None] = mapped_column(String(20))
    pan: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(20))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    pincode: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(50), default="India")
    logo_url: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(255))
    subscription_plan: Mapped[SubscriptionPlan] = mapped_column(
        SAEnum(SubscriptionPlan), default=SubscriptionPlan.FREE
    )
    status: Mapped[OrganizationStatus] = mapped_column(
        SAEnum(OrganizationStatus), default=OrganizationStatus.TRIAL
    )
    # DEPRECATED — see docs/adr/002-shared-schema-tenancy.md. Isolation is shared-
    # schema + `organization_id` discriminator, not schema-per-tenant. Do not read
    # or rely on this column in new code; it is retained (not dropped) until F6
    # (Postgres RLS) lands and a repo-wide grep confirms nothing references it.
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    clinics: Mapped[list["Clinic"]] = relationship("Clinic", back_populates="organization")


class MembershipStatus(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"


class Membership(BaseModel):
    """A user's membership in an organization.

    Introduced to replace the single `users.organization_id NOT NULL` constraint
    with a proper N:M relationship — one user can belong to multiple orgs (e.g. an
    independent doctor who is later invited to a clinic). `users.organization_id`
    is kept in place as the "home"/default org during the migration window and is
    not read by new code; see ROADMAP.md Phase 1 (F1/F2).
    """

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus), default=MembershipStatus.ACTIVE, nullable=False
    )
    # The org selected by default when a user with multiple memberships logs in.
    # Exactly one TRUE per user is an application-level invariant (not DB-enforced,
    # to keep the migration additive — enforce via a partial unique index later).
    is_default: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
