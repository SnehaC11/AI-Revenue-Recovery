from database.database import Base, SessionLocal, engine
from database.models import (
    AuditLog,
    Customer,
    Payment,
    RecoveryAction,
    RecoveryCase,
)


CUSTOMERS = [
    ("CUS-1001", "Aarav Shah", "aarav@example.com", 145000, 18, 1),
    ("CUS-1002", "Anaya Rao", "anaya@example.com", 92000, 11, 1),
    ("CUS-1003", "Vihaan Mehta", "vihaan@example.com", 310000, 26, 0),
    ("CUS-1004", "Ira Kapoor", "ira@example.com", 68000, 9, 2),
    ("CUS-1005", "Kabir Jain", "kabir@example.com", 124000, 16, 0),
    ("CUS-1006", "Diya Nair", "diya@example.com", 58000, 7, 2),
    ("CUS-1007", "Advait Sen", "advait@example.com", 201000, 22, 0),
    ("CUS-1008", "Myra Das", "myra@example.com", 77000, 8, 1),
    ("CUS-1009", "Arjun Iyer", "arjun@example.com", 43000, 5, 2),
    ("CUS-1010", "Sara Thomas", "sara@example.com", 89000, 12, 1),
]

PAYMENTS = [
    ("PAY-2001", "CUS-1001", 14999, "FAILED", "INSUFFICIENT_FUNDS", 0, False),
    ("PAY-2002", "CUS-1002", 18999, "FAILED", "BANK_DECLINED", 3, False),
    ("PAY-2003", "CUS-1003", 42000, "FAILED", "NETWORK_ERROR", 0, False),
    ("PAY-2004", "CUS-1004", 6999, "FAILED", "CARD_EXPIRED", 1, False),
    ("PAY-2005", "CUS-1005", 22999, "FAILED", "NETWORK_ERROR", 0, False),
    ("PAY-2006", "CUS-1006", 4999, "FAILED", "AUTHENTICATION_FAILED", 2, False),
    ("PAY-2007", "CUS-1007", 15999, "FAILED", "INSUFFICIENT_FUNDS", 0, False),
    ("PAY-2008", "CUS-1008", 8999, "FAILED", "CARD_EXPIRED", 0, False),
]

RECOVERY_CASES = [
    {
        "case_id": "CHK-1001",
        "customer_id": "CUS-1001",
        "amount_at_risk": 24999,
        "risk_score": 0.91,
        "recovery_probability": 0.72,
        "expected_recovery": 16249.35,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1002",
        "customer_id": "CUS-1002",
        "amount_at_risk": 8999,
        "risk_score": 0.72,
        "recovery_probability": 0.41,
        "expected_recovery": 3149.65,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1003",
        "customer_id": "CUS-1003",
        "amount_at_risk": 125000,
        "risk_score": 0.97,
        "recovery_probability": 0.38,
        "expected_recovery": 47500,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1004",
        "customer_id": "CUS-1004",
        "amount_at_risk": 15999,
        "risk_score": 0.79,
        "recovery_probability": 0.63,
        "expected_recovery": 10079.37,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1005",
        "customer_id": "CUS-1005",
        "amount_at_risk": 54000,
        "risk_score": 0.83,
        "recovery_probability": 0.66,
        "expected_recovery": 35100,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1006",
        "customer_id": "CUS-1006",
        "amount_at_risk": 6999,
        "risk_score": 0.58,
        "recovery_probability": 0.31,
        "expected_recovery": 2169.69,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1007",
        "customer_id": "CUS-1007",
        "amount_at_risk": 9800,
        "risk_score": 0.76,
        "recovery_probability": 0.48,
        "expected_recovery": 4704,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1008",
        "customer_id": "CUS-1008",
        "amount_at_risk": 118000,
        "risk_score": 0.88,
        "recovery_probability": 0.34,
        "expected_recovery": 40120,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1009",
        "customer_id": "CUS-1009",
        "amount_at_risk": 12999,
        "risk_score": 0.69,
        "recovery_probability": 0.46,
        "expected_recovery": 5979.54,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
    {
        "case_id": "CHK-1010",
        "customer_id": "CUS-1010",
        "amount_at_risk": 45999,
        "risk_score": 0.81,
        "recovery_probability": 0.61,
        "expected_recovery": 28059.39,
        "status": "AT_RISK",
        "recovery_type": "CHECKOUT_ABANDONMENT",
    },
]


def reset_tables(db):
    # Clear dependent workflow history first so re-seeding is a true clean demo.
    db.query(AuditLog).delete()
    db.query(RecoveryAction).delete()
    db.query(RecoveryCase).delete()
    db.query(Payment).delete()
    db.query(Customer).delete()
    db.commit()


def seed_customers(db):
    for row in CUSTOMERS:
        db.add(
            Customer(
                customer_id=row[0],
                name=row[1],
                email=row[2],
                lifetime_value=row[3],
                successful_payments=row[4],
                failed_payments=row[5],
            )
        )


def seed_payments(db):
    for row in PAYMENTS:
        db.add(
            Payment(
                payment_id=row[0],
                customer_id=row[1],
                amount=row[2],
                currency="INR",
                status=row[3],
                original_status=row[3],
                failure_reason=row[4],
                retry_count=row[5],
                recovered=row[6],
            )
        )


def seed_cases(db):
    for item in RECOVERY_CASES:
        db.add(RecoveryCase(**item))

    for payment_id, customer_id, amount, _, _, retry_count, _ in PAYMENTS:
        db.add(
            RecoveryCase(
                case_id=f"RC-{payment_id}",
                payment_id=payment_id,
                customer_id=customer_id,
                amount_at_risk=amount,
                risk_score=0.89 if amount >= 14000 else 0.64,
                recovery_probability=0.74 if retry_count == 0 else 0.27,
                expected_recovery=round(
                    amount * (0.74 if retry_count == 0 else 0.27),
                    2,
                ),
                status="AT_RISK",
                recovery_type="PAYMENT_FAILURE",
            )
        )


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        reset_tables(db)
        seed_customers(db)
        seed_payments(db)
        seed_cases(db)
        db.commit()
        print("RecoverAI demo dataset reset and seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
