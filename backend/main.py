from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.analytics import router as analytics_router
from api.recovery import router as recovery_router
from database import models
from database.database import Base, engine


def ensure_schema():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        def add_missing_columns(table, definitions):
            columns = {
                row[1]
                for row in connection.execute(
                    text(f"PRAGMA table_info({table})")
                )
            }
            for name, definition in definitions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )

        add_missing_columns("customers", {
            "recovery_consent": "BOOLEAN DEFAULT 1",
            "contact_opt_out": "BOOLEAN DEFAULT 0",
            "preferred_contact_channel": "VARCHAR DEFAULT 'EMAIL'",
        })
        add_missing_columns("recovery_cases", {
            "amount_recovered": "FLOAT DEFAULT 0",
            "recovery_attempts": "INTEGER DEFAULT 0",
            "source_event_id": "VARCHAR",
            "source_context": "VARCHAR DEFAULT '{}'",
            "contact_attempts": "INTEGER DEFAULT 0",
            "execution_key": "VARCHAR",
        })
        add_missing_columns("recovery_actions", {
            "action_key": "VARCHAR",
            "channel": "VARCHAR",
            "recipient": "VARCHAR",
            "outcome": "VARCHAR DEFAULT 'PENDING'",
            "provider_reference": "VARCHAR",
            "is_simulated": "BOOLEAN DEFAULT 1",
            "evidence": "VARCHAR DEFAULT '{}'",
        })
        add_missing_columns("audit_logs", {
            "previous_hash": "VARCHAR",
            "event_hash": "VARCHAR",
        })
        # SQLite cannot add unique constraints with ALTER TABLE.  These
        # indexes give upgraded demo databases the same idempotency and audit
        # guarantees as freshly-created schemas.
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_recovery_action_key "
            "ON recovery_actions(action_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_recovery_execution_key "
            "ON recovery_cases(execution_key)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_recovery_source_event "
            "ON recovery_cases(source_event_id)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_event_hash "
            "ON audit_logs(event_hash)"
        ))

        # Versions before checkout-event ingestion generated CHK-100000 through
        # CHK-100099 whenever the dashboard's detection button was clicked.
        # Remove only those known synthetic rows and their history; no seeded
        # or externally supplied checkout event matches this exact range.
        legacy_checkout_filter = (
            "recovery_type = 'CHECKOUT_ABANDONMENT' "
            "AND case_id >= 'CHK-REC-CHK-100000' "
            "AND case_id <= 'CHK-REC-CHK-100099' "
            "AND source_event_id >= 'CHK-100000' "
            "AND source_event_id <= 'CHK-100099' "
            "AND source_context NOT LIKE '%seeded_demo%'"
        )
        connection.execute(text(
            "DELETE FROM audit_logs WHERE case_id IN "
            f"(SELECT case_id FROM recovery_cases WHERE {legacy_checkout_filter})"
        ))
        connection.execute(text(
            "DELETE FROM recovery_actions WHERE case_id IN "
            f"(SELECT case_id FROM recovery_cases WHERE {legacy_checkout_filter})"
        ))
        connection.execute(text(
            f"DELETE FROM recovery_cases WHERE {legacy_checkout_filter}"
        ))


ensure_schema()


app = FastAPI(
    title="RecoverAI",
    description="AI Revenue Recovery Agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recovery_router)
app.include_router(analytics_router)


@app.get("/")
def root():
    return {
        "name": "RecoverAI",
        "status": "running",
        "message": "AI Revenue Recovery Agent",
    }
