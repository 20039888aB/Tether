import re
from collections.abc import Iterable
from dataclasses import dataclass

PERMISSION_ACTIONS = ("view", "add", "edit", "approve", "delete", "export", "print")


@dataclass(frozen=True)
class MatrixEntry:
    department: str
    role: str
    function: str
    actions: tuple[str, ...]
    notes: str = ""


MATRIX_ENTRIES = (
    MatrixEntry(
        "Front Office",
        "Receptionist",
        "Patient registration and biodata",
        ("view", "add", "edit"),
        "Edits to key identifiers should be logged.",
    ),
    MatrixEntry(
        "Front Office",
        "Receptionist",
        "Search existing patient records",
        ("view",),
        "Use patient identifiers to avoid duplicate records.",
    ),
    MatrixEntry(
        "Front Office",
        "Receptionist",
        "Open outpatient visit",
        ("view", "add", "edit"),
        "Cannot alter clinical notes.",
    ),
    MatrixEntry("Front Office", "Receptionist", "Appointment scheduling", ("view", "add", "edit")),
    MatrixEntry(
        "Medical Records",
        "Medical Records Officer",
        "Patient file management",
        ("view", "add", "edit"),
        "Maintain confidentiality and record access logs.",
    ),
    MatrixEntry(
        "Medical Records",
        "Medical Records Officer",
        "Upload/scan clinical documents",
        ("view", "add", "edit"),
        "Do not overwrite signed clinical records.",
    ),
    MatrixEntry(
        "Medical Records",
        "Medical Records Officer",
        "Medical statistics and records reports",
        ("view", "add"),
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Consultation notes and examination",
        ("view", "add", "edit", "approve"),
        "Sign/lock notes after completion; amendments should be traceable.",
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Diagnosis and ICD coding",
        ("view", "add", "edit", "approve"),
        "Clinical responsibility rests with the treating clinician.",
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Laboratory and imaging requests",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Medication prescriptions",
        ("view", "add", "edit", "approve"),
        "Prescription signing/authorization required.",
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Treatment plan and clinical orders",
        ("view", "add", "edit", "approve"),
    ),
    MatrixEntry(
        "Clinical",
        "Doctor / Medical Officer",
        "Admission, transfer and discharge orders",
        ("view", "add", "edit", "approve"),
        "Discharge approval restricted to authorized clinicians.",
    ),
    MatrixEntry(
        "Nursing",
        "Nurse",
        "Triage and vital signs",
        ("view", "add", "edit"),
        "Corrections must retain original value and audit history.",
    ),
    MatrixEntry(
        "Nursing",
        "Nurse",
        "Nursing notes and care plans",
        ("view", "add", "edit"),
        "Signed notes should not be silently changed.",
    ),
    MatrixEntry(
        "Nursing",
        "Nurse",
        "Medication administration record",
        ("view", "add", "edit"),
        "Record actual administration and omissions.",
    ),
    MatrixEntry("Nursing", "Nurse", "Ward observations and fluid charts", ("view", "add", "edit")),
    MatrixEntry(
        "Nursing",
        "Ward In-Charge / Matron",
        "Nursing documentation review",
        ("view", "add", "edit", "approve"),
        "Approval/review should be attributable to reviewer.",
    ),
    MatrixEntry(
        "Laboratory", "Laboratory Technologist", "Laboratory requests and worklists", ("view",)
    ),
    MatrixEntry(
        "Laboratory",
        "Laboratory Technologist",
        "Sample collection and processing",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Laboratory", "Laboratory Technologist", "Enter laboratory results", ("view", "add", "edit")
    ),
    MatrixEntry(
        "Laboratory",
        "Senior Lab Technologist",
        "Validate and release laboratory results",
        ("view", "edit", "approve"),
        "Prefer a second-person validation workflow for critical results.",
    ),
    MatrixEntry(
        "Radiology", "Radiology Officer", "Imaging requests and schedule", ("view", "add", "edit")
    ),
    MatrixEntry(
        "Radiology", "Radiology Officer", "Upload images and reports", ("view", "add", "edit")
    ),
    MatrixEntry(
        "Radiology",
        "Radiologist / Authorized Reviewer",
        "Validate and release imaging report",
        ("view", "edit", "approve"),
    ),
    MatrixEntry("Pharmacy", "Pharmacist / Pharmacy Technician", "View prescriptions", ("view",)),
    MatrixEntry(
        "Pharmacy",
        "Pharmacist / Pharmacy Technician",
        "Dispense medication",
        ("view", "add", "edit"),
        "Dispensing should be linked to a valid prescription.",
    ),
    MatrixEntry(
        "Pharmacy",
        "Pharmacist",
        "Medication stock and batch records",
        ("view", "add", "edit", "approve"),
        "Approval for stock adjustments should be restricted.",
    ),
    MatrixEntry(
        "Pharmacy",
        "Pharmacist-in-Charge",
        "Approve stock adjustments / returns",
        ("view", "edit", "approve"),
        "Record reason and supporting evidence.",
    ),
    MatrixEntry(
        "Theatre", "Theatre Officer / Nurse", "Theatre booking and list", ("view", "add", "edit")
    ),
    MatrixEntry(
        "Theatre",
        "Surgeon / Anaesthetist",
        "Operation and anaesthesia notes",
        ("view", "add", "edit", "approve"),
        "Each clinician signs their own documentation.",
    ),
    MatrixEntry(
        "Theatre",
        "Theatre Officer",
        "Theatre consumables used",
        ("view", "add", "edit"),
        "Post usage to patient account and inventory.",
    ),
    MatrixEntry(
        "Billing",
        "Billing Officer",
        "View patient charges and account",
        ("view",),
        "Access limited to billing information needed for work.",
    ),
    MatrixEntry(
        "Billing",
        "Billing Officer",
        "Generate invoices and post charges",
        ("view", "add", "edit"),
        "Charges should link to an order, service or approved tariff.",
    ),
    MatrixEntry(
        "Cash Office",
        "Cashier",
        "Receive cash / M-Pesa / card payments",
        ("view", "add"),
        "Do not permit cashier to approve own refunds.",
    ),
    MatrixEntry(
        "Cash Office",
        "Cashier",
        "Generate receipts",
        ("view", "add"),
        "Receipt numbering should be system controlled.",
    ),
    MatrixEntry(
        "Billing",
        "Billing Supervisor",
        "Approve discounts, reversals and bill adjustments",
        ("view", "edit", "approve"),
        "Use limits and mandatory reason codes.",
    ),
    MatrixEntry(
        "Insurance / SHA",
        "SHA / Insurance Officer",
        "Verify eligibility and coverage",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Insurance / SHA",
        "SHA / Insurance Officer",
        "Create and submit preauthorizations / claims",
        ("view", "add", "edit"),
        "Submission should retain attachments and status history.",
    ),
    MatrixEntry(
        "Insurance / SHA",
        "SHA / Insurance Officer",
        "Upload claim supporting documents",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Insurance / SHA",
        "Claims Supervisor",
        "Review and approve claims for submission",
        ("view", "edit", "approve"),
        "Where possible, separate preparation from approval.",
    ),
    MatrixEntry("Accounts", "Accountant", "View financial transactions and reports", ("view",)),
    MatrixEntry(
        "Accounts",
        "Accountant",
        "Reconcile payments and insurer remittances",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Accounts",
        "Finance Manager",
        "Approve refunds and credit notes",
        ("view", "edit", "approve"),
        "Require supporting documents and independent approval.",
    ),
    MatrixEntry(
        "Administration",
        "Hospital Administrator",
        "Operational dashboards and reports",
        ("view",),
        "Access to identifiable clinical data only when necessary.",
    ),
    MatrixEntry(
        "Administration",
        "Hospital Administrator",
        "Approve operational requests",
        ("view", "edit", "approve"),
        "Define approval limits in facility policy.",
    ),
    MatrixEntry(
        "Human Resources",
        "HR Officer",
        "Staff records and employment details",
        ("view", "add", "edit"),
        "Restrict access to HR-sensitive information.",
    ),
    MatrixEntry(
        "Human Resources", "HR Manager", "Approve leave and HR actions", ("view", "edit", "approve")
    ),
    MatrixEntry(
        "Stores / Procurement",
        "Storekeeper",
        "Receive, issue and transfer stock",
        ("view", "add", "edit"),
        "Maintain batch, expiry and stock movement history.",
    ),
    MatrixEntry(
        "Stores / Procurement",
        "Procurement Officer",
        "Suppliers and purchase orders",
        ("view", "add", "edit"),
    ),
    MatrixEntry(
        "Stores / Procurement",
        "Procurement Manager",
        "Approve purchase orders",
        ("view", "edit", "approve"),
        "Approval limits and segregation of duties apply.",
    ),
    MatrixEntry(
        "Quality / Audit",
        "Quality Assurance Officer",
        "Quality indicators and incident reports",
        ("view", "add", "edit"),
        "Limit access to identifiable patient details.",
    ),
    MatrixEntry(
        "Quality / Audit",
        "Internal Auditor",
        "Read-only audit trail and transaction reports",
        ("view",),
        "Auditors should not edit operational transactions.",
    ),
    MatrixEntry(
        "IT",
        "System Administrator",
        "Create and deactivate user accounts",
        ("view", "add", "edit", "approve"),
        "Use named accounts; avoid shared logins.",
    ),
    MatrixEntry(
        "IT",
        "System Administrator",
        "Assign roles and permissions",
        ("view", "add", "edit", "approve"),
        "Privileged access should be restricted and reviewed.",
    ),
    MatrixEntry(
        "IT",
        "System Administrator",
        "System configuration and backups",
        ("view", "add", "edit", "approve"),
        "Log privileged actions; test backup restoration.",
    ),
    MatrixEntry(
        "Patient Services",
        "Patient Portal User",
        "View own appointments, bills and selected results",
        ("view",),
        "Patient must only access their own records.",
    ),
    MatrixEntry(
        "Patient Services",
        "Patient Portal User",
        "Request appointments / update contact details",
        ("view", "add", "edit"),
        "Changes to identity details may require staff verification.",
    ),
)


ROLE_DESCRIPTIONS = {
    "SuperAdmin": (
        "Full access to every registered permission. Reserved for the initial system owner."
    ),
    "Receptionist": "Patient registration, visit creation, appointments and patient direction.",
    "Medical Records Officer": "Patient file management, document scanning and records reporting.",
    "Doctor / Medical Officer": (
        "Consultation, diagnosis, investigations, treatment and clinical decisions."
    ),
    "Nurse": "Triage, vital signs, nursing notes, medication administration and monitoring.",
    "Ward In-Charge / Matron": "Nursing supervision and review of ward documentation.",
    "Laboratory Technologist": "Sample processing and entry of laboratory results.",
    "Senior Lab Technologist": "Validation and release of laboratory results.",
    "Radiology Officer": "Imaging workflow, image/report uploads and scheduling.",
    "Radiologist / Authorized Reviewer": "Review, validation and release of imaging reports.",
    "Pharmacist / Pharmacy Technician": "Prescription processing, dispensing and stock management.",
    "Pharmacist": "Medication stock, batch records and pharmacy workflow.",
    "Pharmacist-in-Charge": "Approval of stock adjustments and returns.",
    "Theatre Officer / Nurse": "Theatre scheduling, consumables and procedure workflow.",
    "Surgeon / Anaesthetist": "Surgical and anaesthesia documentation and clinical authorization.",
    "Theatre Officer": "Theatre consumables and patient-account posting.",
    "Billing Officer": "Patient invoices, charge posting and account review.",
    "Cashier": "Payment collection and receipt generation.",
    "Billing Supervisor": "Approval of discounts, reversals and bill adjustments.",
    "SHA / Insurance Officer": "Eligibility checks, preauthorization, claims and follow-up.",
    "Claims Supervisor": "Review and approval of claims for submission.",
    "Accountant": "Reconciliation, financial reporting and remittance tracking.",
    "Finance Manager": "Approval of refunds and credit notes.",
    "Hospital Administrator": "Operational oversight, approvals and performance monitoring.",
    "HR Officer": "Staff records and employment details.",
    "HR Manager": "Approval of leave and HR actions.",
    "Storekeeper": "Inventory movements, receiving, issuing and transfers.",
    "Procurement Officer": "Suppliers and purchase orders.",
    "Procurement Manager": "Approval of purchase orders.",
    "Quality Assurance Officer": "Quality monitoring and incident reporting.",
    "Internal Auditor": "Independent read-only access to audit and transaction reports.",
    "System Administrator": "User accounts, access control, configuration and backups.",
    "Patient Portal User": (
        "Access limited to the patient's own appointments, bills and selected information."
    ),
}


CORE_PERMISSIONS = {
    "identity.users.read": "Read user accounts.",
    "identity.users.manage": "Create users, assign roles, and activate or deactivate accounts.",
    "identity.roles.read": "Read roles and the permission catalog.",
    "identity.roles.manage": "Create roles and assign permissions to roles.",
    "configuration.clinic-catalog.view": "Read the global clinic and visit-type catalog.",
    "configuration.clinic-catalog.manage": "Create and edit the global clinic catalog.",
    "configuration.facility-clinics.view": "Read clinic availability for the assigned facility.",
    "configuration.facility-clinics.manage": (
        "Enable, disable, schedule availability, and assign doctors to facility clinics."
    ),
}

SEPARATION_OF_DUTIES_RULES = {
    "cashier_refund_approval": frozenset(
        {
            "cash-office.receive-cash-m-pesa-card-payments.add",
            "accounts.approve-refunds-and-credit-notes.approve",
        }
    ),
}


def _slug(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def permission_catalog() -> dict[str, str]:
    catalog = dict(CORE_PERMISSIONS)
    for entry in MATRIX_ENTRIES:
        for action in PERMISSION_ACTIONS:
            key = f"{_slug(entry.department)}.{_slug(entry.function)}.{action}"
            description = f"{entry.department} - {entry.function}: {action.title()}."
            if entry.notes:
                description = f"{description} {entry.notes}"
            if action == "delete":
                description = f"{description} Permanent deletion is policy-restricted."
            catalog[key] = description
    return catalog


def separation_of_duties_conflict(permission_keys: Iterable[str]) -> str | None:
    assigned_permissions = set(permission_keys)
    return next(
        (
            rule_name
            for rule_name, required_permissions in SEPARATION_OF_DUTIES_RULES.items()
            if required_permissions.issubset(assigned_permissions)
        ),
        None,
    )


def default_role_permissions() -> dict[str, set[str]]:
    grants = {role: set() for role in ROLE_DESCRIPTIONS}
    for entry in MATRIX_ENTRIES:
        for action in entry.actions:
            grants[entry.role].add(f"{_slug(entry.department)}.{_slug(entry.function)}.{action}")
    grants["System Administrator"].update(CORE_PERMISSIONS)
    grants["System Administrator"].discard("configuration.clinic-catalog.view")
    grants["System Administrator"].discard("configuration.clinic-catalog.manage")
    grants["System Administrator"].add(
        "quality-audit.read-only-audit-trail-and-transaction-reports.view"
    )
    grants["Hospital Administrator"].update(
        {
            "configuration.facility-clinics.view",
            "configuration.facility-clinics.manage",
        }
    )
    grants["SuperAdmin"] = set(permission_catalog())
    return grants
