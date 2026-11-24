"""Operational events: one structured log line per thing operations alerts on.

Each call writes a JSON log record with `ops_event` set (Cloud Logging puts it at
jsonPayload.ops_event). Terraform turns each event name into a log-based metric and an
alert (infra/terraform/modules/environment/monitoring.tf), so the names below are an
interface: renaming one silently breaks its alert. test_ops.py pins them.

Fields must be ids and counts, never personal data (the log filter redacts it anyway).
"""

import logging

logger = logging.getLogger("barterly.ops")

# Event name → what it means. monitoring.tf has a metric for each.
EVENTS = {
    "webhook_rejected": "A provider webhook failed its signature or format check.",
    "webhook_failed": "A signed webhook couldn't be applied (it will be retried).",
    "reconciliation_mismatch": "The daily ledger-vs-gateway check found differences.",
    "notification_dead_letter": "A notification used up its retries.",
    "db_connection_failed": "The database couldn't be reached after every retry.",
    "job_failed": "A scheduled job raised; Cloud Scheduler will retry it.",
    "backlog": "Periodic counts of work waiting (the ops_backlog job).",
}


def ops_event(name: str, *, level: int = logging.WARNING, **fields) -> None:
    if name not in EVENTS:
        raise ValueError(f"Unknown ops event {name!r}; add it to apps.common.ops.EVENTS.")
    logger.log(level, "ops: %s", name, extra={"ops_event": name, **fields})
