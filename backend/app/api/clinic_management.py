from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import DbSession, _audit, _is_superadmin, require_permission
from app.db.models import (
    AuditLog,
    Clinic,
    DoctorClinic,
    Facility,
    FacilityClinic,
    OutpatientVisit,
    Role,
    User,
    VisitType,
    clinic_visit_types,
)

router = APIRouter(prefix="/clinics", tags=["clinic management"])
DEFAULT_FACILITY_ID = 1


class FacilityCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Facility name must not be blank.")
        return normalized


class ClinicCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=30, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=2, max_length=150)
    sort_order: int = Field(default=0, ge=0)
    visit_type_ids: list[int] = Field(min_length=1)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Clinic name must not be blank.")
        return normalized


class ClinicUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    sort_order: int | None = Field(default=None, ge=0)
    is_deleted: bool | None = None
    visit_type_ids: list[int] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        if value is not None and not normalized:
            raise ValueError("Clinic name must not be blank.")
        return normalized or None


class VisitTypeCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    color_hex: str = Field(default="#F26B6B", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Visit type name must not be blank.")
        return normalized


class VisitTypeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: bool | None = None


class FacilityClinicUpdateRequest(BaseModel):
    is_enabled: bool
    is_unavailable: bool = False
    unavailable_reason: str | None = Field(default=None, max_length=255)
    unavailable_until: datetime | None = None

    @field_validator("unavailable_reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    @model_validator(mode="after")
    def validate_unavailability(self) -> "FacilityClinicUpdateRequest":
        if self.is_unavailable and not self.unavailable_reason:
            raise ValueError("A reason is required when a clinic is unavailable.")
        return self


class DoctorAssignmentRequest(BaseModel):
    user_id: UUID
    on_leave_from: date | None = None
    on_leave_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_leave_dates(self) -> "DoctorAssignmentRequest":
        if (
            self.on_leave_from is not None
            and self.on_leave_to is not None
            and self.on_leave_to < self.on_leave_from
        ):
            raise ValueError("Leave end date cannot be before leave start date.")
        return self


def _facility_id_for_user(user: User, requested_id: int | None) -> int:
    if user.facility_id is not None:
        if requested_id is not None and requested_id != user.facility_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="facility_access_denied",
            )
        return user.facility_id
    if _is_superadmin(user):
        return requested_id or DEFAULT_FACILITY_ID
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="facility_assignment_required",
    )


async def _active_visit_types(
    db: AsyncSession,
    clinic_ids: list[int],
) -> dict[int, list[dict[str, object]]]:
    result: dict[int, list[dict[str, object]]] = {clinic_id: [] for clinic_id in clinic_ids}
    if not clinic_ids:
        return result
    rows = (
        await db.execute(
            select(clinic_visit_types.c.clinic_id, VisitType)
            .join(VisitType, VisitType.id == clinic_visit_types.c.visit_type_id)
            .where(
                clinic_visit_types.c.clinic_id.in_(clinic_ids),
                VisitType.is_active.is_(True),
            )
            .order_by(VisitType.name)
        )
    ).all()
    for clinic_id, visit_type in rows:
        result[clinic_id].append(
            {
                "id": visit_type.id,
                "name": visit_type.name,
                "color_hex": visit_type.color_hex,
            }
        )
    return result


@router.get("/facilities")
async def list_facilities(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.view")),
    ],
) -> list[dict[str, object]]:
    statement = select(Facility).where(Facility.is_active.is_(True)).order_by(Facility.name)
    if not _is_superadmin(current):
        if current.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="facility_assignment_required",
            )
        statement = statement.where(Facility.id == current.facility_id)
    facilities = (await db.scalars(statement)).all()
    return [{"id": facility.id, "name": facility.name} for facility in facilities]


@router.post("/facilities", status_code=status.HTTP_201_CREATED)
async def create_facility(
    facility_data: FacilityCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> dict[str, object]:
    facility = Facility(name=facility_data.name, is_active=True)
    db.add(facility)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="facility_name_already_exists",
        ) from error
    db.add(
        _audit(
            request,
            action="configuration.clinic.facility.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(facility.id),
            resource_type="facility",
        )
    )
    await db.commit()
    return {"id": facility.id, "name": facility.name}


@router.get("/catalog")
async def list_clinic_catalog(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.view")),
    ],
) -> list[dict[str, object]]:
    clinics = (
        await db.scalars(select(Clinic).order_by(Clinic.sort_order, Clinic.name))
    ).all()
    visit_types = await _active_visit_types(db, [clinic.id for clinic in clinics])
    return [
        {
            "id": clinic.id,
            "code": clinic.code,
            "name": clinic.name,
            "sort_order": clinic.sort_order,
            "is_deleted": clinic.is_deleted,
            "visit_types": visit_types[clinic.id],
        }
        for clinic in clinics
    ]


@router.post("/catalog", status_code=status.HTTP_201_CREATED)
async def create_clinic(
    clinic_data: ClinicCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> dict[str, object]:
    visit_types = (
        await db.scalars(
            select(VisitType).where(
                VisitType.id.in_(clinic_data.visit_type_ids),
                VisitType.is_active.is_(True),
            )
        )
    ).all()
    if {visit_type.id for visit_type in visit_types} != set(clinic_data.visit_type_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="visit_type_not_found",
        )
    clinic = Clinic(
        code=clinic_data.code,
        name=clinic_data.name,
        sort_order=clinic_data.sort_order,
        created_by=current.id,
    )
    db.add(clinic)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clinic_code_or_name_already_exists",
        ) from error
    await db.execute(
        clinic_visit_types.insert(),
        [
            {"clinic_id": clinic.id, "visit_type_id": visit_type.id}
            for visit_type in visit_types
        ],
    )
    db.add(
        _audit(
            request,
            action="configuration.clinic.catalog.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(clinic.id),
            resource_type="clinic",
            event_metadata={"code": clinic.code, "visit_type_count": len(visit_types)},
        )
    )
    await db.commit()
    return {
        "id": clinic.id,
        "code": clinic.code,
        "name": clinic.name,
        "sort_order": clinic.sort_order,
        "is_deleted": clinic.is_deleted,
        "visit_types": [
            {"id": visit_type.id, "name": visit_type.name, "color_hex": visit_type.color_hex}
            for visit_type in visit_types
        ],
    }


@router.post("/visit-types", status_code=status.HTTP_201_CREATED)
async def create_visit_type(
    visit_type_data: VisitTypeCreateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> dict[str, object]:
    visit_type = VisitType(
        name=visit_type_data.name,
        color_hex=visit_type_data.color_hex.upper(),
    )
    db.add(visit_type)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_type_name_already_exists",
        ) from error
    db.add(
        _audit(
            request,
            action="configuration.clinic.visit-type.create",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit_type.id),
            resource_type="visit_type",
        )
    )
    await db.commit()
    return {"id": visit_type.id, "name": visit_type.name, "color_hex": visit_type.color_hex}


@router.get("/visit-types")
async def list_visit_types(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.view")),
    ],
) -> list[dict[str, object]]:
    visit_types = (
        await db.scalars(select(VisitType).order_by(VisitType.name))
    ).all()
    return [
        {
            "id": visit_type.id,
            "name": visit_type.name,
            "color_hex": visit_type.color_hex,
            "is_active": visit_type.is_active,
        }
        for visit_type in visit_types
    ]


@router.patch("/visit-types/{visit_type_id}")
async def update_visit_type(
    visit_type_id: int,
    visit_type_data: VisitTypeUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> dict[str, object]:
    visit_type = await db.get(VisitType, visit_type_id)
    if visit_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="visit_type_not_found",
        )
    fields = visit_type_data.model_fields_set
    if "name" in fields and visit_type_data.name is not None:
        visit_type.name = visit_type_data.name.strip()
    if "color_hex" in fields and visit_type_data.color_hex is not None:
        visit_type.color_hex = visit_type_data.color_hex.upper()
    if "is_active" in fields and visit_type_data.is_active is not None:
        visit_type.is_active = visit_type_data.is_active
    db.add(
        _audit(
            request,
            action="configuration.clinic.visit-type.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(visit_type.id),
            resource_type="visit_type",
            event_metadata={"updated_fields": sorted(fields)},
        )
    )
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="visit_type_name_already_exists",
        ) from error
    return {
        "id": visit_type.id,
        "name": visit_type.name,
        "color_hex": visit_type.color_hex,
        "is_active": visit_type.is_active,
    }


@router.patch("/catalog/{clinic_id}")
async def update_clinic(
    clinic_id: int,
    clinic_data: ClinicUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> dict[str, object]:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clinic_not_found")
    fields = clinic_data.model_fields_set
    if "name" in fields and clinic_data.name is not None:
        clinic.name = clinic_data.name
    if "sort_order" in fields and clinic_data.sort_order is not None:
        clinic.sort_order = clinic_data.sort_order
    if "is_deleted" in fields and clinic_data.is_deleted is not None:
        clinic.is_deleted = clinic_data.is_deleted
    if "visit_type_ids" in fields and clinic_data.visit_type_ids is not None:
        visit_types = (
            await db.scalars(
                select(VisitType).where(
                    VisitType.id.in_(clinic_data.visit_type_ids),
                    VisitType.is_active.is_(True),
                )
            )
        ).all()
        if {visit_type.id for visit_type in visit_types} != set(clinic_data.visit_type_ids):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="visit_type_not_found",
            )
        await db.execute(
            clinic_visit_types.delete().where(clinic_visit_types.c.clinic_id == clinic_id)
        )
        if visit_types:
            await db.execute(
                clinic_visit_types.insert(),
                [
                    {"clinic_id": clinic.id, "visit_type_id": visit_type.id}
                    for visit_type in visit_types
                ],
            )
    db.add(
        _audit(
            request,
            action="configuration.clinic.catalog.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(clinic.id),
            resource_type="clinic",
            event_metadata={"updated_fields": sorted(fields)},
        )
    )
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clinic_name_already_exists",
        ) from error
    visit_types_by_clinic = await _active_visit_types(db, [clinic.id])
    return {
        "id": clinic.id,
        "code": clinic.code,
        "name": clinic.name,
        "sort_order": clinic.sort_order,
        "is_deleted": clinic.is_deleted,
        "visit_types": visit_types_by_clinic[clinic.id],
    }


@router.delete("/catalog/{clinic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unused_clinic(
    clinic_id: int,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.clinic-catalog.manage")),
    ],
) -> None:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clinic_not_found")
    if await db.scalar(
        select(OutpatientVisit.id).where(OutpatientVisit.clinic_id == clinic.id).limit(1)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="clinic_has_visits_deactivate_instead",
        )
    await db.execute(
        clinic_visit_types.delete().where(clinic_visit_types.c.clinic_id == clinic.id)
    )
    await db.execute(
        DoctorClinic.__table__.delete().where(DoctorClinic.clinic_id == clinic.id)
    )
    await db.execute(
        FacilityClinic.__table__.delete().where(FacilityClinic.clinic_id == clinic.id)
    )
    await db.delete(clinic)
    db.add(
        _audit(
            request,
            action="configuration.clinic.catalog.delete",
            outcome="success",
            actor_user_id=current.id,
            resource_id=str(clinic.id),
            resource_type="clinic",
        )
    )
    await db.commit()


@router.get("/available")
async def list_available_clinics(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("front-office.open-outpatient-visit.view")),
    ],
    facility_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, object]:
    selected_facility_id = _facility_id_for_user(current, facility_id)
    facility = await db.get(Facility, selected_facility_id)
    if facility is None or not facility.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="facility_not_found",
        )
    rows = (
        await db.execute(
            select(Clinic, FacilityClinic)
            .join(FacilityClinic, FacilityClinic.clinic_id == Clinic.id)
            .where(
                FacilityClinic.facility_id == selected_facility_id,
                FacilityClinic.is_enabled.is_(True),
                Clinic.is_deleted.is_(False),
                or_(
                    FacilityClinic.is_unavailable.is_(False),
                    FacilityClinic.unavailable_until <= func.now(),
                ),
            )
            .order_by(Clinic.sort_order, Clinic.name)
        )
    ).all()
    clinic_ids = [clinic.id for clinic, _ in rows]
    visit_types = await _active_visit_types(db, clinic_ids)
    today = date.today()
    doctor_rows = (
        await db.execute(
            select(DoctorClinic.clinic_id, func.count())
            .join(User, User.id == DoctorClinic.user_id)
            .where(
                DoctorClinic.facility_id == selected_facility_id,
                DoctorClinic.is_active.is_(True),
                User.is_active.is_(True),
                or_(
                    DoctorClinic.on_leave_from.is_(None),
                    DoctorClinic.on_leave_from > today,
                    and_(
                        DoctorClinic.on_leave_to.is_not(None),
                        DoctorClinic.on_leave_to < today,
                    ),
                ),
            )
            .group_by(DoctorClinic.clinic_id)
        )
    ).all()
    doctor_counts = {clinic_id: count for clinic_id, count in doctor_rows}
    return {
        "facility_id": selected_facility_id,
        "facility_name": facility.name,
        "items": [
            {
                "id": clinic.id,
                "code": clinic.code,
                "name": clinic.name,
                "visit_types": visit_types[clinic.id],
                "has_available_doctor": doctor_counts.get(clinic.id, 0) > 0,
            }
            for clinic, _ in rows
            if visit_types[clinic.id]
        ],
    }


@router.get("/admin")
async def list_facility_clinics(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.view")),
    ],
    facility_id: Annotated[int | None, Query(ge=1)] = None,
) -> dict[str, object]:
    selected_facility_id = _facility_id_for_user(current, facility_id)
    facility = await db.get(Facility, selected_facility_id)
    if facility is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="facility_not_found")
    rows = (
        await db.execute(
            select(Clinic, FacilityClinic)
            .outerjoin(
                FacilityClinic,
                and_(
                    FacilityClinic.clinic_id == Clinic.id,
                    FacilityClinic.facility_id == selected_facility_id,
                ),
            )
            .order_by(Clinic.sort_order, Clinic.name)
        )
    ).all()
    clinic_ids = [clinic.id for clinic, _ in rows]
    visit_types = await _active_visit_types(db, clinic_ids)
    assigned_doctors = (
        await db.execute(
            select(DoctorClinic.clinic_id, User.id, User.username, DoctorClinic.is_active)
            .join(User, User.id == DoctorClinic.user_id)
            .where(
                DoctorClinic.facility_id == selected_facility_id,
                DoctorClinic.clinic_id.in_(clinic_ids or [-1]),
            )
            .order_by(User.username)
        )
    ).all()
    doctors_by_clinic: dict[int, list[dict[str, object]]] = {
        clinic_id: [] for clinic_id in clinic_ids
    }
    for clinic_id, user_id, username, is_active in assigned_doctors:
        doctors_by_clinic[clinic_id].append(
            {
                "id": str(user_id),
                "username": username,
                "is_active": is_active,
            }
        )
    return {
        "facility_id": selected_facility_id,
        "facility_name": facility.name,
        "items": [
            {
                "id": clinic.id,
                "code": clinic.code,
                "name": clinic.name,
                "sort_order": clinic.sort_order,
                "is_deleted": clinic.is_deleted,
                "visit_types": visit_types[clinic.id],
                "is_enabled": facility_clinic.is_enabled if facility_clinic else False,
                "is_unavailable": facility_clinic.is_unavailable if facility_clinic else False,
                "unavailable_reason": (
                    facility_clinic.unavailable_reason if facility_clinic else None
                ),
                "unavailable_until": (
                    facility_clinic.unavailable_until.isoformat()
                    if facility_clinic and facility_clinic.unavailable_until
                    else None
                ),
                "has_available_doctor": any(
                    doctor["is_active"] for doctor in doctors_by_clinic[clinic.id]
                ),
                "doctors": doctors_by_clinic[clinic.id],
            }
            for clinic, facility_clinic in rows
        ],
    }


@router.get("/facilities/{facility_id}/doctors")
async def list_facility_doctors(
    facility_id: int,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.view")),
    ],
) -> list[dict[str, object]]:
    _facility_id_for_user(current, facility_id)
    doctors = (
        await db.execute(
            select(User.id, User.username, User.email)
            .join(User.roles)
            .where(
                User.facility_id == facility_id,
                User.is_active.is_(True),
                func.lower(Role.name) == "doctor / medical officer",
            )
            .order_by(User.username)
        )
    ).all()
    return [
        {"id": str(user_id), "username": username, "email": email}
        for user_id, username, email in doctors
    ]


@router.get("/audit")
async def list_clinic_audit(
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.view")),
    ],
    facility_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, object]]:
    selected_facility_id = _facility_id_for_user(current, facility_id)
    statement = (
        select(AuditLog, User.username)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.action.like("configuration.clinic.%"))
        .order_by(AuditLog.id.desc())
        .limit(limit)
    )
    if not _is_superadmin(current):
        statement = statement.where(
            AuditLog.resource_id.like(f"{selected_facility_id}:%")
        )
    rows = (await db.execute(statement)).all()
    return [
        {
            "id": audit.id,
            "occurred_at": audit.occurred_at.isoformat(),
            "actor_username": username,
            "action": audit.action,
            "resource_type": audit.resource_type,
            "resource_id": audit.resource_id,
            "outcome": audit.outcome,
        }
        for audit, username in rows
    ]


@router.patch("/facilities/{facility_id}/clinics/{clinic_id}")
async def update_facility_clinic(
    facility_id: int,
    clinic_id: int,
    clinic_data: FacilityClinicUpdateRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.manage")),
    ],
) -> dict[str, object]:
    _facility_id_for_user(current, facility_id)
    clinic = await db.get(Clinic, clinic_id)
    facility = await db.get(Facility, facility_id)
    if clinic is None or clinic.is_deleted or facility is None or not facility.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="clinic_or_facility_not_found",
        )
    assignment = await db.get(FacilityClinic, (facility_id, clinic_id))
    if assignment is None:
        assignment = FacilityClinic(facility_id=facility_id, clinic_id=clinic_id)
        db.add(assignment)
    assignment.is_enabled = clinic_data.is_enabled
    assignment.is_unavailable = clinic_data.is_unavailable
    assignment.unavailable_reason = (
        clinic_data.unavailable_reason if clinic_data.is_unavailable else None
    )
    assignment.unavailable_from = datetime.now(UTC) if clinic_data.is_unavailable else None
    assignment.unavailable_until = (
        clinic_data.unavailable_until if clinic_data.is_unavailable else None
    )
    assignment.updated_by = current.id
    db.add(
        _audit(
            request,
            action="configuration.clinic.facility.update",
            outcome="success",
            actor_user_id=current.id,
            resource_id=f"{facility_id}:{clinic_id}",
            resource_type="facility_clinic",
            event_metadata={
                "is_enabled": assignment.is_enabled,
                "is_unavailable": assignment.is_unavailable,
            },
        )
    )
    await db.commit()
    return {
        "facility_id": facility_id,
        "clinic_id": clinic_id,
        "is_enabled": assignment.is_enabled,
        "is_unavailable": assignment.is_unavailable,
        "unavailable_reason": assignment.unavailable_reason,
        "unavailable_until": (
            assignment.unavailable_until.isoformat() if assignment.unavailable_until else None
        ),
    }


@router.post("/facilities/{facility_id}/clinics/{clinic_id}/doctors")
async def assign_doctor_to_clinic(
    facility_id: int,
    clinic_id: int,
    assignment_data: DoctorAssignmentRequest,
    request: Request,
    db: DbSession,
    current: Annotated[
        User,
        Depends(require_permission("configuration.facility-clinics.manage")),
    ],
) -> dict[str, object]:
    _facility_id_for_user(current, facility_id)
    doctor = await db.scalar(
        select(User)
        .join(User.roles)
        .where(
            User.id == assignment_data.user_id,
            User.is_active.is_(True),
            User.facility_id == facility_id,
            func.lower(Role.name) == "doctor / medical officer",
        )
    )
    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="active_facility_doctor_required",
        )
    if await db.get(Clinic, clinic_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clinic_not_found")
    assignment = await db.get(DoctorClinic, (doctor.id, facility_id, clinic_id))
    if assignment is None:
        assignment = DoctorClinic(
            user_id=doctor.id,
            facility_id=facility_id,
            clinic_id=clinic_id,
        )
        db.add(assignment)
    assignment.on_leave_from = assignment_data.on_leave_from
    assignment.on_leave_to = assignment_data.on_leave_to
    assignment.is_active = assignment_data.is_active
    db.add(
        _audit(
            request,
            action="configuration.clinic.doctor.assign",
            outcome="success",
            actor_user_id=current.id,
            resource_id=f"{facility_id}:{clinic_id}:{doctor.id}",
            resource_type="doctor_clinic",
        )
    )
    await db.commit()
    return {
        "facility_id": facility_id,
        "clinic_id": clinic_id,
        "user_id": str(doctor.id),
        "username": doctor.username,
        "is_active": assignment.is_active,
        "on_leave_from": assignment.on_leave_from.isoformat() if assignment.on_leave_from else None,
        "on_leave_to": assignment.on_leave_to.isoformat() if assignment.on_leave_to else None,
    }
