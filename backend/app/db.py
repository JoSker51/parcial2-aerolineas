"""Pool de conexiones a PostgreSQL."""
import pathlib

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

pool = ConnectionPool(
    settings.database_url,
    min_size=settings.pool_min,
    max_size=settings.pool_max,
    timeout=settings.pool_timeout_s,
    kwargs={"row_factory": dict_row},
    open=False,
)

SCHEMA = pathlib.Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


def init_schema() -> None:
    """Idempotente (CREATE ... IF NOT EXISTS): se puede correr en cada arranque."""
    with pool.connection() as conn:
        # Candado de sesión: con 2 procesos arrancando a la vez, solo uno crea las tablas.
        conn.execute("SELECT pg_advisory_lock(190)")
        try:
            conn.execute(SCHEMA.read_text(encoding="utf-8"))
        finally:
            conn.execute("SELECT pg_advisory_unlock(190)")
