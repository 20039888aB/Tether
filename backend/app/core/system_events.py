from uuid import UUID

from app.db.models import AuditLog, SystemEvent

_EVENT_PREFIXES = (
    ("configuration.", "configuration"),
    ("clinical.admission-", "admissions"),
    ("admissions.", "admissions"),
    ("inpatient.", "admissions"),
    ("laboratory.", "laboratory"),
    ("radiology.", "laboratory"),
    ("pharmacy.", "pharmacy"),
    ("billing.", "billing"),
    ("cash-office.", "billing"),
    ("accounts.", "billing"),
    ("messaging.", "messaging"),
    ("communications.", "messaging"),
    ("nursing.", "nursing"),
    ("clinical.", "clinical"),
    ("front-office.", "patient_access"),
    ("patient.", "patient_access"),
    ("patient-services.", "patient_access"),
    ("outpatient.", "patient_access"),
    ("medical-records.", "patient_access"),
    ("identity.", "identity"),
)


def attach_operation_event(
    audit_log: AuditLog,
    *,
    action: str,
    outcome: str,
    actor_user_id: UUID | None,
    resource_id: str | None,
    resource_type: str,
) -> None:
    if outcome != "success" or action.endswith((".read", ".search")):
        return

    category = next(
        (category for prefix, category in _EVENT_PREFIXES if action.startswith(prefix)),
        None,
    )
    if category is None:
        return

    audit_log.operation_event = SystemEvent(
        actor_user_id=actor_user_id,
        category=category,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
