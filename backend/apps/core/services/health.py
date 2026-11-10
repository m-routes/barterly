"""Health checks used by the /api/v1/health/ endpoint and deploy smoke tests."""

from dataclasses import dataclass

from django.db import DatabaseError, connections


@dataclass(frozen=True)
class HealthReport:
    database: bool

    @property
    def ok(self) -> bool:
        return self.database

    def as_dict(self) -> dict[str, str]:
        return {
            "status": "ok" if self.ok else "degraded",
            "database": "ok" if self.database else "unavailable",
        }


def check_database(alias: str = "default") -> bool:
    try:
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except DatabaseError:
        return False


def get_health_report() -> HealthReport:
    return HealthReport(database=check_database())
