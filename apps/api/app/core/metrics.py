"""Minimal in-process metrics for GET /metrics (OBS-2).

Prometheus text format without an extra dependency. Business metrics (questions per
day, fallback rate) come from the database in the admin dashboard (M5), not from here.
"""

import time
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Metrics:
    started_at: float = field(default_factory=time.time)
    requests_by_status: Counter[int] = field(default_factory=Counter)

    def record_request(self, status_code: int) -> None:
        self.requests_by_status[status_code] += 1

    def render(self) -> str:
        lines = [
            "# HELP campus_pulse_uptime_seconds Seconds since the API process started.",
            "# TYPE campus_pulse_uptime_seconds gauge",
            f"campus_pulse_uptime_seconds {time.time() - self.started_at:.0f}",
            "# HELP campus_pulse_http_requests_total HTTP requests by status code.",
            "# TYPE campus_pulse_http_requests_total counter",
        ]
        for status, count in sorted(self.requests_by_status.items()):
            lines.append(f'campus_pulse_http_requests_total{{status="{status}"}} {count}')
        return "\n".join(lines) + "\n"


metrics = Metrics()
