"""Import all ORM models so SQLAlchemy mappers are fully configured at startup."""

from app.modules.appointments.models import Appointment  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.billing.invoices.models import Invoice, InvoiceLineItem, ServiceChargeMaster  # noqa: F401
from app.modules.billing.payments.models import Payment  # noqa: F401
from app.modules.clinical.diagnoses.models import Diagnosis, ICD10Code  # noqa: F401
from app.modules.clinical.encounters.models import Encounter  # noqa: F401
from app.modules.clinical.lab_orders.models import LabOrder, LabOrderItem, LabResult  # noqa: F401
from app.modules.clinical.vitals.models import Vital  # noqa: F401
from app.modules.clinics.models import Clinic  # noqa: F401
from app.modules.doctors.models import Doctor, DoctorClinicAssignment, DoctorSchedule  # noqa: F401
from app.modules.medicines.models import Medicine  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.organizations.models import Organization  # noqa: F401
from app.modules.patients.models import Patient, PatientConsent, PatientDocument  # noqa: F401
from app.modules.prescriptions.models import Prescription, PrescriptionItem  # noqa: F401
from app.modules.users.models import Permission, Role, RolePermission, User, UserRole  # noqa: F401
