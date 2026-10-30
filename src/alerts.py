"""E-mail alerts through the project's SNS topic (the same one the CloudWatch alarms use).

The topic ARN comes from QGW_ALERT_TOPIC_ARN, set by infra/aws on the drift job and the dashboard.
Without it (local runs, CI) nothing is sent and notify() returns False.
"""

import os

TOPIC_ENV = "QGW_ALERT_TOPIC_ARN"


def enabled() -> bool:
    return bool(os.getenv(TOPIC_ENV))


def notify(subject: str, message: str) -> bool:
    arn = os.getenv(TOPIC_ENV)
    if not arn:
        return False
    import boto3

    boto3.client("sns").publish(TopicArn=arn, Subject=subject[:100], Message=message)
    return True


def drift_message(rec: dict, check_date: str, source: str, extra: list[str] | None = None) -> tuple[str, str]:
    """Subject and body for a Tier 3 retraining recommendation."""
    subject = f"QGlacierWatch: retraining needed (Tier {rec['tier']}, {check_date})"
    lines = [
        f"Source: {source}",
        f"Check date: {check_date}",
        f"Tier {rec['tier']}: {rec['action']}",
        "Reasons:",
        *[f"  - {r}" for r in rec["reasons"]],
        *(extra or []),
        "",
        "Retraining starts only after a named person approves it; a candidate is promoted only if it passes the registry gate.",
    ]
    return subject, "\n".join(lines)
