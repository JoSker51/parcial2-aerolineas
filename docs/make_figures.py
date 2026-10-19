"""Genera las figuras del documento: diagrama de arquitectura y capturas reales del frontend.

Uso: python docs/make_figures.py http://IP:8000
"""
import pathlib
import sys
import uuid

import httpx
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "diagramas"
BASE = sys.argv[1].rstrip("/")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 800}, device_scale_factor=2)
    pg.goto((OUT / "arquitectura.html").as_uri())
    pg.locator("#c").screenshot(path=str(OUT / "arquitectura.png"))

    # Flujo del cliente sobre un vuelo de demostración creado con el endpoint de administración.
    fid = "DEMO" + uuid.uuid4().hex[:6].upper()
    httpx.post(f"{BASE}/admin/flights", json={"flight_id": fid, "route": "SMR-CTG", "flight_date": "2031-06-10",
                                               "capacity": 180, "price_cents": 154000}, timeout=15)
    pg = b.new_page(viewport={"width": 900, "height": 700}, device_scale_factor=2)
    pg.goto(BASE + "/")
    pg.get_by_test_id("search-origin").fill("SMR")
    pg.get_by_test_id("search-destination").fill("CTG")
    pg.get_by_test_id("search-date").fill("2031-06-10")
    pg.get_by_test_id("search-submit").click()
    pg.get_by_test_id("flight-row").first.wait_for()
    pg.screenshot(path=str(OUT / "cliente-busqueda.png"))
    pg.get_by_test_id("flight-row").first.get_by_test_id("reserve-button").click()
    pg.get_by_test_id("passenger-name").fill("Ana Gómez")
    pg.get_by_test_id("confirm-submit").click()
    pg.get_by_test_id("confirmation-id").wait_for()
    pg.screenshot(path=str(OUT / "cliente-confirmacion.png"))

    pg = b.new_page(viewport={"width": 900, "height": 520}, device_scale_factor=2)
    pg.goto(BASE + "/manager")
    pg.get_by_test_id("manager-route").fill("SMR-CTG")
    pg.get_by_test_id("manager-month").fill("2024-01")
    pg.get_by_test_id("manager-load").click()
    pg.get_by_test_id("occupancy-value").wait_for()
    pg.screenshot(path=str(OUT / "panel-gerencial.png"))
    b.close()
print("ok")
