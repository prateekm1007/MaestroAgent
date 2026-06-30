"""
SQLAlchemy ORM models for all Maestro database tables.

These models replace the raw CREATE TABLE statements that were scattered
across 17 files. They are the single source of truth for the database schema.

All models use the Base class from maestro_db.base.
Alembic uses these models to generate migrations.
"""

from __future__ import annotations

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from maestro_db.base import Base


# ═══════════════════════════════════════════════════════════════════════════
# OEM: Prediction Lifecycle (HIGHEST RISK — learning loop)
# ═══════════════════════════════════════════════════════════════════════════

class Prediction(Base):
    """A prediction made by Maestro — auto-created, auto-resolved."""
    __tablename__ = "predictions"
    id = Column(String, primary_key=True)
    prediction_id = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(String, nullable=False)
    organization = Column(String, default="default")
    scope = Column(String, default="org")
    prediction_type = Column(String, nullable=False)
    entity_id = Column(Text)
    recommendation = Column(Text)
    expected_outcome = Column(Text)
    expected_metric = Column(Text)
    baseline_value = Column(Float)
    predicted_value = Column(Float)
    expected_timeframe = Column(Text)
    expires_at = Column(Text)
    linked_receipts = Column(Text)  # JSON array
    linked_laws = Column(Text)      # JSON array
    linked_patterns = Column(Text)  # JSON array
    confidence = Column(Float, nullable=False)
    decision_quality = Column(String, default="medium")
    status = Column(String, nullable=False, default="pending", index=True)
    resolved_at = Column(Text)
    resolution_evidence = Column(Text)  # JSON
    created_by = Column(String, default="system")

    __table_args__ = (
        Index("idx_pred_status", "status"),
        Index("idx_pred_entity", "entity_id"),
        Index("idx_pred_type", "prediction_type"),
        Index("idx_pred_expires", "expires_at"),
    )


class ConfidenceHistory(Base):
    """History of confidence changes for any entity."""
    __tablename__ = "confidence_history"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    reason = Column(Text)
    prediction_id = Column(Text)
    source = Column(String, default="calibration")

    __table_args__ = (
        Index("idx_conf_entity", "entity_type", "entity_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# OEM: Learning / Calibration (HIGHEST RISK — learning loop)
# ═══════════════════════════════════════════════════════════════════════════

class PredictionOutcome(Base):
    """Calibration engine — tracks prediction outcomes per confidence bucket."""
    __tablename__ = "prediction_outcomes"
    id = Column(String, primary_key=True)
    prediction_id = Column(String, nullable=False)
    prediction_type = Column(String, nullable=False)
    predicted_confidence = Column(Float, nullable=False)
    predicted_bucket = Column(Integer, nullable=False)
    actual_outcome = Column(String, default="pending")  # pending | hit | miss
    actual_value = Column(Float)
    predicted_at = Column(String, nullable=False)
    resolved_at = Column(Text)
    entity_id = Column(Text)
    metadata_json = Column("metadata", Text)  # JSON


class CalibrationHistory(Base):
    """Historical calibration snapshots."""
    __tablename__ = "calibration_history"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    bucket = Column(Integer, nullable=False)
    expected_rate = Column(Float)
    actual_rate = Column(Float)
    calibration_error = Column(Float)


class FeedbackEvent(Base):
    """CEO feedback events for learning."""
    __tablename__ = "feedback_events"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    feedback = Column(String, nullable=False)
    confidence_before = Column(Float)
    confidence_after = Column(Float)
    reasoning = Column(Text)
    actor = Column(String)


class DriftEvent(Base):
    """Concept drift detection events."""
    __tablename__ = "drift_events"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    drift_type = Column(String, nullable=False)
    entity_id = Column(String)
    metric = Column(String)
    old_value = Column(Float)
    new_value = Column(Float)
    severity = Column(Float)


class LawEvolutionEvent(Base):
    """Law evolution events (promotion, demotion, drift)."""
    __tablename__ = "law_evolution_events"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    law_code = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    old_status = Column(String)
    new_status = Column(String)
    confidence_before = Column(Float)
    confidence_after = Column(Float)
    reason = Column(Text)


class KnowledgeFreshness(Base):
    """Knowledge freshness tracking."""
    __tablename__ = "knowledge_freshness"
    id = Column(String, primary_key=True)
    domain = Column(String, nullable=False)
    last_signal_at = Column(String)
    freshness_score = Column(Float)
    half_life_days = Column(Integer, default=30)


# ═══════════════════════════════════════════════════════════════════════════
# OEM: Checkpoint Store (ingestion)
# ═══════════════════════════════════════════════════════════════════════════

class ImportJob(Base):
    """Import job tracking."""
    __tablename__ = "import_jobs"
    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    sync_mode = Column(String, default="full")
    resource_type = Column(String)
    status = Column(String, default="pending")
    started_at = Column(String)
    completed_at = Column(Text)
    total_pages = Column(Integer, default=0)
    pages_completed = Column(Integer, default=0)
    signals_produced = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    error_message = Column(Text)
    metadata_json = Column("metadata", Text)  # JSON


class ImportCheckpoint(Base):
    """Import checkpoint for resume."""
    __tablename__ = "import_checkpoints"
    id = Column(String, primary_key=True)
    provider = Column(String, nullable=False)
    sync_mode = Column(String)
    resource_type = Column(String)
    last_page = Column(Integer, default=0)
    last_cursor = Column(Text)
    last_timestamp = Column(Text)
    total_pages_estimated = Column(Integer, default=0)
    pages_completed = Column(Integer, default=0)
    signals_produced = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    started_at = Column(String)
    last_updated = Column(String)
    completed = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_cp_provider", "provider"),
    )


class OAuthCredential(Base):
    """OAuth tokens for connected providers."""
    __tablename__ = "oauth_credentials"
    provider = Column(String, primary_key=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    token_type = Column(String, default="Bearer")
    expires_at = Column(Text)
    scopes = Column(Text)  # JSON array
    metadata_json = Column("metadata", Text)  # JSON
    created_at = Column(String)
    updated_at = Column(String)


class ProviderConnection(Base):
    """Provider connection state."""
    __tablename__ = "provider_connections"
    provider = Column(String, primary_key=True)
    connected = Column(Boolean, default=False)
    connected_at = Column(Text)
    org_id = Column(Text)
    metadata_json = Column("metadata", Text)  # JSON


# ═══════════════════════════════════════════════════════════════════════════
# Auth: Users, Sessions, Roles
# ═══════════════════════════════════════════════════════════════════════════

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String)
    password_hash = Column(Text)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    mfa_secret = Column(Text)
    mfa_enabled = Column(Boolean, default=False)
    org_id = Column(String, default="default")
    created_at = Column(String)
    updated_at = Column(String)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_hash = Column(Text, nullable=False)
    expires_at = Column(String, nullable=False)
    created_at = Column(String)
    ip_address = Column(String)
    user_agent = Column(Text)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token_hash = Column(Text, nullable=False)
    family_id = Column(String)
    expires_at = Column(String, nullable=False)
    created_at = Column(String)
    revoked = Column(Boolean, default=False)


class Role(Base):
    __tablename__ = "roles"
    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)


class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    id = Column(String, primary_key=True)
    role_id = Column(String, ForeignKey("roles.id"), nullable=False)
    permission = Column(String, nullable=False)


class Group(Base):
    __tablename__ = "groups"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    display_name = Column(Text)


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(String, primary_key=True)
    group_id = Column(String, ForeignKey("groups.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    actor = Column(String)
    action = Column(String, nullable=False)
    resource_type = Column(String)
    resource_id = Column(String)
    ip_address = Column(String)
    user_agent = Column(Text)
    metadata_json = Column("metadata", Text)  # JSON
    hash_prev = Column(Text)
    hash_current = Column(Text, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(String, primary_key=True)
    key_hash = Column(Text, unique=True, nullable=False)
    name = Column(String)
    created_at = Column(String)
    revoked = Column(Boolean, default=False)
    scopes = Column(Text)  # JSON


# ═══════════════════════════════════════════════════════════════════════════
# OAuth Config Store (enterprise self-service)
# ═══════════════════════════════════════════════════════════════════════════

class OAuthProviderConfig(Base):
    """Admin-configured OAuth provider settings (encrypted secrets)."""
    __tablename__ = "oauth_provider_config"
    id = Column(String, primary_key=True)
    provider = Column(String, unique=True, nullable=False)
    client_id = Column(Text, nullable=False)
    client_secret_encrypted = Column(Text, nullable=False)
    scopes = Column(Text, default="[]")  # JSON
    redirect_uri = Column(Text)
    configured_by = Column(String, default="admin")
    configured_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    enabled = Column(Integer, default=1)

    __table_args__ = (
        Index("idx_opc_provider", "provider"),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Cost tracking
# ═══════════════════════════════════════════════════════════════════════════

class CostEntry(Base):
    __tablename__ = "cost_entries"
    id = Column(String, primary_key=True)
    timestamp = Column(String, nullable=False)
    provider = Column(String)
    model = Column(String)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost = Column(Float)
    run_id = Column(String)


# ═══════════════════════════════════════════════════════════════════════════
# Schema version
# ═══════════════════════════════════════════════════════════════════════════

class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version = Column(Integer, primary_key=True)
    applied_at = Column(String, nullable=False)
