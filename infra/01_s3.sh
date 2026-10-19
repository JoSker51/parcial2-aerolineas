#!/usr/bin/env bash
# Crea el bucket y sube: datos crudos (completos y muestra), el job de PySpark.
# Uso: bash infra/01_s3.sh
source "$(dirname "$0")/env.sh"

aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || aws s3api create-bucket --bucket "$BUCKET"
# Sin acceso público: nada de este bucket se sirve a internet.
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
# Los resultados de Athena son desechables: se borran solos a los 7 días (costo S3 ~ 0).
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
  '{"Rules":[{"ID":"athena-results-7d","Status":"Enabled","Filter":{"Prefix":"athena-results/"},"Expiration":{"Days":7}},{"ID":"emr-logs-14d","Status":"Enabled","Filter":{"Prefix":"emr-logs/"},"Expiration":{"Days":14}}]}'

aws s3 cp data/raw/flights.csv        "s3://${BUCKET}/raw/full/flights.csv"
aws s3 cp data/raw/reservations.csv   "s3://${BUCKET}/raw/full/reservations.csv"
if [ -f data/raw-sample/flights.csv ]; then
  aws s3 cp data/raw-sample/flights.csv      "s3://${BUCKET}/raw/sample/flights.csv"
  aws s3 cp data/raw-sample/reservations.csv "s3://${BUCKET}/raw/sample/reservations.csv"
fi
aws s3 cp emr/curate.py "s3://${BUCKET}/code/curate.py"
aws s3 ls "s3://${BUCKET}/" --recursive --human-readable
