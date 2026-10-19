"""API del sistema de reservas (contrato A.1) + las dos páginas del frontend (A.3).

Un solo proceso sirve API y páginas estáticas: un único puerto, sin CORS y sin un segundo
servidor que mantener (decisión de hosting, pilar de optimización de costos).
"""
import datetime as dt
import pathlib
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from psycopg import errors as pg_errors
from pydantic import BaseModel, Field

from app import analytics, booking
from app.db import init_schema, pool

STATIC = pathlib.Path(__file__).resolve().parent / "static"
ROUTE_RE = r"^[A-Z]{3}-[A-Z]{3}$"
IATA_RE = r"^[A-Z]{3}$"
MONTH_RE = r"^\d{4}-(0[1-9]|1[0-2])$"


@asynccontextmanager
async def lifespan(_app):
    pool.open(wait=True)
    init_schema()
    yield
    pool.close()


app = FastAPI(title="Airline reservations - parcial 2", lifespan=lifespan)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message})


@app.exception_handler(booking.NotFound)
async def _not_found(_req, exc):
    return _error(404, "NOT_FOUND", str(exc))


@app.exception_handler(booking.Conflict)
async def _conflict(_req, exc):
    return _error(409, "SEAT_UNAVAILABLE", str(exc))


@app.exception_handler(pg_errors.LockNotAvailable)
async def _lock_timeout(_req, exc):
    # Si alguna vez venciera lock_timeout, se responde 409 y no 500: el contrato exige que
    # "sin sillas" o "inventario ocupado" sea un conflicto, nunca un error del servidor.
    return _error(409, "INVENTORY_BUSY", "flight inventory is busy, retry")


@app.exception_handler(analytics.AthenaError)
async def _athena_error(_req, exc):
    return _error(502, "ANALYTICS_UNAVAILABLE", str(exc))


# --------------------------------------------------------------------------- modelos
class FlightIn(BaseModel):
    flight_id: str = Field(min_length=1, max_length=64)
    route: str = Field(pattern=ROUTE_RE)
    flight_date: dt.date
    capacity: int = Field(gt=0)
    price_cents: int = Field(gt=0)


class ReservationIn(BaseModel):
    flight_id: str = Field(min_length=1)
    passenger_name: str = Field(min_length=1, max_length=200)
    fare_class: Literal["ECONOMY", "BUSINESS"]


# ------------------------------------------------------------------------------- API
@app.get("/health")
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/admin/flights", status_code=201)
def create_flight(body: FlightIn):
    return booking.create_flight(body.flight_id, body.route, body.flight_date, body.capacity, body.price_cents)


@app.get("/flights/search")
def search(origin: str = Query(pattern=IATA_RE), destination: str = Query(pattern=IATA_RE),
           date: dt.date = Query()):
    return booking.search_flights(origin, destination, date)


@app.post("/reservations", status_code=201)
def create_reservation(body: ReservationIn):
    return booking.create_reservation(body.flight_id, body.passenger_name, body.fare_class)


@app.get("/reservations/{reservation_id}")
def get_reservation(reservation_id: str):
    return booking.get_reservation(reservation_id)


@app.get("/analytics/occupancy")
def occupancy(route: str = Query(pattern=ROUTE_RE), month: str = Query(pattern=MONTH_RE)):
    r = analytics.occupancy(route, month)
    if r is None:
        return _error(404, "NOT_FOUND", f"no data for {route} {month}")
    return r


# --------------------------------------------------------------------------- frontend
@app.get("/", include_in_schema=False)
def customer_page():
    return FileResponse(STATIC / "index.html")


@app.get("/manager", include_in_schema=False)
def manager_page():
    return FileResponse(STATIC / "manager.html")
