"""Prueba el endpoint de ocupación con TODOS los pares (ruta, mes) del seed, no solo los 5 del harness.

El docente elige sus pares con un probe_salt secreto: si los 336 pares responden bien, cualquier
salt pasa R7 y R9.

Uso: python pruebas/todos_los_pares.py <carpeta-del-harness> http://IP:8000
"""
import concurrent.futures as cf
import sys
import time

import httpx

sys.path.insert(0, sys.argv[1])
from airline_data.oracle import load_truth  # noqa: E402

BASE = sys.argv[2].rstrip("/")
TOL = 0.001          # misma tolerancia relativa que el harness (thresholds.yaml)
LIMIT_S = 10         # límite de R7


def check(row):
    route, month = row.route, row.month
    t0 = time.perf_counter()
    try:
        r = httpx.get(f"{BASE}/analytics/occupancy", params={"route": route, "month": month}, timeout=20)
    except Exception as e:  # noqa: BLE001
        return route, month, None, f"error de red: {e}"
    el = time.perf_counter() - t0
    if r.status_code != 200:
        return route, month, el, f"HTTP {r.status_code}"
    b = r.json()
    if abs(float(b["occupancy"]) - row.occupancy) > TOL * row.occupancy:
        return route, month, el, f"occupancy {b['occupancy']} vs {row.occupancy}"
    if int(b["seats_sold"]) != row.seats_sold or int(b["seats_capacity"]) != row.seats_capacity:
        return route, month, el, "seats_sold/seats_capacity no coinciden"
    if el > LIMIT_S:
        return route, month, el, f"tardó {el:.1f} s"
    return route, month, el, None


def main():
    truth = load_truth(190, 2_000_000)
    rows = list(truth.metrics.itertuples(index=False))
    print(f"Probando {len(rows)} pares contra {BASE} ...")
    t0 = time.time()
    # 6 en paralelo: por debajo del límite de consultas concurrentes de Athena en el laboratorio.
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(check, rows))
    lat = sorted(el for _, _, el, _ in results if el is not None)
    fails = [(r, m, e) for r, m, _, e in results if e]
    print(f"Terminó en {time.time() - t0:.0f} s · latencia p50={lat[len(lat)//2]:.2f}s "
          f"p95={lat[int(.95*len(lat))-1]:.2f}s max={lat[-1]:.2f}s")
    print(f"OK: {len(rows) - len(fails)}/{len(rows)}")
    for r, m, e in fails[:20]:
        print(f"  FALLA {r} {m}: {e}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
