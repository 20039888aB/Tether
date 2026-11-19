from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

json_type = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True
    ),
    Column("granted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("granted_by", Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("failed_login_attempts >= 0"),
        Index(
            "uq_users_system_owner",
            "is_system_owner",
            unique=True,
            sqlite_where=text("is_system_owner = 1"),
            postgresql_where=text("is_system_owner"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(128))
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id", ondelete="SET NULL"))
    password_hash: Mapped[str] = mapped_column(Text)
    is_system_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_pending_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles,
        primaryjoin=lambda: User.id == user_roles.c.user_id,
        secondaryjoin=lambda: Role.id == user_roles.c.role_id,
        back_populates="users",
    )
    permission_overrides: Mapped[list["UserPermissionOverride"]] = relationship(
        back_populates="user",
        foreign_keys="UserPermissionOverride.user_id",
        cascade="all, delete-orphan",
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    users: Mapped[list[User]] = relationship(
        secondary=user_roles,
        primaryjoin=lambda: Role.id == user_roles.c.role_id,
        secondaryjoin=lambda: User.id == user_roles.c.user_id,
        back_populates="roles",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions, back_populates="roles"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    permission_key: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )
    user_overrides: Mapped[list["UserPermissionOverride"]] = relationship(
        back_populates="permission",
        cascade="all, delete-orphan",
    )


class UserPermissionOverride(Base):
    __tablename__ = "user_permission_overrides"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[UUID] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    user: Mapped[User] = relationship(
        back_populates="permission_overrides",
        foreign_keys=[user_id],
    )
    permission: Mapped[Permission] = relationship(
        back_populates="user_overrides",
    )


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (CheckConstraint("sort_order >= 0"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VisitType(Base):
    __tablename__ = "visit_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color_hex: Mapped[str] = mapped_column(String(7), default="#F26B6B", server_default="#F26B6B")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


clinic_visit_types = Table(
    "clinic_visit_types",
    Base.metadata,
    Column("clinic_id", Integer, ForeignKey("clinics.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "visit_type_id",
        Integer,
        ForeignKey("visit_types.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


class FacilityClinic(Base):
    __tablename__ = "facility_clinics"
    __table_args__ = (
        CheckConstraint("NOT is_unavailable OR unavailable_reason IS NOT NULL"),
    )

    facility_id: Mapped[int] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), primary_key=True
    )
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), primary_key=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    is_unavailable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    unavailable_reason: Mapped[str | None] = mapped_column(String(255))
    unavailable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unavailable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DoctorClinic(Base):
    __tablename__ = "doctor_clinics"

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    facility_id: Mapped[int] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), primary_key=True
    )
    clinic_id: Mapped[int] = mapped_column(
        ForeignKey("clinics.id", ondelete="RESTRICT"), primary_key=True
    )
    on_leave_from: Mapped[date | None] = mapped_column(Date)
    on_leave_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (CheckConstraint("expires_at > created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    csrf_token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class PatientNumberCounter(Base):
    __tablename__ = "patient_number_counters"
    __table_args__ = (CheckConstraint("value >= 0"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "sex_at_birth IS NULL OR sex_at_birth IN "
            "('female', 'male', 'intersex', 'unknown')"
        ),
        CheckConstraint(
            "(next_of_kin_name IS NULL AND next_of_kin_phone IS NULL "
            "AND next_of_kin_relationship IS NULL) OR "
            "(next_of_kin_name IS NOT NULL AND next_of_kin_phone IS NOT NULL "
            "AND next_of_kin_relationship IS NOT NULL)"
        ),
        CheckConstraint(
            "next_of_kin_relationship IS NULL OR next_of_kin_relationship IN "
            "('spouse', 'partner', 'parent', 'mother', 'father', 'child', 'son', "
            "'daughter', 'sibling', 'brother', 'sister', 'grandparent', "
            "'grandmother', 'grandfather', 'grandchild', 'aunt', 'uncle', "
            "'niece', 'nephew', 'cousin', 'step_parent', 'step_child', "
            "'parent_in_law', 'child_in_law', 'sibling_in_law', 'guardian', "
            "'legal_guardian', 'foster_parent', 'caregiver', 'friend', "
            "'neighbor', 'other')"
        ),
        CheckConstraint(
            "(next_of_kin_relationship = 'other' AND "
            "next_of_kin_relationship_other IS NOT NULL) OR "
            "(next_of_kin_relationship IS NULL AND "
            "next_of_kin_relationship_other IS NULL) OR "
            "(next_of_kin_relationship IS NOT NULL AND "
            "next_of_kin_relationship != 'other' AND "
            "next_of_kin_relationship_other IS NULL)"
        ),
        CheckConstraint("version >= 1"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    patient_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    sex_at_birth: Mapped[str | None] = mapped_column(String(16))
    phone_number: Mapped[str | None] = mapped_column(String(32), index=True)
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(String(500))
    next_of_kin_name: Mapped[str | None] = mapped_column(String(200))
    next_of_kin_phone: Mapped[str | None] = mapped_column(String(32))
    next_of_kin_relationship: Mapped[str | None] = mapped_column(String(32))
    next_of_kin_relationship_other: Mapped[str | None] = mapped_column(String(100))
    nationality: Mapped[str | None] = mapped_column(String(80))
    document_type: Mapped[str | None] = mapped_column(String(40))
    document_number: Mapped[str | None] = mapped_column(String(100))
    marital_status: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(100))
    phone_country_code: Mapped[str] = mapped_column(
        String(8), default="+254", server_default="+254"
    )
    city_town: Mapped[str | None] = mapped_column(String(100))
    sub_county_estate: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    next_of_kin_phone_country_code: Mapped[str] = mapped_column(
        String(8), default="+254", server_default="+254"
    )
    next_of_kin_email: Mapped[str | None] = mapped_column(String(320))
    next_of_kin_id_number: Mapped[str | None] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    debtor_account: Mapped[str | None] = mapped_column(String(100))
    staff_account: Mapped[str | None] = mapped_column(String(100))
    operating_currency: Mapped[str] = mapped_column(
        String(3), default="KES", server_default="KES"
    )
    legacy_number: Mapped[str | None] = mapped_column(String(100))
    tax_pin: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    outpatient_visits: Mapped[list["OutpatientVisit"]] = relationship(
        back_populates="patient",
    )


class OutpatientVisit(Base):
    __tablename__ = "outpatient_visits"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'cancelled', 'completed')"),
        CheckConstraint(
            "workflow_state IN "
            "('awaiting_triage', 'awaiting_doctor', 'consultation_in_progress', "
            "'completed', 'cancelled')"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    patient_id: Mapped[UUID] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"),
        index=True,
    )
    clinic_id: Mapped[int | None] = mapped_column(ForeignKey("clinics.id", ondelete="RESTRICT"))
    visit_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    clinic: Mapped[str] = mapped_column(String(128))
    visit_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    workflow_state: Mapped[str] = mapped_column(
        String(32), default="awaiting_triage", server_default="awaiting_triage"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    patient: Mapped[Patient] = relationship(back_populates="outpatient_visits")
    triage: Mapped["VisitTriage | None"] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        uselist=False,
    )
    consultation_notes: Mapped[list["ConsultationNote"]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="ConsultationNote.created_at",
    )


class VisitTriage(Base):
    __tablename__ = "visit_triages"
    __table_args__ = (
        CheckConstraint(
            "blood_pressure_systolic IS NULL OR blood_pressure_diastolic IS NULL OR "
            "blood_pressure_systolic > blood_pressure_diastolic"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    visit_id: Mapped[UUID] = mapped_column(
        ForeignKey("outpatient_visits.id", ondelete="RESTRICT"),
        unique=True,
        index=True,
    )
    blood_pressure_systolic: Mapped[int | None] = mapped_column(Integer)
    blood_pressure_diastolic: Mapped[int | None] = mapped_column(Integer)
    pulse_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    temperature_celsius: Mapped[float | None] = mapped_column()
    respiratory_rate_bpm: Mapped[int | None] = mapped_column(Integer)
    oxygen_saturation_percent: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column()
    height_cm: Mapped[float | None] = mapped_column()
    pain_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    visit: Mapped[OutpatientVisit] = relationship(back_populates="triage")


class ConsultationNote(Base):
    __tablename__ = "consultation_notes"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'signed')"),
        CheckConstraint("note_type IN ('consultation', 'addendum')"),
        CheckConstraint(
            "(note_type = 'consultation' AND parent_note_id IS NULL) OR "
            "(note_type = 'addendum' AND parent_note_id IS NOT NULL)"
        ),
        CheckConstraint("version >= 1"),
        Index("consultation_notes_visit_created_idx", "visit_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    visit_id: Mapped[UUID] = mapped_column(
        ForeignKey("outpatient_visits.id", ondelete="RESTRICT"),
        index=True,
    )
    parent_note_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("consultation_notes.id", ondelete="RESTRICT")
    )
    note_type: Mapped[str] = mapped_column(String(16), default="consultation")
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    author_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    visit: Mapped[OutpatientVisit] = relationship(back_populates="consultation_notes")
    parent_note: Mapped["ConsultationNote | None"] = relationship(remote_side=[id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(160))
    resource_type: Mapped[str] = mapped_column(String(160))
    resource_id: Mapped[str | None] = mapped_column(String(256))
    outcome: Mapped[str] = mapped_column(String(16))
    source_ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), default=uuid4)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", json_type, default=dict)
    operation_event: Mapped["SystemEvent | None"] = relationship(
        back_populates="audit_log",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (
        CheckConstraint(
            "category IN ('patient_access', 'nursing', 'clinical', 'admissions', "
            "'laboratory', 'pharmacy', 'billing', 'messaging', 'identity', 'configuration')"
        ),
        Index("system_events_category_id_idx", "category", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_log_id: Mapped[int] = mapped_column(
        ForeignKey("audit_logs.id", ondelete="RESTRICT"),
        unique=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(160))
    resource_type: Mapped[str] = mapped_column(String(160))
    resource_id: Mapped[str | None] = mapped_column(String(256))
    audit_log: Mapped[AuditLog] = relationship(back_populates="operation_event")
