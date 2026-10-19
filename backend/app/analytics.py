"""Ocupación por ruta y mes, leída de Athena en cada petición (R7, R9).

Por qué Athena y no la base transaccional: la analítica nunca toca PostgreSQL, así que un
gerente consultando no puede frenar una reserva (separación de cargas, R1/R2).

La consulta va contra route_month_metrics (336 filas ya agregadas por EMR), no contra el
detalle de 2 M filas: escanea unos pocos KB, Athena cobra el mínimo de 10 MB por consulta
(~US$0.00005) y responde en 1-3 s, dentro del límite de 10 s de R7.

La ruta y el mes viajan como parámetros de ejecución (ExecutionParameters), nunca concatenados
en el SQL: sin inyección posible aunque alguien envíe una ruta maliciosa.
"""
import time

import boto3

from app.config import settings

_athena = boto3.client("athena", region_name=settings.aws_region)

SQL = (f"SELECT route, month, seats_sold, seats_capacity, occupancy "
       f"FROM {settings.metrics_table} WHERE route = ? AND month = ?")


class AthenaError(Exception):
    pass


def occupancy(route: str, month: str) -> dict | None:
    kw = dict(QueryString=SQL,
              QueryExecutionContext={"Database": settings.athena_database},
              WorkGroup=settings.athena_workgroup,
              ExecutionParameters=[f"'{route}'", f"'{month}'"])
    if settings.athena_output:
        kw["ResultConfiguration"] = {"OutputLocation": settings.athena_output}
    qid = _athena.start_query_execution(**kw)["QueryExecutionId"]

    deadline = time.monotonic() + settings.athena_timeout_s
    delay = 0.1
    while True:
        st = _athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if st["State"] == "SUCCEEDED":
            break
        if st["State"] in ("FAILED", "CANCELLED"):
            raise AthenaError(st.get("StateChangeReason", st["State"]))
        if time.monotonic() > deadline:
            _athena.stop_query_execution(QueryExecutionId=qid)
            raise AthenaError(f"Athena query {qid} timed out")
        time.sleep(delay)
        delay = min(delay * 1.5, 0.5)

    rows = _athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    if len(rows) < 2:          # la fila 0 es el encabezado
        return None
    v = [c.get("VarCharValue") for c in rows[1]["Data"]]
    return {"route": v[0], "month": v[1], "occupancy": float(v[4]),
            "seats_sold": int(v[2]), "seats_capacity": int(v[3])}
