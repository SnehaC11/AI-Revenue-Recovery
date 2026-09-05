from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from datetime import datetime

from database.database import Base


class Customer(Base):

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)

    customer_id = Column(String, unique=True, index=True)

    name = Column(String)

    email = Column(String)

    lifetime_value = Column(Float, default=0)

    successful_payments = Column(Integer, default=0)

    failed_payments = Column(Integer, default=0)

    # Recovery communications are opt-in by default only for the local demo.
    # Production ingestion must set these from the system of record.
    recovery_consent = Column(Boolean, default=True, nullable=False)
    contact_opt_out = Column(Boolean, default=False, nullable=False)
    preferred_contact_channel = Column(String, default="EMAIL")


class Payment(Base):

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)

    payment_id = Column(String, unique=True, index=True)

    customer_id = Column(String, index=True)

    amount = Column(Float)

    currency = Column(String, default="INR")

    status = Column(String)

    original_status = Column(String)

    failure_reason = Column(String, nullable=True)

    retry_count = Column(Integer, default=0)

    recovered = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class RecoveryCase(Base):

    __tablename__ = "recovery_cases"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(String, unique=True, index=True)

    payment_id = Column(String)

    customer_id = Column(String)

    amount_at_risk = Column(Float)

    risk_score = Column(Float)

    recovery_probability = Column(Float)

    expected_recovery = Column(Float, default=0)

    status = Column(String, default="AT_RISK")

    selected_action = Column(String, nullable=True)

    agent_reason = Column(String, nullable=True)

    confidence = Column(Float, default=0)

    amount_recovered = Column(Float, default=0)

    recovery_attempts = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    recovery_type = Column(String, default="PAYMENT_FAILURE")

    # Snapshot of the source signal used for the decision.  Retaining it makes
    # a later audit reproducible even if the upstream event changes.
    source_event_id = Column(String, unique=True, nullable=True)
    source_context = Column(String, default="{}")
    contact_attempts = Column(Integer, default=0, nullable=False)
    execution_key = Column(String, unique=True, nullable=True)


class RecoveryAction(Base):

    __tablename__ = "recovery_actions"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(String)

    action = Column(String)

    result = Column(String)

    amount_recovered = Column(Float, default=0)

    action_key = Column(String, unique=True, index=True)
    channel = Column(String, nullable=True)
    recipient = Column(String, nullable=True)
    outcome = Column(String, default="PENDING")
    provider_reference = Column(String, nullable=True)
    is_simulated = Column(Boolean, default=True, nullable=False)
    evidence = Column(String, default="{}")

    timestamp = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    case_id = Column(String)

    event = Column(String)

    details = Column(String)

    timestamp = Column(DateTime, default=datetime.utcnow)

    # Append-only application audit chain.  Each event commits to the prior
    # event for the same case, making edits or removals detectable on export.
    previous_hash = Column(String, nullable=True)
    event_hash = Column(String, unique=True, index=True, nullable=True)

    @property
    def event_type(self):
        return self.event

    @property
    def created_at(self):
        return self.timestamp
