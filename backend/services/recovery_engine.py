from sqlalchemy.orm import Session

from database.models import (
    RecoveryCase,
    Payment,
    Customer,
    RecoveryAction,
    AuditLog
)

from agents.recovery_agent import decide_recovery_action

from services.policy_engine import (
    validate_action,
    should_stop
)

from services.payment_simulator import (
    retry_payment
)


def create_audit_log(
    db,
    case_id,
    event,
    details
):

    audit = AuditLog(
        case_id=case_id,
        event=event,
        details=str(details)
    )

    db.add(audit)


def execute_recovery(
    db: Session,
    case_id: str
):

    # --------------------------------
    # Find recovery case
    # --------------------------------

    case = (
        db.query(RecoveryCase)
        .filter(
            RecoveryCase.case_id == case_id
        )
        .first()
    )

    if not case:

        return {
            "success": False,
            "message": "Recovery case not found."
        }

    # --------------------------------
    # Find payment
    # --------------------------------

    payment = (
        db.query(Payment)
        .filter(
            Payment.payment_id == case.payment_id
        )
        .first()
    )

    # --------------------------------
    # Find customer
    # --------------------------------

    customer = (
        db.query(Customer)
        .filter(
            Customer.customer_id == case.customer_id
        )
        .first()
    )

    if not payment or not customer:

        return {
            "success": False,
            "message": "Payment or customer not found."
        }

    # --------------------------------
    # Check stopping rules first
    # --------------------------------

    stop_result = should_stop(
        case,
        payment
    )

    if stop_result["stop"]:

        case.status = (
            "RECOVERED"
            if payment.recovered
            else "EXHAUSTED"
        )

        create_audit_log(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            stop_result["reason"]
        )

        db.commit()

        return {
            "success": payment.recovered,
            "status": case.status,
            "stopped": True,
            "reason": stop_result["reason"],
            "amount_recovered": (
                payment.amount
                if payment.recovered
                else 0
            )
        }

    # --------------------------------
    # Ask AI for decision
    # --------------------------------

    decision = decide_recovery_action(
        case,
        payment,
        customer
    )

    action = decision["action"]

    case.selected_action = action
    case.agent_reason = decision["reason"]

    # --------------------------------
    # Audit AI decision
    # --------------------------------

    create_audit_log(
        db,
        case.case_id,
        "AGENT_DECISION",
        {
            "action": action,
            "confidence": decision.get(
                "confidence"
            ),
            "reason": decision.get(
                "reason"
            )
        }
    )

    # --------------------------------
    # Policy validation
    # --------------------------------

    policy_result = validate_action(
        case,
        payment,
        action
    )

    create_audit_log(
        db,
        case.case_id,
        "POLICY_CHECK",
        policy_result
    )

    # --------------------------------
    # Policy blocked action
    # --------------------------------

    if not policy_result["allowed"]:

        case.status = "ESCALATED"

        create_audit_log(
            db,
            case.case_id,
            "POLICY_BLOCK",
            policy_result["violations"]
        )

        db.commit()

        return {
            "success": False,
            "status": "ESCALATED",
            "action": action,
            "reason": policy_result["violations"]
        }

    # --------------------------------
    # Execute payment retry
    # --------------------------------

    if action == "RETRY_PAYMENT":

        result = retry_payment(payment)

        # ----------------------------
        # Successful recovery
        # ----------------------------

        if result["success"]:

            case.status = "RECOVERED"

        # ----------------------------
        # Failed retry
        # ----------------------------

        else:

            if payment.retry_count >= 2:

                case.status = "EXHAUSTED"

            else:

                case.status = "RETRY_PENDING"

        # ----------------------------
        # Store action
        # ----------------------------

        recovery_action = RecoveryAction(
            case_id=case.case_id,
            action=action,
            result=(
                "SUCCESS"
                if result["success"]
                else "FAILED"
            ),
            amount_recovered=result[
                "amount_recovered"
            ]
        )

        db.add(recovery_action)

        # ----------------------------
        # Audit execution
        # ----------------------------

        create_audit_log(
            db,
            case.case_id,
            "ACTION_EXECUTED",
            result
        )

        # ----------------------------
        # Automatic stopping
        # ----------------------------

        final_stop = should_stop(
            case,
            payment
        )

        if final_stop["stop"]:

            create_audit_log(
                db,
                case.case_id,
                "WORKFLOW_STOPPED",
                final_stop["reason"]
            )

        db.commit()

        return {
            "success": result["success"],
            "status": case.status,
            "action": action,
            "selected_action": action,
            "agent_reason": decision.get("reason"),
            "confidence": decision.get("confidence"),
            "retry_count": payment.retry_count,
            "amount_recovered": result["amount_recovered"],
            "message": result["message"],
            "workflow_stopped": final_stop["stop"],
            "stop_reason": final_stop["reason"],
        }

    # --------------------------------
    # Non-retry actions
    # --------------------------------

    case.status = "ACTION_PENDING"

    create_audit_log(
        db,
        case.case_id,
        "ACTION_PENDING",
        action
    )

    db.commit()

    return {
        "success": True,
        "status": case.status,
        "action": action,
        "message": "Action selected and awaiting execution."
    }