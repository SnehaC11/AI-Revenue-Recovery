from logging import config
import os
import json

from dotenv import load_dotenv
from google import genai
from google.genai import errors

DEMO_MODE = os.getenv("RECOVERY_DEMO_MODE", "false").lower() == "true"
load_dotenv()


client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


AVAILABLE_ACTIONS = [
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "REQUEST_PAYMENT_METHOD_UPDATE",
    "ESCALATE_TO_FINANCE",
    "CLOSE_CASE"
]


def build_agent_prompt(case, payment, customer):

    return f"""
You are RecoverAI, an AI revenue recovery agent.

Your job is to select the safest and most effective recovery
action for a failed payment.

You do NOT execute payments yourself.

You may only recommend one of the allowed actions.

CUSTOMER
---------
Customer ID: {customer.customer_id}
Name: {customer.name}
Lifetime Value: ₹{customer.lifetime_value}
Successful Payments: {customer.successful_payments}
Failed Payments: {customer.failed_payments}

PAYMENT
-------
Payment ID: {payment.payment_id}
Amount: ₹{payment.amount}
Currency: {payment.currency}
Status: {payment.status}
Failure Reason: {payment.failure_reason}
Previous Retry Count: {payment.retry_count}

RISK ANALYSIS
-------------
Risk Score: {case.risk_score}
Recovery Probability: {case.recovery_probability}
Expected Recovery: ₹{case.expected_recovery}

ALLOWED ACTIONS
---------------
{", ".join(AVAILABLE_ACTIONS)}

DECISION RULES
--------------
1. If the failure is likely temporary and the customer has
   a strong payment history, prefer RETRY_PAYMENT.

2. If the payment method is expired, prefer
   REQUEST_PAYMENT_METHOD_UPDATE.

3. If automatic retry is unlikely to work, prefer
   SEND_PAYMENT_LINK.

4. If the amount is very high or the situation is uncertain,
   prefer ESCALATE_TO_FINANCE.

5. Never invent an action outside the allowed actions.

6. Never claim that a payment has succeeded.
   You are only selecting an action.

Return ONLY valid JSON in this exact structure:

{{
    "action": "ONE_ALLOWED_ACTION",
    "confidence": 0.0,
    "reason": "short explanation",
    "expected_outcome": "short explanation"
}}
"""

def fallback_recovery_decision(case):
    """
    Deterministic fallback used when Gemini is unavailable.
    Keeps the recovery workflow running safely.
    """

    risk_score = getattr(case, "risk_score", 0) or 0
    retry_count = getattr(case, "retry_count", 0) or 0

    if retry_count >= 2:
        return {
            "action": "ESCALATE",
            "confidence": 0.95,
            "reason": "Retry limit reached. Further automated attempts are blocked.",
            "source": "POLICY_FALLBACK"
        }

    if risk_score >= 80:
        return {
            "action": "RETRY_PAYMENT",
            "confidence": 0.88,
            "reason": "High recovery probability with one bounded retry permitted.",
            "source": "POLICY_FALLBACK"
        }

    if risk_score >= 60:
        return {
            "action": "RETRY_PAYMENT",
            "confidence": 0.76,
            "reason": "Moderate recovery probability. One bounded retry is permitted.",
            "source": "POLICY_FALLBACK"
        }

    return {
        "action": "ESCALATE",
        "confidence": 0.82,
        "reason": "Risk score below automated recovery threshold.",
        "source": "POLICY_FALLBACK"
    }

def decide_recovery_action(case, payment, customer):

    prompt = build_agent_prompt(
        case,
        payment,
        customer
    )
    if DEMO_MODE:
        return fallback_recovery_decision(case)

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )

        # Existing parsing logic goes here

    except errors.ClientError as e:

        if e.code == 429:

            return {
                "action": "RETRY_PAYMENT",
                "confidence": 0.70,
                "reason": (
                    "Gemini quota unavailable. "
                    "Fallback recovery policy selected "
                    "a bounded retry based on payment risk."
                ),
                "source": "POLICY_FALLBACK"
            }

        raise

    text = response.text.strip()

    # Remove markdown code fences if Gemini adds them
    if text.startswith("```"):
        text = text.replace("```json", "")
        text = text.replace("```", "")
        text = text.strip()

    decision = json.loads(text)

    return decision