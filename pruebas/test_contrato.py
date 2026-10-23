"""Pruebas extra del contrato A.1/A.3 que el harness no cubre, por si el docente agrega las suyas.

Uso: BASE_URL=http://IP:8000 python -m pytest pruebas/test_contrato.py -q
"""
import datetime as dt
import os
import threading
import time
import uuid

import httpx
import pytest

BASE = os.environ.get("BASE_URL", "http://100.60.245.136:8000").rstrip("/")
ROUTE = "CUC-CTG"


def mk_flight(capacity=5, date="2032-02-02", route=ROUTE, price=99000):
    fid = "X" + uuid.uuid4().hex[:10].upper()
    body = {"flight_id": fid, "route": route, "flight_date": date, "capacity": capacity, "price_cents": price}
    r = httpx.post(f"{BASE}/admin/flights", json=body, timeout=15)
    assert r.status_code == 201, r.text
    return fid, body, r


def reserve(client, fid, name="Prueba", fare="ECONOMY"):
    return client.post(f"{BASE}/reservations", json={"flight_id": fid, "passenger_name": name, "fare_class": fare})


# ----------------------------------------------------------------------------- /health
def test_health():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200


# ---------------------------------------------------------------------- /admin/flights
def test_admin_devuelve_el_mismo_cuerpo():
    _, body, r = mk_flight()
    assert r.json() == body


def test_admin_duplicado_es_409():
    fid, body, _ = mk_flight()
    assert httpx.post(f"{BASE}/admin/flights", json=body, timeout=15).status_code == 409


@pytest.mark.parametrize("cambio", [{"route": "BOGMDE"}, {"capacity": 0}, {"price_cents": -1}, {"flight_date": "2032-13-01"}])
def test_admin_datos_invalidos_no_son_5xx(cambio):
    body = {"flight_id": "BAD" + uuid.uuid4().hex[:6], "route": ROUTE, "flight_date": "2032-01-01",
            "capacity": 3, "price_cents": 1000} | cambio
    r = httpx.post(f"{BASE}/admin/flights", json=body, timeout=15)
    assert 400 <= r.status_code < 500


# ---------------------------------------------------------------------- /flights/search
def test_busqueda_forma_de_la_respuesta():
    fid, _, _ = mk_flight(capacity=7, date="2032-03-03")
    o, d = ROUTE.split("-")
    r = httpx.get(f"{BASE}/flights/search", params={"origin": o, "destination": d, "date": "2032-03-03"}, timeout=15)
    assert r.status_code == 200
    f = next(x for x in r.json() if x["flight_id"] == fid)
    assert set(f) >= {"flight_id", "route", "flight_date", "seats_available", "price_cents"}
    assert f["seats_available"] == 7 and f["route"] == ROUTE and f["flight_date"] == "2032-03-03"


def test_busqueda_sin_vuelos_es_lista_vacia():
    r = httpx.get(f"{BASE}/flights/search", params={"origin": "LET", "destination": "PSO", "date": "1999-01-01"}, timeout=15)
    assert r.status_code == 200 and r.json() == []


@pytest.mark.parametrize("params", [{"origin": "CUC", "destination": "CTG"},
                                    {"origin": "CUC", "destination": "CTG", "date": "no-es-fecha"},
                                    {"origin": "CUCUTA", "destination": "CTG", "date": "2032-03-03"}])
def test_busqueda_parametros_malos_es_422(params):
    assert httpx.get(f"{BASE}/flights/search", params=params, timeout=15).status_code == 422


def test_vuelo_lleno_desaparece_de_la_busqueda():
    fid, _, _ = mk_flight(capacity=1, date="2032-04-04")
    with httpx.Client(timeout=15) as c:
        assert reserve(c, fid).status_code == 201
    o, d = ROUTE.split("-")
    r = httpx.get(f"{BASE}/flights/search", params={"origin": o, "destination": d, "date": "2032-04-04"}, timeout=15)
    assert fid not in [x["flight_id"] for x in r.json()]


# ------------------------------------------------------------------------ /reservations
def test_reserva_forma_y_lectura():
    fid, _, _ = mk_flight()
    with httpx.Client(timeout=15) as c:
        r = reserve(c, fid, "María José Ñúñez", "BUSINESS")
        assert r.status_code == 201
        b = r.json()
        assert set(b) >= {"reservation_id", "flight_id", "status", "passenger_name"}
        assert b["status"] == "CONFIRMED" and b["passenger_name"] == "María José Ñúñez"
        g = c.get(f"{BASE}/reservations/{b['reservation_id']}")
        assert g.status_code == 200 and g.json()["reservation_id"] == b["reservation_id"]


def test_reserva_vuelo_inexistente_es_404():
    with httpx.Client(timeout=15) as c:
        assert reserve(c, "NO-EXISTE-" + uuid.uuid4().hex).status_code == 404


@pytest.mark.parametrize("body", [{"passenger_name": "A", "fare_class": "FIRST"},
                                  {"fare_class": "ECONOMY"},
                                  {"passenger_name": "", "fare_class": "ECONOMY"}])
def test_reserva_cuerpo_invalido_es_422(body):
    fid, _, _ = mk_flight()
    r = httpx.post(f"{BASE}/reservations", json={"flight_id": fid} | body, timeout=15)
    assert r.status_code == 422


def test_sin_sillas_es_409_secuencial():
    fid, _, _ = mk_flight(capacity=2)
    with httpx.Client(timeout=15) as c:
        codes = [reserve(c, fid).status_code for _ in range(4)]
    assert codes == [201, 201, 409, 409]


# ------------------------------------------------------- concurrencia más dura que R2
def _race(fid, n):
    barrier, codes = threading.Barrier(n), [None] * n
    clients = [httpx.Client(timeout=60) for _ in range(n)]

    def go(i):
        barrier.wait()
        try:
            codes[i] = reserve(clients[i], fid, f"C{i}").status_code
        except Exception:  # noqa: BLE001
            codes[i] = -1
    ths = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    [c.close() for c in clients]
    return codes


def test_100_simultaneas_por_1_silla():
    fid, _, _ = mk_flight(capacity=1)
    codes = _race(fid, 100)
    assert codes.count(201) == 1 and codes.count(409) == 99, sorted(set(codes))


def test_80_simultaneas_por_20_sillas_mientras_hay_analitica_y_busquedas():
    """Separación de cargas: la analítica y la búsqueda corriendo a la vez no rompen la reserva."""
    fid, _, _ = mk_flight(capacity=20, date="2032-05-05")
    stop, side_errors = threading.Event(), []

    def ruido():
        with httpx.Client(timeout=30) as c:
            while not stop.is_set():
                a = c.get(f"{BASE}/analytics/occupancy", params={"route": "SMR-CTG", "month": "2024-01"})
                s = c.get(f"{BASE}/flights/search", params={"origin": "CUC", "destination": "CTG", "date": "2032-05-05"})
                if a.status_code != 200 or s.status_code != 200:
                    side_errors.append((a.status_code, s.status_code))
    bg = [threading.Thread(target=ruido) for _ in range(3)]
    [t.start() for t in bg]
    time.sleep(1)
    codes = _race(fid, 80)
    stop.set()
    [t.join() for t in bg]
    assert codes.count(201) == 20 and codes.count(409) == 60, sorted(set(codes))
    assert not side_errors, side_errors[:5]


def test_busqueda_p95_con_50_clientes():
    """R1 con más del doble de concurrencia que el harness (50 en vez de 20)."""
    o, d = ROUTE.split("-")
    lat, lock = [], threading.Lock()

    def worker():
        with httpx.Client(timeout=20) as c:
            for _ in range(6):
                t0 = time.perf_counter()
                r = c.get(f"{BASE}/flights/search", params={"origin": o, "destination": d, "date": "2030-03-01"})
                with lock:
                    lat.append((time.perf_counter() - t0, r.status_code))
    ths = [threading.Thread(target=worker) for _ in range(50)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    times = sorted(t for t, _ in lat)
    assert all(code == 200 for _, code in lat)
    assert times[int(.95 * len(times)) - 1] <= 1.0, f"p95 {times[int(.95 * len(times)) - 1]:.3f}s"


# -------------------------------------------------------------- /analytics/occupancy
@pytest.mark.parametrize("params", [{"route": "SMR-CTG", "month": "2024-13"}, {"route": "smr ctg", "month": "2024-01"}, {"route": "SMR-CTG"}])
def test_analitica_parametros_malos_no_son_5xx(params):
    r = httpx.get(f"{BASE}/analytics/occupancy", params=params, timeout=20)
    assert 400 <= r.status_code < 500


def test_analitica_mes_fuera_de_rango_es_404():
    r = httpx.get(f"{BASE}/analytics/occupancy", params={"route": "SMR-CTG", "month": "2030-01"}, timeout=20)
    assert r.status_code == 404


# -------------------------------------------------------------------------- frontend
@pytest.mark.parametrize("path,ids", [
    ("/", ["search-origin", "search-destination", "search-date", "search-submit", "passenger-name", "confirm-submit", "confirmation-id"]),
    ("/manager", ["manager-route", "manager-month", "manager-load", "occupancy-value"])])
def test_paginas_tienen_todos_los_selectores(path, ids):
    html = httpx.get(BASE + path, timeout=15).text
    for i in ids:
        assert f'data-testid="{i}"' in html, i
    # flight-row y reserve-button se crean por JavaScript al mostrar resultados
    if path == "/":
        assert '"flight-row"' in html and '"reserve-button"' in html
