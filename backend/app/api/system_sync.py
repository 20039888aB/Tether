import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import (
    DbSession,
    _effective_permission_keys,
    _is_superadmin,
    _requires_mfa,
    get_auth_session,
)
from app.db.models import AuthSession, SystemEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system synchronization"])

EVENT_CATEGORY_PERMISSIONS = {
    "patient_access": (
        "front-office.patient-registration-and-biodata.view",
        "front-office.search-existing-patient-records.view",
        "front-office.open-outpatient-visit.view",
        "medical-records.patient-file-management.view",
        "nursing.triage-and-vital-signs.view",
        "clinical.consultation-notes-and-examination.view",
    ),
    "nursing": (
        "nursing.triage-and-vital-signs.view",
        "clinical.consultation-notes-and-examination.view",
        "front-office.open-outpatient-visit.view",
    ),
    "clinical": (
        "clinical.consultation-notes-and-examination.view",
        "medical-records.patient-file-management.view",
    ),
    "admissions": (
        "clinical.admission-transfer-and-discharge-orders.view",
        "nursing.ward-observations-and-fluid-charts.view",
    ),
    "laboratory": (
        "laboratory.laboratory-requests-and-worklists.view",
        "radiology.imaging-requests-and-schedule.view",
        "clinical.consultation-notes-and-examination.view",
    ),
    "pharmacy": (
        "pharmacy.view-prescriptions.view",
        "pharmacy.medication-stock-and-batch-records.view",
        "clinical.medication-prescriptions.view",
    ),
    "billing": (
        "billing.view-patient-charges-and-account.view",
        "cash-office.receive-cash-m-pesa-card-payments.view",
        "accounts.view-financial-transactions-and-reports.view",
    ),
    "messaging": ("communications.messaging.view",),
    "identity": (
        "identity.users.read",
        "identity.users.manage",
        "identity.roles.read",
        "identity.roles.manage",
    ),
    "configuration": (
        "configuration.clinic-catalog.view",
        "configuration.clinic-catalog.manage",
        "configuration.facility-clinics.view",
        "configuration.facility-clinics.manage",
    ),
}


@router.get("/sync")
async def synchronize_system(
    db: DbSession,
    auth_session: Annotated[AuthSession, Depends(get_auth_session)],
    after_id: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, object]:
    user = auth_session.user
    if _requires_mfa(user) and user.totp_enabled_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="mfa_setup_required",
        )

    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        logger.exception("System synchronization database check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from error

    latest_id = await db.scalar(select(func.max(SystemEvent.id))) or 0
    if after_id is None:
        records: list[SystemEvent] = []
        next_cursor = latest_id
    else:
        records = (
            await db.scalars(
                select(SystemEvent)
                .where(SystemEvent.id > after_id)
                .order_by(SystemEvent.id)
                .limit(limit)
            )
        ).all()
        next_cursor = records[-1].id if records else after_id

    permissions = _effective_permission_keys(user)
    visible_events = [
        {
            "id": event.id,
            "category": event.category,
            "action": event.action,
            "occurred_at": event.occurred_at.isoformat(),
        }
        for event in records
        if _is_superadmin(user)
        or permissions.intersection(EVENT_CATEGORY_PERMISSIONS[event.category])
    ]
    return {
        "status": "ready",
        "checked_at": datetime.now(UTC).isoformat(),
        "cursor": next_cursor,
        "events": visible_events,
    }
