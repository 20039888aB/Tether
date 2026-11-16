from app.core.rbac import default_role_permissions, permission_catalog


def test_workbook_role_defaults_grant_only_defined_actions() -> None:
    grants = default_role_permissions()
    permissions = permission_catalog()
    receptionist = grants["Receptionist"]

    assert receptionist == {
        "front-office.patient-registration-and-biodata.view",
        "front-office.patient-registration-and-biodata.add",
        "front-office.patient-registration-and-biodata.edit",
        "front-office.search-existing-patient-records.view",
        "front-office.open-outpatient-visit.view",
        "front-office.open-outpatient-visit.add",
        "front-office.open-outpatient-visit.edit",
        "front-office.appointment-scheduling.view",
        "front-office.appointment-scheduling.add",
        "front-office.appointment-scheduling.edit",
    }
    assert any(permission.endswith(".delete") for permission in permissions)
    assert any(permission.endswith(".export") for permission in permissions)
    assert any(permission.endswith(".print") for permission in permissions)
    assert all(
        not permission.endswith((".delete", ".export", ".print"))
        for role, role_permissions in grants.items()
        if role != "SuperAdmin"
        for permission in role_permissions
    )
    assert grants["SuperAdmin"] == set(permissions)
    assert {
        "identity.users.read",
        "identity.users.manage",
        "identity.roles.read",
        "identity.roles.manage",
        "quality-audit.read-only-audit-trail-and-transaction-reports.view",
    }.issubset(grants["System Administrator"])
