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
        columns = {
            row[1]
            for row in connection.execute(
                text("PRAGMA table_info(recovery_cases)")
            )
        }

        if "amount_recovered" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE recovery_cases "
                    "ADD COLUMN amount_recovered FLOAT DEFAULT 0"
                )
            )

        if "recovery_attempts" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE recovery_cases "
                    "ADD COLUMN recovery_attempts INTEGER DEFAULT 0"
                )
            )


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
