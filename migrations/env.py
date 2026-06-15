import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them for autogenerate
from app.database import Base  # noqa: E402
from app.modules.organizations.models import Organization  # noqa: F401, E402
from app.modules.clinics.models import Clinic  # noqa: F401, E402
from app.modules.users.models import Permission, Role, RolePermission, User, UserRole  # noqa: F401, E402
from app.modules.patients.models import Patient, PatientConsent, PatientDocument  # noqa: F401, E402
from app.modules.doctors.models import Doctor, DoctorClinicAssignment, DoctorSchedule  # noqa: F401, E402
from app.modules.appointments.models import Appointment  # noqa: F401, E402
from app.modules.clinical.encounters.models import Encounter  # noqa: F401, E402
from app.modules.clinical.vitals.models import Vital  # noqa: F401, E402
from app.modules.clinical.diagnoses.models import Diagnosis, ICD10Code  # noqa: F401, E402
from app.modules.clinical.lab_orders.models import LabOrder, LabOrderItem, LabResult  # noqa: F401, E402
from app.modules.medicines.models import Medicine  # noqa: F401, E402
from app.modules.prescriptions.models import Prescription, PrescriptionItem  # noqa: F401, E402
from app.modules.billing.invoices.models import Invoice, InvoiceLineItem, ServiceChargeMaster  # noqa: F401, E402
from app.modules.billing.payments.models import Payment  # noqa: F401, E402
from app.modules.notifications.models import Notification  # noqa: F401, E402
from app.modules.audit.models import AuditLog  # noqa: F401, E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
