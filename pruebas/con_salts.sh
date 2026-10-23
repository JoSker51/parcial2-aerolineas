#!/usr/bin/env bash
# Simula la copia secreta del docente: corre R7 y R9 del harness con varios probe_salt distintos.
# Uso: bash pruebas/con_salts.sh <carpeta-de-una-copia-limpia-del-harness> [python]
# Modifica SOLO el thresholds.yaml de esa copia (nunca el del harness que se entrega).
set -uo pipefail
H="${1:?carpeta del harness}"
PY="${2:-python}"
cp "$H/thresholds.yaml" "$H/thresholds.yaml.orig"
for SALT in 7 1234 98765 424242 2026; do
  sed -i "s/^probe_salt: .*/probe_salt: ${SALT}/" "$H/thresholds.yaml"
  OUT=$(cd "$H" && HARNESS_REPORT="report-salt-${SALT}" "$PY" -m pytest -q -p no:warnings \
          tests/test_analytics.py tests/test_frontend.py -k "endpoint_matches or manager_panel" 2>&1 | tail -1)
  echo "salt=${SALT}: ${OUT}"
  grep -h "evidence" "$H/report-salt-${SALT}.md" | sed 's/^/    /'
done
mv "$H/thresholds.yaml.orig" "$H/thresholds.yaml"
