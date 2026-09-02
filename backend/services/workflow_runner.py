from sqlalchemy.orm import Session

from database.models import RecoveryCase

from services.recovery_engine import execute_recovery


MAX_WORKFLOW_ATTEMPTS = 2


def run_case_workflow(
    db: Session,
    case_id: str
):

    attempts = []

    for workflow_attempt in range(
        1,
        MAX_WORKFLOW_ATTEMPTS + 1
    ):

        result = execute_recovery(
            db,
            case_id
        )

        attempts.append({
            "workflow_attempt": workflow_attempt,
            **result
        })

        # ----------------------------
        # Stop after success
        # ----------------------------

        if result.get("success"):

            break

        # ----------------------------
        # Stop if case is exhausted
        # ----------------------------

        if result.get("status") in {
            "EXHAUSTED",
            "ESCALATED",
            "RECOVERED"
        }:

            break

    return attempts