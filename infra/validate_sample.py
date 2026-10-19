"""Compara la salida de EMR sobre la MUESTRA con el oráculo del harness (mismo seed, mismas filas).

Uso (desde la raíz del repo, con el venv del harness):
    python infra/validate_sample.py s3://BUCKET/curated-sample 100000

Descarga los Parquet con boto3 y verifica: conteo total, filas por mes, ingresos confirmados por mes
y la tabla de métricas completa. Si todo cuadra, el job está listo para el dataset completo.
"""
import io
import os
import sys

import boto3
import pandas as pd
import pyarrow.parquet as pq

HARNESS = os.path.join(os.path.dirname(__file__), "..", "..", "parcial2-harness-estudiantes", "parcial2-harness")
sys.path.insert(0, os.path.abspath(HARNESS))
from airline_data.oracle import load_truth  # noqa: E402


def read_prefix(s3, uri):
    bucket, prefix = uri[5:].split("/", 1)
    frames = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            if not o["Key"].endswith(".parquet"):
                continue
            df = pq.read_table(io.BytesIO(s3.get_object(Bucket=bucket, Key=o["Key"])["Body"].read())).to_pandas()
            month = [p[6:] for p in o["Key"].split("/") if p.startswith("month=")]
            if month:
                df["month"] = month[0]
            frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main():
    out, rows = sys.argv[1].rstrip("/"), int(sys.argv[2])
    s3 = boto3.client("s3")
    truth = load_truth(190, rows)
    det = read_prefix(s3, f"{out}/reservations_curated/")
    met = read_prefix(s3, f"{out}/route_month_metrics/")
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("OK   " if cond else "FAIL ") + name, detail)

    check("columnas detalle", list(det.columns[:6]) == ["reservation_id", "flight_id", "route", "fare_class", "price_cents", "status"], list(det.columns))
    check("filas detalle", len(det) == truth.row_count, f"{len(det)} vs {truth.row_count}")
    check("24 meses", det["month"].nunique() == 24)
    check("filas por mes", det.groupby("month").size().to_dict() == truth.partition_counts)
    conf = det[det.status == "CONFIRMED"]
    check("ingresos por mes", all(int(conf[conf.month == m].price_cents.sum()) == truth.confirmed_revenue(m)
                                  for m in truth.partition_counts))
    exp = truth.metrics.set_index(["route", "month"]).sort_index()
    got = met.set_index(["route", "month"]).sort_index()
    check("filas métricas", len(got) == len(exp), f"{len(got)} vs {len(exp)}")
    for c in ["seats_capacity", "seats_sold", "revenue_cents", "cancellations"]:
        check(f"métrica {c}", (got[c].astype("int64") == exp[c]).all())
    check("métrica occupancy", ((got.occupancy - exp.occupancy).abs() < 1e-9).all())
    print("\nRESULTADO:", "TODO CUADRA" if ok else "HAY DIFERENCIAS")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
