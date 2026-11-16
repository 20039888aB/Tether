import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.auth import DbSession, _audit, require_permission
from app.db.models import OutpatientVisit, Patient, User

router = APIRouter(tags=["patient access"])


class PatientCreateRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    sex_at_birth: Literal["female", "male", "intersex", "unknown"] | None = None
    phone_number: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("first_name", "middle_name", "last_name")
    @classmethod
    def normalize_names(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        if not normalized and value is not None:
            raise ValueError("Name fields must not be blank.")
        return normalized or None

    @field_validator("phone_number")
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

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return value


class PatientUpdateRequest(PatientCreateRequest):
    pass


class OutpatientVisitCreateRequest(BaseModel):
    patient_id: UUID
    clinic: str = Field(min_length=1, max_length=128)
    visit_type: str = Field(min_length=1, max_length=64)

    @field_validator("clinic", "visit_type")
    @classmethod
    def normalize_nonblank_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("This field must not be blank.")
        return normalized


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
        "created_at": visit.created_at.isoformat() if visit.created_at else None,
    }


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


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
        patient_number=f"TTH-{patient_id.hex.upper()}",
        first_name=patient_data.first_name,
        middle_name=patient_data.middle_name,
        last_name=patient_data.last_name,
        date_of_birth=patient_data.date_of_birth,
        sex_at_birth=patient_data.sex_at_birth,
        phone_number=patient_data.phone_number,
        email=patient_data.email,
        address=patient_data.address,
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

    visit_id = uuid4()
    visit = OutpatientVisit(
        id=visit_id,
        patient_id=patient.id,
        visit_number=f"OPD-{visit_id.hex.upper()}",
        clinic=visit_data.clinic,
        visit_type=visit_data.visit_type,
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

    patient.first_name = patient_data.first_name
    patient.middle_name = patient_data.middle_name
    patient.last_name = patient_data.last_name
    patient.date_of_birth = patient_data.date_of_birth
    patient.sex_at_birth = patient_data.sex_at_birth
    patient.phone_number = patient_data.phone_number
    patient.email = patient_data.email
    patient.address = patient_data.address
    patient.updated_by = current.id
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
