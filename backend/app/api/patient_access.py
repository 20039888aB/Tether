import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.orm import selectinload

from app.api.auth import DbSession, _audit, require_permission
from app.db.models import (
    Clinic,
    ConsultationNote,
    Facility,
    FacilityClinic,
    OutpatientVisit,
    Patient,
    PatientNumberCounter,
    User,
    VisitTriage,
    VisitType,
    clinic_visit_types,
)

router = APIRouter(tags=["patient access"])

NextOfKinRelationship = Literal[
    "spouse",
    "partner",
    "parent",
    "mother",
    "father",
    "child",
    "son",
    "daughter",
    "sibling",
    "brother",
    "sister",
    "grandparent",
    "grandmother",
    "grandfather",
    "grandchild",
    "aunt",
    "uncle",
    "niece",
    "nephew",
    "cousin",
    "step_parent",
    "step_child",
    "parent_in_law",
    "child_in_law",
    "sibling_in_law",
    "guardian",
    "legal_guardian",
    "foster_parent",
    "caregiver",
    "friend",
    "neighbor",
    "other",
]


class PatientCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    sex_at_birth: Literal["female", "male", "intersex", "unknown"] | None = None
    phone_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=500)
    next_of_kin_name: str | None = Field(default=None, max_length=200)
    next_of_kin_phone: str | None = Field(default=None, max_length=32)
    next_of_kin_relationship: NextOfKinRelationship | None = None
    next_of_kin_relationship_other: str | None = Field(default=None, max_length=100)
    nationality: str | None = Field(default=None, max_length=80)
    document_type: str | None = Field(default=None, max_length=40)
    document_number: str | None = Field(default=None, max_length=100)
    marital_status: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=100)
    phone_country_code: str = Field(default="+254", max_length=8)
    city_town: str | None = Field(default=None, max_length=100)
    sub_county_estate: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=32)
    next_of_kin_phone_country_code: str = Field(default="+254", max_length=8)
    next_of_kin_email: str | None = Field(default=None, max_length=320)
    next_of_kin_id_number: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    debtor_account: str | None = Field(default=None, max_length=100)
    staff_account: str | None = Field(default=None, max_length=100)
    operating_currency: str = Field(default="KES", min_length=3, max_length=3)
    legacy_number: str | None = Field(default=None, max_length=100)
    tax_pin: str | None = Field(default=None, max_length=32)

    @field_validator("first_name", "middle_name", "last_name")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        if not normalized and value is not None:
            raise ValueError("Name fields must not be blank.")
        return normalized or None

    @field_validator("phone_number", "next_of_kin_phone")
    @classmethod
    def normalize_phone_number(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        if normalized and not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,30}", normalized):
            raise ValueError("Enter a valid phone number.")
        return normalized or None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        normalized = value.strip().lower() if value else ""
        if normalized and ("@" not in normalized or any(char.isspace() for char in normalized)):
            raise ValueError("Enter a valid email address.")
        return normalized or None

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @field_validator(
        "nationality",
        "document_type",
        "document_number",
        "marital_status",
        "category",
        "city_town",
        "sub_county_estate",
        "postal_code",
        "next_of_kin_email",
        "next_of_kin_id_number",
        "department",
        "debtor_account",
        "staff_account",
        "legacy_number",
        "tax_pin",
    )
    @classmethod
    def normalize_optional_registration_fields(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @field_validator("phone_country_code", "next_of_kin_phone_country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"\+[1-9][0-9]{0,3}", normalized):
            raise ValueError("Enter a valid international calling code.")
        return normalized

    @field_validator("operating_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", normalized):
            raise ValueError("Enter a valid three-letter currency code.")
        return normalized

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return value

    @field_validator("next_of_kin_name", "next_of_kin_relationship_other")
    @classmethod
    def normalize_next_of_kin_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @model_validator(mode="after")
    def validate_next_of_kin(self) -> "PatientCreateRequest":
        kin_details = (
            self.next_of_kin_name,
            self.next_of_kin_phone,
            self.next_of_kin_relationship,
        )
        if any(kin_details) and not all(kin_details):
            raise ValueError("Enter the next-of-kin name, phone and relationship together.")
        if self.next_of_kin_relationship == "other" and not self.next_of_kin_relationship_other:
            raise ValueError("Specify the next-of-kin relationship when Other is selected.")
        if self.next_of_kin_relationship != "other":
            self.next_of_kin_relationship_other = None
        return self


class PatientUpdateRequest(PatientCreateRequest):
    version: int = Field(ge=1)


class OutpatientVisitCreateRequest(BaseModel):
    patient_id: UUID
    clinic: str = Field(min_length=1, max_length=128)
    visit_type: str = Field(min_length=1, max_length=64)
    clinic_id: int | None = Field(default=None, ge=1)
    visit_type_id: int | None = Field(default=None, ge=1)

    @field_validator("clinic", "visit_type")
    @classmethod
    def normalize_nonblank_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized


class VisitTriageCreateRequest(BaseModel):
    blood_pressure_systolic: int | None = Field(default=None, ge=40, le=300)
    blood_pressure_diastolic: int | None = Field(default=None, ge=20, le=200)
    pulse_rate_bpm: int | None = Field(default=None, ge=0, le=300)
    temperature_celsius: float | None = Field(default=None, ge=25, le=45)
    respiratory_rate_bpm: int | None = Field(default=None, ge=0, le=100)
    oxygen_saturation_percent: int | None = Field(default=None, ge=0, le=100)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_cm: float | None = Field(default=None, gt=0, le=300)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def normalize_triage_notes(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @model_validator(mode="after")
    def validate_blood_pressure(self) -> "VisitTriageCreateRequest":
        if (self.blood_pressure_systolic is None) != (
            self.blood_pressure_diastolic is None
        ):
            raise ValueError("Enter both blood pressure values.")
        if (
            self.blood_pressure_systolic is not None
            and self.blood_pressure_diastolic is not None
            and self.blood_pressure_systolic <= self.blood_pressure_diastolic
        ):
            raise ValueError("Systolic pressure must be greater than diastolic pressure.")
        return self


class ConsultationNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)

    @field_validator("body")
    @classmethod
    def normalize_note_body(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Consultation note must not be blank.")
        return normalized


class ConsultationNoteUpdateRequest(ConsultationNoteCreateRequest):
    version: int = Field(ge=1)


class ConsultationNoteSignRequest(BaseModel):
    version: int = Field(ge=1)


def _patient_payload(patient: Patient) -> dict[str, object]:
    return {
        "id": str(patient.id),
        "patient_number": patient.patient_number,
        "first_name": patient.first_name,
        "middle_name": patient.middle_name,
        "last_name": patient.last_name,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex_at_birth": patient.sex_at_birth,
        "phone_number": patient.phone_number,
        "email": patient.email,
        "address": patient.address,
        "next_of_kin_name": patient.next_of_kin_name,
        "next_of_kin_phone": patient.next_of_kin_phone,
        "next_of_kin_relationship": patient.next_of_kin_relationship,
        "next_of_kin_relationship_other": patient.next_of_kin_relationship_other,
        "nationality": patient.nationality,
        "document_type": patient.document_type,
        "document_number": patient.document_number,
        "marital_status": patient.marital_status,
        "category": patient.category,
        "phone_country_code": patient.phone_country_code,
        "city_town": patient.city_town,
        "sub_county_estate": patient.sub_county_estate,
        "postal_code": patient.postal_code,
        "next_of_kin_phone_country_code": patient.next_of_kin_phone_country_code,
        "next_of_kin_email": patient.next_of_kin_email,
        "next_of_kin_id_number": patient.next_of_kin_id_number,
        "department": patient.department,
        "debtor_account": patient.debtor_account,
        "staff_account": patient.staff_account,
        "operating_currency": patient.operating_currency,
        "legacy_number": patient.legacy_number,
        "tax_pin": patient.tax_pin,
        "version": patient.version,
        "created_at": patient.created_at.isoformat() if patient.created_at else None,
        "updated_at": patient.updated_at.isoformat() if patient.updated_at else None,
    }


def _visit_payload(visit: OutpatientVisit) -> dict[str, object]:
    return {
        "id": str(visit.id),
        "patient_id": str(visit.patient_id),
        "patient_number": visit.patient.patient_number,
        "patient_name": f"{visit.patient.first_name} {visit.patient.last_name}",
        "visit_number": visit.visit_number,
        "clinic": visit.clinic,
        "visit_type": visit.visit_type,
        "status": visit.status,
        "workflow_state": visit.workflow_state,
        "created_at": visit.created_at.isoformat() if visit.created_at else None,
    }


def _triage_payload(triage: VisitTriage) -> dict[str, object]:
    return {
        "id": str(triage.id),
        "blood_pressure_systolic": triage.blood_pressure_systolic,
        "blood_pressure_diastolic": triage.blood_pressure_diastolic,
        "pulse_rate_bpm": triage.pulse_rate_bpm,
        "temperature_celsius": triage.temperature_celsius,
        "respiratory_rate_bpm": triage.respiratory_rate_bpm,
        "oxygen_saturation_percent": triage.oxygen_saturation_percent,
        "weight_kg": triage.weight_kg,
        "height_cm": triage.height_cm,
        "pain_score": triage.pain_score,
        "notes": triage.notes,
        "created_at": triage.created_at.isoformat() if triage.created_at else None,
    }


def _consultation_note_payload(note: ConsultationNote) -> dict[str, object]:
    return {
        "id": str(note.id),
        "parent_note_id": str(note.parent_note_id) if note.parent_note_id else None,
        "note_type": note.note_type,
        "body": note.body,
        "status": note.status,
        "author_user_id": str(note.author_user_id),
        "version": note.version,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        "signed_at": note.signed_at.isoformat() if note.signed_at else None,
    }


def _clinical_visit_payload(visit: OutpatientVisit) -> dict[str, object]:
    return {
        **_visit_payload(visit),
        "patient": _patient_payload(visit.patient),
        "triage": _triage_payload(visit.triage) if visit.triage else None,
        "consultation_notes": [
            _consultation_note_payload(note) for note in visit.consultation_notes
        ],
    }


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _next_patient_number(db: DbSession) -> str:
    await db.execute(
        text(
            "INSERT INTO patient_number_counters (id, value) VALUES (1, 11313) "
            "ON CONFLICT (id) DO NOTHING"
        )
    )
    await db.execute(
        update(PatientNumberCounter)
        .where(PatientNumberCounter.id == 1)
        .values(value=PatientNumberCounter.value + 1)
    )
    number = await db.scalar(
        select(PatientNumberCounter.value).where(PatientNumberCounter.id == 1)
    )
    if number is None:
        raise RuntimeError("The patient number counter could not be incremented.")
    return f"TTH-{number}"


@router.get("/patients")
async def search_patients(
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.search-existing-patient-records.view")),
    ],
    q: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    statement = select(Patient)
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        statement = statement.where(
            or_(
                Patient.patient_number.ilike(pattern, escape="\\"),
                Patient.first_name.ilike(pattern, escape="\\"),
                Patient.middle_name.ilike(pattern, escape="\\"),
                Patient.last_name.ilike(pattern, escape="\\"),
                Patient.phone_number.ilike(pattern, escape="\\"),
            )
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    patients = (
        await db.scalars(
            statement.order_by(Patient.last_name, Patient.first_name, Patient.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    db.add(
        _audit(
            request,
            action="patient.records.search",
            outcome="success",
            actor_user_id=current.id,
            resource_type="patient",
            event_metadata={"limit": limit, "offset": offset, "result_count": len(patients)},
        )
    )
    await db.commit()
    return {
        "items": [_patient_payload(patient) for patient in patients],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/patients/next-number")
async def get_next_patient_number(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.patient-registration-and-biodata.view")),
    ],
) -> dict[str, str]:
    last_number = await db.scalar(
        select(PatientNumberCounter.value).where(PatientNumberCounter.id == 1)
    )
    return {"patient_number": f"TTH-{(last_number or 11313) + 1}"}


@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def register_patient(
    patient_data: PatientCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.patient-registration-and-biodata.add")),
    ],
) -> dict[str, object]:
    duplicate_conditions = []
    if patient_data.phone_number:
        duplicate_conditions.append(Patient.phone_number == patient_data.phone_number)
    if patient_data.date_of_birth:
        duplicate_conditions.append(
            (func.lower(Patient.first_name) == patient_data.first_name.lower())
            & (func.lower(Patient.last_name) == patient_data.last_name.lower())
            & (Patient.date_of_birth == patient_data.date_of_birth)
        )
    duplicate_id = None
    if duplicate_conditions:
        duplicate_id = await db.scalar(
            select(Patient.id).where(or_(*duplicate_conditions)).limit(1)
        )
    if duplicate_id is not None:
        db.add(
            _audit(
                request,
                action="patient.registration.possible-duplicate",
                outcome="denied",
                actor_user_id=current.id,
                resource_id=str(duplicate_id),
                resource_type="patient",
                event_metadata={"duplicate_review_required": True},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="possible_duplicate_patient",
        )

    patient_id = uuid4()
    patient = Patient(
        id=patient_id,
        patient_number=await _next_patient_number(db),
        first_name=patient_data.first_name,
        middle_name=patient_data.middle_name,
        last_name=patient_data.last_name,
        date_of_birth=patient_data.date_of_birth,
        sex_at_birth=patient_data.sex_at_birth,
        phone_number=patient_data.phone_number,
        email=patient_data.email,
        address=patient_data.address,
        next_of_kin_name=patient_data.next_of_kin_name,
        next_of_kin_phone=patient_data.next_of_kin_phone,
        next_of_kin_relationship=patient_data.next_of_kin_relationship,
        next_of_kin_relationship_other=patient_data.next_of_kin_relationship_other,
        nationality=patient_data.nationality,
        document_type=patient_data.document_type,
        document_number=patient_data.document_number,
        marital_status=patient_data.marital_status,
        category=patient_data.category,
        phone_country_code=patient_data.phone_country_code,
        city_town=patient_data.city_town,
        sub_county_estate=patient_data.sub_county_estate,
        postal_code=patient_data.postal_code,
        next_of_kin_phone_country_code=patient_data.next_of_kin_phone_country_code,
        next_of_kin_email=patient_data.next_of_kin_email,
        next_of_kin_id_number=patient_data.next_of_kin_id_number,
        department=patient_data.department,
        debtor_account=patient_data.debtor_account,
        staff_account=patient_data.staff_account,
        operating_currency=patient_data.operating_currency,
        legacy_number=patient_data.legacy_number,
        tax_pin=patient_data.tax_pin,
        created_by=current.id,
        updated_by=current.id,
        outpatient_visits=[],
    )
    db.add(patient)
    await db.flush()
    db.add(
        _audit(
            request,
            action="patient.registration.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(patient.id),
            resource_type="patient",
        )
    )
    await db.commit()
    await db.refresh(patient)
    return _patient_payload(patient)


@router.get("/outpatient-visits")
async def list_outpatient_visits(
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.open-outpatient-visit.view")),
    ],
    visit_status: Annotated[
        Literal["queued", "cancelled", "completed"] | None,
        Query(alias="status"),
    ] = "queued",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    statement = select(OutpatientVisit).options(selectinload(OutpatientVisit.patient))
    if visit_status is not None:
        statement = statement.where(OutpatientVisit.status == visit_status)
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    visits = (
        await db.scalars(
            statement.order_by(OutpatientVisit.created_at.desc(), OutpatientVisit.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    db.add(
        _audit(
            request,
            action="outpatient.visit-queue.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="outpatient_visit",
            event_metadata={"limit": limit, "offset": offset, "result_count": len(visits)},
        )
    )
    await db.commit()
    return {
        "items": [_visit_payload(visit) for visit in visits],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/outpatient-visits", status_code=status.HTTP_201_CREATED)
async def open_outpatient_visit(
    visit_data: OutpatientVisitCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.open-outpatient-visit.add")),
    ],
) -> dict[str, object]:
    patient = await db.get(Patient, visit_data.patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    clinic_id = None
    clinic_name = visit_data.clinic
    visit_type_name = visit_data.visit_type
    if visit_data.clinic_id is not None:
        facility_id = current.facility_id or 1
        clinic = await db.scalar(
            select(Clinic)
            .join(FacilityClinic, FacilityClinic.clinic_id == Clinic.id)
            .join(Facility, Facility.id == FacilityClinic.facility_id)
            .where(
                Clinic.id == visit_data.clinic_id,
                Clinic.is_deleted.is_(False),
                Facility.is_active.is_(True),
                FacilityClinic.facility_id == facility_id,
                FacilityClinic.is_enabled.is_(True),
                or_(
                    FacilityClinic.is_unavailable.is_(False),
                    FacilityClinic.unavailable_until <= func.now(),
                ),
            )
        )
        if clinic is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="clinic_not_available_at_this_facility",
            )
        visit_type_statement = (
            select(VisitType)
            .join(clinic_visit_types, clinic_visit_types.c.visit_type_id == VisitType.id)
            .where(
                clinic_visit_types.c.clinic_id == clinic.id,
                VisitType.is_active.is_(True),
            )
        )
        if visit_data.visit_type_id is not None:
            visit_type_statement = visit_type_statement.where(
                VisitType.id == visit_data.visit_type_id
            )
        else:
            visit_type_statement = visit_type_statement.where(
                func.lower(VisitType.name) == visit_data.visit_type.lower()
            )
        visit_type = await db.scalar(visit_type_statement)
        if visit_type is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="visit_type_not_available_for_clinic",
            )
        clinic_id = clinic.id
        clinic_name = clinic.name
        visit_type_name = visit_type.name

    visit_id = uuid4()
    visit = OutpatientVisit(
        id=visit_id,
        patient_id=patient.id,
        clinic_id=clinic_id,
        visit_number=f"OPD-{visit_id.hex.upper()}",
        clinic=clinic_name,
        visit_type=visit_type_name,
        status="queued",
        created_by=current.id,
        patient=patient,
    )
    db.add(visit)
    await db.flush()
    db.add(
        _audit(
            request,
            action="outpatient.visit.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit.id),
            resource_type="outpatient_visit",
            event_metadata={
                "patient_id": str(patient.id),
                "clinic": visit.clinic,
                "visit_type": visit.visit_type,
            },
        )
    )
    await db.commit()
    return _visit_payload(visit)


@router.get("/patients/{patient_id}")
async def get_patient(
    patient_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.search-existing-patient-records.view")),
    ],
) -> dict[str, object]:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")
    db.add(
        _audit(
            request,
            action="patient.record.read",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(patient.id),
            resource_type="patient",
        )
    )
    await db.commit()
    return _patient_payload(patient)


@router.put("/patients/{patient_id}")
async def update_patient(
    patient_id: UUID,
    patient_data: PatientUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.patient-registration-and-biodata.edit")),
    ],
) -> dict[str, object]:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patient_not_found")

    duplicate_conditions = []
    if patient_data.phone_number:
        duplicate_conditions.append(Patient.phone_number == patient_data.phone_number)
    if patient_data.date_of_birth:
        duplicate_conditions.append(
            (func.lower(Patient.first_name) == patient_data.first_name.lower())
            & (func.lower(Patient.last_name) == patient_data.last_name.lower())
            & (Patient.date_of_birth == patient_data.date_of_birth)
        )
    duplicate_id = None
    if duplicate_conditions:
        duplicate_id = await db.scalar(
            select(Patient.id)
            .where(Patient.id != patient.id, or_(*duplicate_conditions))
            .limit(1)
        )
    if duplicate_id is not None:
        db.add(
            _audit(
                request,
                action="patient.registration.possible-duplicate",
                outcome="denied",
                actor_user_id=current.id,
                resource_id=str(duplicate_id),
                resource_type="patient",
                event_metadata={"duplicate_review_required": True},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="possible_duplicate_patient",
        )

    update_result = await db.execute(
        update(Patient)
        .where(Patient.id == patient.id, Patient.version == patient_data.version)
        .values(
            first_name=patient_data.first_name,
            middle_name=patient_data.middle_name,
            last_name=patient_data.last_name,
            date_of_birth=patient_data.date_of_birth,
            sex_at_birth=patient_data.sex_at_birth,
            phone_number=patient_data.phone_number,
            email=patient_data.email,
            address=patient_data.address,
            next_of_kin_name=patient_data.next_of_kin_name,
            next_of_kin_phone=patient_data.next_of_kin_phone,
            next_of_kin_relationship=patient_data.next_of_kin_relationship,
            next_of_kin_relationship_other=patient_data.next_of_kin_relationship_other,
            nationality=patient_data.nationality,
            document_type=patient_data.document_type,
            document_number=patient_data.document_number,
            marital_status=patient_data.marital_status,
            category=patient_data.category,
            phone_country_code=patient_data.phone_country_code,
            city_town=patient_data.city_town,
            sub_county_estate=patient_data.sub_county_estate,
            postal_code=patient_data.postal_code,
            next_of_kin_phone_country_code=patient_data.next_of_kin_phone_country_code,
            next_of_kin_email=patient_data.next_of_kin_email,
            next_of_kin_id_number=patient_data.next_of_kin_id_number,
            department=patient_data.department,
            debtor_account=patient_data.debtor_account,
            staff_account=patient_data.staff_account,
            operating_currency=patient_data.operating_currency,
            legacy_number=patient_data.legacy_number,
            tax_pin=patient_data.tax_pin,
            updated_by=current.id,
            updated_at=func.now(),
            version=Patient.version + 1,
        )
    )
    if update_result.rowcount != 1:
        db.add(
            _audit(
                request,
                action="patient.registration.update-conflict",
                outcome="denied",
                actor_user_id=current.id,
                resource_id=str(patient.id),
                resource_type="patient",
                event_metadata={"reason": "stale_version"},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="record_changed_refresh_before_saving",
        )
    db.add(
        _audit(
            request,
            action="patient.registration.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(patient.id),
            resource_type="patient",
            event_metadata={"updated_fields": sorted(patient_data.model_fields_set)},
        )
    )
    await db.commit()
    await db.refresh(patient)
    return _patient_payload(patient)


@router.get("/nursing/triage-queue")
async def list_nursing_triage_queue(
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("nursing.triage-and-vital-signs.view")),
    ],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    statement = (
        select(OutpatientVisit)
        .options(
            selectinload(OutpatientVisit.patient),
            selectinload(OutpatientVisit.triage),
            selectinload(OutpatientVisit.consultation_notes),
        )
        .where(
            OutpatientVisit.status == "queued",
            OutpatientVisit.workflow_state == "awaiting_triage",
        )
    )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    visits = (
        await db.scalars(
            statement.order_by(OutpatientVisit.created_at, OutpatientVisit.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    db.add(
        _audit(
            request,
            action="nursing.triage-queue.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="outpatient_visit",
            event_metadata={"limit": limit, "offset": offset, "result_count": len(visits)},
        )
    )
    await db.commit()
    return {
        "items": [_clinical_visit_payload(visit) for visit in visits],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/nursing/visits/{visit_id}/triage", status_code=status.HTTP_201_CREATED)
async def submit_visit_triage(
    visit_id: UUID,
    triage_data: VisitTriageCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("nursing.triage-and-vital-signs.add")),
    ],
) -> dict[str, object]:
    visit = await db.get(OutpatientVisit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="visit_not_found")
    if visit.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_not_waiting_for_triage",
        )

    transition = await db.execute(
        update(OutpatientVisit)
        .where(
            OutpatientVisit.id == visit_id,
            OutpatientVisit.status == "queued",
            OutpatientVisit.workflow_state == "awaiting_triage",
        )
        .values(workflow_state="awaiting_doctor")
    )
    if transition.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_not_waiting_for_triage",
        )

    triage = VisitTriage(
        visit_id=visit_id,
        created_by=current.id,
        **triage_data.model_dump(),
    )
    db.add(triage)
    await db.flush()
    db.add(
        _audit(
            request,
            action="nursing.triage.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit_id),
            resource_type="outpatient_visit",
            event_metadata={"triage_id": str(triage.id)},
        )
    )
    await db.commit()
    await db.refresh(triage)
    return _triage_payload(triage)


@router.get("/doctors/consultation-queue")
async def list_doctor_consultation_queue(
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.view")),
    ],
    include_completed: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, object]:
    statement = (
        select(OutpatientVisit)
        .options(
            selectinload(OutpatientVisit.patient),
            selectinload(OutpatientVisit.triage),
            selectinload(OutpatientVisit.consultation_notes),
        )
    )
    active_visits = and_(
        OutpatientVisit.status == "queued",
        OutpatientVisit.workflow_state.in_(("awaiting_doctor", "consultation_in_progress")),
    )
    if include_completed:
        statement = statement.where(
            or_(
                active_visits,
                and_(
                    OutpatientVisit.status == "completed",
                    OutpatientVisit.workflow_state == "completed",
                ),
            )
        )
    else:
        statement = statement.where(active_visits)
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    visits = (
        await db.scalars(
            statement.order_by(OutpatientVisit.created_at, OutpatientVisit.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    db.add(
        _audit(
            request,
            action="clinical.consultation-queue.read",
            outcome="success",
            actor_user_id=current.id,
            resource_type="outpatient_visit",
            event_metadata={
                "include_completed": include_completed,
                "limit": limit,
                "offset": offset,
                "result_count": len(visits),
            },
        )
    )
    await db.commit()
    return {
        "items": [_clinical_visit_payload(visit) for visit in visits],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/doctors/visits/{visit_id}/start")
async def start_consultation(
    visit_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.add")),
    ],
) -> dict[str, str]:
    visit = await db.get(OutpatientVisit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="visit_not_found")
    if visit.status != "queued":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_not_available_for_consultation",
        )
    if visit.workflow_state == "consultation_in_progress":
        return {"workflow_state": visit.workflow_state}
    transition = await db.execute(
        update(OutpatientVisit)
        .where(
            OutpatientVisit.id == visit_id,
            OutpatientVisit.status == "queued",
            OutpatientVisit.workflow_state == "awaiting_doctor",
        )
        .values(workflow_state="consultation_in_progress")
    )
    if transition.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_not_available_for_consultation",
        )
    db.add(
        _audit(
            request,
            action="clinical.consultation.start",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit_id),
            resource_type="outpatient_visit",
        )
    )
    await db.commit()
    return {"workflow_state": "consultation_in_progress"}


@router.post(
    "/doctors/visits/{visit_id}/notes",
    status_code=status.HTTP_201_CREATED,
)
async def create_consultation_note(
    visit_id: UUID,
    note_data: ConsultationNoteCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.add")),
    ],
) -> dict[str, object]:
    visit = await db.get(OutpatientVisit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="visit_not_found")
    if visit.status != "queued" or visit.workflow_state != "consultation_in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="consultation_not_in_progress",
        )
    note = ConsultationNote(
        visit_id=visit_id,
        author_user_id=current.id,
        note_type="consultation",
        body=note_data.body,
    )
    db.add(note)
    await db.flush()
    db.add(
        _audit(
            request,
            action="clinical.consultation-note.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(note.id),
            resource_type="consultation_note",
            event_metadata={"visit_id": str(visit_id), "note_type": note.note_type},
        )
    )
    await db.commit()
    await db.refresh(note)
    return _consultation_note_payload(note)


@router.put("/doctors/notes/{note_id}")
async def update_consultation_note(
    note_id: UUID,
    note_data: ConsultationNoteUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.edit")),
    ],
) -> dict[str, object]:
    note = await db.get(ConsultationNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note_not_found")
    if note.author_user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="note_author_required")
    if note.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="signed_note_is_immutable")
    visit = await db.get(OutpatientVisit, note.visit_id)
    if visit is None or not (
        visit.workflow_state == "consultation_in_progress"
        or (visit.status == "completed" and note.note_type == "addendum")
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="consultation_not_in_progress",
        )
    update_result = await db.execute(
        update(ConsultationNote)
        .where(
            ConsultationNote.id == note.id,
            ConsultationNote.version == note_data.version,
            ConsultationNote.status == "draft",
            ConsultationNote.author_user_id == current.id,
        )
        .values(
            body=note_data.body,
            version=ConsultationNote.version + 1,
            updated_at=func.now(),
        )
    )
    if update_result.rowcount != 1:
        db.add(
            _audit(
                request,
                action="clinical.consultation-note.update-conflict",
                outcome="denied",
                actor_user_id=current.id,
                resource_id=str(note.id),
                resource_type="consultation_note",
                event_metadata={"reason": "stale_version"},
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="record_changed_refresh_before_saving",
        )
    db.add(
        _audit(
            request,
            action="clinical.consultation-note.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(note.id),
            resource_type="consultation_note",
            event_metadata={"visit_id": str(note.visit_id)},
        )
    )
    await db.commit()
    await db.refresh(note)
    return _consultation_note_payload(note)


@router.post("/doctors/notes/{note_id}/sign")
async def sign_consultation_note(
    note_id: UUID,
    sign_data: ConsultationNoteSignRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.approve")),
    ],
) -> dict[str, object]:
    note = await db.get(ConsultationNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note_not_found")
    if note.author_user_id != current.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="note_author_required")
    if note.status != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="note_already_signed")
    visit = await db.get(OutpatientVisit, note.visit_id)
    if visit is None or visit.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="visit_not_available")
    if note.version != sign_data.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="record_changed_refresh_before_saving",
        )
    sign_time = datetime.now(UTC)
    sign_result = await db.execute(
        update(ConsultationNote)
        .where(
            ConsultationNote.id == note.id,
            ConsultationNote.version == sign_data.version,
            ConsultationNote.status == "draft",
            ConsultationNote.author_user_id == current.id,
        )
        .values(
            status="signed",
            signed_at=sign_time,
            version=ConsultationNote.version + 1,
            updated_at=sign_time,
        )
    )
    if sign_result.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="record_changed_refresh_before_saving",
        )
    db.add(
        _audit(
            request,
            action="clinical.consultation-note.sign",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(note.id),
            resource_type="consultation_note",
            event_metadata={"visit_id": str(note.visit_id), "note_type": note.note_type},
        )
    )
    await db.commit()
    await db.refresh(note)
    return _consultation_note_payload(note)


@router.post(
    "/doctors/notes/{note_id}/addenda",
    status_code=status.HTTP_201_CREATED,
)
async def create_consultation_addendum(
    note_id: UUID,
    note_data: ConsultationNoteCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.add")),
    ],
) -> dict[str, object]:
    parent_note = await db.get(ConsultationNote, note_id)
    if parent_note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note_not_found")
    if parent_note.status != "signed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="addendum_requires_signed_note",
        )
    visit = await db.get(OutpatientVisit, parent_note.visit_id)
    if visit is None or visit.status == "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="visit_not_available")
    addendum = ConsultationNote(
        visit_id=parent_note.visit_id,
        parent_note_id=parent_note.id,
        author_user_id=current.id,
        note_type="addendum",
        body=note_data.body,
    )
    db.add(addendum)
    await db.flush()
    db.add(
        _audit(
            request,
            action="clinical.consultation-note.addendum",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(addendum.id),
            resource_type="consultation_note",
            event_metadata={
                "visit_id": str(parent_note.visit_id),
                "parent_note_id": str(parent_note.id),
            },
        )
    )
    await db.commit()
    await db.refresh(addendum)
    return _consultation_note_payload(addendum)


@router.post("/doctors/visits/{visit_id}/complete")
async def complete_consultation(
    visit_id: UUID,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("clinical.consultation-notes-and-examination.approve")),
    ],
) -> dict[str, str]:
    visit = await db.get(OutpatientVisit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="visit_not_found")
    if visit.status != "queued" or visit.workflow_state != "consultation_in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="consultation_not_in_progress",
        )

    signed_consultation = await db.scalar(
        select(ConsultationNote.id).where(
            ConsultationNote.visit_id == visit_id,
            ConsultationNote.note_type == "consultation",
            ConsultationNote.status == "signed",
        )
    )
    if signed_consultation is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="signed_consultation_note_required",
        )
    draft_note = await db.scalar(
        select(ConsultationNote.id).where(
            ConsultationNote.visit_id == visit_id,
            ConsultationNote.status == "draft",
        )
    )
    if draft_note is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="unsigned_notes_remain",
        )

    completion = await db.execute(
        update(OutpatientVisit)
        .where(
            OutpatientVisit.id == visit_id,
            OutpatientVisit.status == "queued",
            OutpatientVisit.workflow_state == "consultation_in_progress",
        )
        .values(status="completed", workflow_state="completed")
    )
    if completion.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="consultation_not_in_progress",
        )
    db.add(
        _audit(
            request,
            action="clinical.consultation.complete",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit_id),
            resource_type="outpatient_visit",
        )
    )
    await db.commit()
    return {"workflow_state": "completed"}
