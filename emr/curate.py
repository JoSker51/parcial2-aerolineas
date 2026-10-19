"""Job batch de EMR (PySpark): limpia el histórico crudo y produce las dos tablas del contrato.

Entrada  (CSV crudo, generado con el seed del equipo):
    <raw>/flights.csv        flight_id, route, flight_date, capacity
    <raw>/reservations.csv   reservation_id, flight_id, fare_class, price_cents, status, days_before_departure

Salida (Parquet):
    <curated>/month=YYYY-MM/...   reservations_curated, una partición por mes del vuelo
    <metrics>/...                 route_month_metrics, una fila por (ruta, mes)

Reglas de limpieza (sección 4.1 del enunciado), en el mismo orden que el oráculo del harness:
    C1 route: quitar TODO espacio en blanco y pasar a mayúsculas   (' bog - mde ' -> 'BOG-MDE')
    C2 status: quitar espacios de los extremos y pasar a mayúsculas
    C3 conservar solo status CONFIRMED o CANCELLED
    C4 descartar price_cents nulo o <= 0
    C5 descartar reservation_id duplicados conservando la PRIMERA aparición en el archivo

Uso (paso de EMR):
    spark-submit curate.py --raw s3://BUCKET/raw --curated s3://BUCKET/curated/reservations_curated \
                           --metrics s3://BUCKET/curated/route_month_metrics
"""
import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType

FLIGHTS_SCHEMA = StructType([
    StructField("flight_id", LongType()),
    StructField("route", StringType()),
    StructField("flight_date", StringType()),
    StructField("capacity", LongType()),
])

# price_cents viene vacío en algunas filas inválidas: con esquema explícito el CSV lo lee como NULL.
RESERVATIONS_SCHEMA = StructType([
    StructField("reservation_id", LongType()),
    StructField("flight_id", LongType()),
    StructField("fare_class", StringType()),
    StructField("price_cents", LongType()),
    StructField("status", StringType()),
    StructField("days_before_departure", LongType()),
])

CURATED_COLUMNS = ["reservation_id", "flight_id", "route", "fare_class", "price_cents", "status"]


def clean_flights(flights):
    # C1. regexp \s+ (no solo trim): la ruta sucia trae espacios en el medio, como 'BOG - MDE'.
    return (flights
            .withColumn("route", F.upper(F.regexp_replace("route", r"\s+", "")))
            .withColumn("month", F.substring("flight_date", 1, 7)))


def clean_reservations(res):
    # Se numera cada fila en el orden del archivo ANTES de filtrar, para que C5 conserve la primera.
    # monotonically_increasing_id crece con el número de partición y con la posición dentro de
    # ella, y las particiones de un CSV siguen el orden de los bytes del archivo.
    res = res.withColumn("_row", F.monotonically_increasing_id())
    # C2. Se quita todo espacio de los extremos (equivale a str.strip() de Python, no solo ' ').
    res = res.withColumn("status", F.upper(F.regexp_replace("status", r"^\s+|\s+$", "")))
    res = res.filter(F.col("status").isin("CONFIRMED", "CANCELLED"))               # C3
    res = res.filter(F.col("price_cents").isNotNull() & (F.col("price_cents") > 0))  # C4
    first = Window.partitionBy("reservation_id").orderBy("_row")                       # C5
    return (res.withColumn("_rn", F.row_number().over(first))
               .filter(F.col("_rn") == 1)
               .drop("_rn", "_row"))


def build_curated(flights_clean, res_clean):
    # La reserva cruda no trae ruta: ruta y mes salen del vuelo (ya limpio con C1).
    f = flights_clean.select("flight_id", "route", "month")
    d = res_clean.join(f, on="flight_id", how="inner")
    return d.select(
        F.col("reservation_id").cast("string").alias("reservation_id"),
        F.col("flight_id").cast("string").alias("flight_id"),
        "route", "fare_class",
        F.col("price_cents").cast("bigint").alias("price_cents"),
        "status", "month")


def build_metrics(flights_clean, curated):
    # La capacidad sale de TODOS los vuelos del mes, no solo de los que tienen reservas.
    cap = flights_clean.groupBy("route", "month").agg(F.sum("capacity").cast("bigint").alias("seats_capacity"))
    conf = F.col("status") == "CONFIRMED"
    agg = curated.groupBy("route", "month").agg(
        F.sum(F.when(conf, 1).otherwise(0)).cast("bigint").alias("seats_sold"),
        F.sum(F.when(conf, F.col("price_cents")).otherwise(0)).cast("bigint").alias("revenue_cents"),
        # Contrato A.2: bookings cuenta solo CONFIRMED (las canceladas no son sillas vendidas).
        F.sum(F.when(conf, 1).otherwise(0)).cast("bigint").alias("bookings"),
        F.sum(F.when(F.col("status") == "CANCELLED", 1).otherwise(0)).cast("bigint").alias("cancellations"))
    m = cap.join(agg, on=["route", "month"], how="left").fillna(0)
    m = m.withColumn("occupancy", (F.col("seats_sold") / F.col("seats_capacity")).cast("double"))
    return m.select("route", "month", "seats_capacity", "seats_sold", "occupancy",
                    "revenue_cents", "bookings", "cancellations")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--curated", required=True)
    ap.add_argument("--metrics", required=True)
    a = ap.parse_args()

    spark = SparkSession.builder.appName("airline-curate").getOrCreate()
    read = spark.read.option("header", "true").option("mode", "PERMISSIVE")
    flights = clean_flights(read.schema(FLIGHTS_SCHEMA).csv(f"{a.raw.rstrip('/')}/flights.csv"))
    res = clean_reservations(read.schema(RESERVATIONS_SCHEMA).csv(f"{a.raw.rstrip('/')}/reservations.csv"))

    curated = build_curated(flights, res).cache()
    # repartition("month"): un archivo por partición. Pocos archivos grandes = menos peticiones
    # a S3 y menos overhead de Athena que cientos de archivos pequeños.
    (curated.repartition("month")
            .write.mode("overwrite").partitionBy("month").parquet(a.curated))

    metrics = build_metrics(flights, curated)
    metrics.coalesce(1).write.mode("overwrite").parquet(a.metrics)

    print(f"curated rows: {curated.count()}  metric rows: {metrics.count()}")
    spark.stop()


if __name__ == "__main__":
    main()
