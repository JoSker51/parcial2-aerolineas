#!/usr/bin/env bash
# Crea la base y las dos tablas en el Glue Data Catalog ejecutando athena/ddl.sql (R5).
# Uso: bash infra/03_athena.sh
source "$(dirname "$0")/env.sh"

run_sql() {
  local qid state
  qid="$(aws athena start-query-execution --query-string "$1" --work-group primary \
          --result-configuration "OutputLocation=${ATHENA_OUTPUT}" \
          --query QueryExecutionId --output text | tr -d '\r')"
  while true; do
    state="$(aws athena get-query-execution --query-execution-id "$qid" \
              --query QueryExecution.Status.State --output text | tr -d '\r')"
    case "$state" in
      SUCCEEDED) echo "  ok"; return 0 ;;
      FAILED|CANCELLED)
        aws athena get-query-execution --query-execution-id "$qid" \
          --query QueryExecution.Status.StateChangeReason --output text; return 1 ;;
    esac
    sleep 1
  done
}

# Quita comentarios, reemplaza ${BUCKET} (pero no ${month}, que es de Athena) y separa por ';'.
sed -e 's/--.*$//' -e "s/\${BUCKET}/${BUCKET}/g" athena/ddl.sql | tr '\n' ' ' | tr ';' '\n' |
while IFS= read -r stmt; do
  stmt="$(echo "$stmt" | sed 's/^ *//;s/ *$//')"
  [ -z "$stmt" ] && continue
  echo ">> ${stmt:0:70}..."
  run_sql "$stmt"
done

echo "Verificación:"
run_sql "SELECT count(*) FROM ${ATHENA_DB}.reservations_curated"
