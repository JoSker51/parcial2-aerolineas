-- Tablas del contrato A.2, creadas con DDL de Athena: quedan registradas en el Glue Data
-- Catalog sin crawler (un crawler cobra DPU-hora para descubrir un esquema que ya conocemos).
-- ${BUCKET} lo reemplaza infra/03_athena.sh. Una sentencia por bloque separado con ';'.

CREATE DATABASE IF NOT EXISTS airline_analytics;

DROP TABLE IF EXISTS airline_analytics.reservations_curated;

-- Partition projection: Athena calcula las 24 particiones desde estas propiedades, sin
-- MSCK REPAIR ni registrar particiones tras cada corrida de EMR. Un WHERE month = 'X'
-- lee solo la carpeta month=X/ (R6).
CREATE EXTERNAL TABLE airline_analytics.reservations_curated (
    reservation_id string,
    flight_id      string,
    route          string,
    fare_class     string,
    price_cents    bigint,
    status         string
)
PARTITIONED BY (month string)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/curated/reservations_curated/'
TBLPROPERTIES (
    'classification'             = 'parquet',
    'projection.enabled'         = 'true',
    'projection.month.type'      = 'date',
    'projection.month.format'    = 'yyyy-MM',
    'projection.month.range'     = '2023-01,2024-12',
    'projection.month.interval'  = '1',
    'projection.month.interval.unit' = 'MONTHS',
    'storage.location.template'  = 's3://${BUCKET}/curated/reservations_curated/month=${month}/'
);

DROP TABLE IF EXISTS airline_analytics.route_month_metrics;

-- 336 filas (14 rutas x 24 meses): no vale la pena particionarla.
CREATE EXTERNAL TABLE airline_analytics.route_month_metrics (
    route          string,
    month          string,
    seats_capacity bigint,
    seats_sold     bigint,
    occupancy      double,
    revenue_cents  bigint,
    bookings       bigint,
    cancellations  bigint
)
STORED AS PARQUET
LOCATION 's3://${BUCKET}/curated/route_month_metrics/'
TBLPROPERTIES ('classification' = 'parquet');
