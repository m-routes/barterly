"""PostgreSQL backend that retries new connections (instance restarts, failover).

Use it with ENGINE = "apps.core.db.postgresql". Configure with the
DB_CONNECT_ATTEMPTS and DB_CONNECT_RETRY_DELAY settings.
"""

from django.conf import settings
from django.db.backends.postgresql import base

from apps.core.services.db_retry import connect_with_retry


class DatabaseWrapper(base.DatabaseWrapper):
    def get_new_connection(self, conn_params):
        parent = super().get_new_connection
        return connect_with_retry(
            lambda: parent(conn_params),
            retry_on=(self.Database.OperationalError,),
            attempts=getattr(settings, "DB_CONNECT_ATTEMPTS", 4),
            base_delay=getattr(settings, "DB_CONNECT_RETRY_DELAY", 0.5),
        )
