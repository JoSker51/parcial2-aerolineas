"""Configuración por variables de entorno (nada de credenciales en el código).

En la EC2 las credenciales de AWS NO se configuran: boto3 las toma del perfil de instancia
(LabInstanceProfile -> LabRole), que rota las claves solo.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://airline:airline@localhost:5432/airline")
    # Pool por proceso de uvicorn. Con 2 procesos x 10 = 20 conexiones, muy por debajo del
    # max_connections de PostgreSQL (100). Las peticiones que no consiguen conexión esperan
    # en la cola del pool en vez de fallar: bajo la ráfaga de R2 eso da 409/201, nunca 5xx.
    pool_min: int = int(os.getenv("POOL_MIN", "2"))
    pool_max: int = int(os.getenv("POOL_MAX", "10"))
    pool_timeout_s: float = float(os.getenv("POOL_TIMEOUT_S", "30"))
    # Espera máxima por el bloqueo de la fila del vuelo. Holgada a propósito: si venciera,
    # una petición que sí tenía silla recibiría error y R2 contaría menos de K reservas.
    lock_timeout_ms: int = int(os.getenv("LOCK_TIMEOUT_MS", "10000"))

    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    athena_database: str = os.getenv("ATHENA_DATABASE", "airline_analytics")
    athena_workgroup: str = os.getenv("ATHENA_WORKGROUP", "primary")
    athena_output: str = os.getenv("ATHENA_OUTPUT", "")
    metrics_table: str = os.getenv("METRICS_TABLE", "route_month_metrics")
    athena_timeout_s: float = float(os.getenv("ATHENA_TIMEOUT_S", "9"))


settings = Settings()
