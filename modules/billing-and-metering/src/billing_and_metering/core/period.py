"""The `[start, end)` window a billing period name resolves to, as of a
given instant -- deliberately the exact same definition FinOps's own
`period_window` uses (`daily`/`monthly`, relative to "now"), since
FinOps's `GET /cost-reports/{tenant_id}` computes its own window
internally and accepts no explicit date range. Mirroring it here is
what lets the Auditability event count this module computes for the
same nominal period line up with the real dollar figure FinOps
reports for it.
"""
from __future__ import annotations

from datetime import datetime, timedelta

VALID_PERIODS = ("daily", "monthly")


def period_window(period: str, at: datetime) -> tuple[datetime, datetime]:
    if period == "daily":
        start = at.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)

    start = at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if at.month == 12:
        end = start.replace(year=at.year + 1, month=1)
    else:
        end = start.replace(month=at.month + 1)
    return start, end
