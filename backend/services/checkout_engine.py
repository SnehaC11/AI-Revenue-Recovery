from datetime import datetime
from database.models import RecoveryCase

def create_checkout_cases(
    db,
    checkout_events
):

    detected_cases = detect_checkout_risk(
        checkout_events
    )

    created_cases = []

    for data in detected_cases:

        existing = (
            db.query(RecoveryCase)
            .filter(
                RecoveryCase.case_id
                == data["case_id"]
            )
            .first()
        )

        if existing:
            created_cases.append(existing)
            continue

        case = RecoveryCase(

            case_id=data["case_id"],

            customer_id=data["customer_id"],

            payment_id=data["checkout_id"],

            amount_at_risk=data[
                "amount_at_risk"
            ],

            risk_score=data[
                "risk_score"
            ],

            expected_recovery=data[
                "expected_recovery"
            ],

            status="OPEN",

            recovery_type=
                "CHECKOUT_ABANDONMENT",
        )

        db.add(case)

        created_cases.append(case)

    db.commit()

    return created_cases

def detect_checkout_risk(
    checkout_events
):

    cases = []

    for checkout in checkout_events:

        amount = checkout["amount"]

        minutes = checkout[
            "minutes_since_abandonment"
        ]

        if amount < 999:
            continue

        risk_score = 50

        if amount >= 9999:
            risk_score += 20

        if minutes <= 60:
            risk_score += 20

        if checkout["payment_attempted"]:
            risk_score += 10

        risk_score = min(
            risk_score,
            100
        )

        expected_recovery = (
            amount * risk_score / 100
        )

        cases.append({
            "case_id":
                f"CHK-REC-{checkout['checkout_id']}",

            "checkout_id":
                checkout["checkout_id"],

            "customer_id":
                checkout["customer_id"],

            "amount_at_risk":
                amount,

            "risk_score":
                risk_score,

            "expected_recovery":
                round(
                    expected_recovery,
                    2
                ),

            "recovery_type":
                "CHECKOUT_ABANDONMENT",

            "detected_at":
                datetime.utcnow(),
        })

    return cases