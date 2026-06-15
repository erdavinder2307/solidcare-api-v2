import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.modules.patients.models import BloodGroup, ConsentType, DocumentType, MaritalStatus


class PatientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = None
    blood_group: BloodGroup | None = None
    marital_status: MaritalStatus | None = None
    phone: str = Field(min_length=10, max_length=20)
    alternate_phone: str | None = None
    email: EmailStr | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    country: str = "India"
    occupation: str | None = None
    known_allergies: list[str] | None = None
    known_conditions: list[str] | None = None
    abha_number: str | None = None
    abha_address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    insurance_provider: str | None = None
    insurance_policy_number: str | None = None


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    gender: str | None = None
    blood_group: BloodGroup | None = None
    marital_status: MaritalStatus | None = None
    alternate_phone: str | None = None
    email: EmailStr | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    known_allergies: list[str] | None = None
    known_conditions: list[str] | None = None
    abha_number: str | None = None
    abha_address: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    emergency_contact_relation: str | None = None
    insurance_provider: str | None = None
    insurance_policy_number: str | None = None


class PatientResponse(BaseModel):
    id: uuid.UUID
    uhid: str
    first_name: str
    last_name: str
    full_name: str
    date_of_birth: date | None
    gender: str | None
    blood_group: BloodGroup | None
    marital_status: MaritalStatus | None
    phone: str
    alternate_phone: str | None
    email: str | None
    address_line1: str | None
    city: str | None
    state: str | None
    pincode: str | None
    country: str
    known_allergies: list[str] | None
    known_conditions: list[str] | None
    abha_number: str | None
    abha_address: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientListItem(BaseModel):
    id: uuid.UUID
    uhid: str
    full_name: str
    phone: str
    email: str | None
    date_of_birth: date | None
    gender: str | None
    blood_group: BloodGroup | None
    city: str | None
    abha_number: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsentUpdate(BaseModel):
    consent_type: ConsentType
    consented: bool
    notes: str | None = None


class PatientDocumentResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    document_type: DocumentType
    file_name: str
    content_type: str | None
    file_size_bytes: int | None
    notes: str | None
    created_at: datetime
    download_url: str | None = None

    model_config = {"from_attributes": True}
