"""Vuelos y reservas: el camino transaccional (R1, R2, R3).

Control de sobreventa (R2) = DEC-4 del parcial 1, reducido a un solo tramo:
  1. BEGIN
  2. SELECT ... FROM flight WHERE flight_id = %s FOR UPDATE   -> bloquea la fila del vuelo
  3. si seats_sold >= capacity -> 409 (rollback)
  4. UPDATE seats_sold = seats_sold + 1 ; INSERT reservation
  5. COMMIT                                                  -> libera el bloqueo

Las N peticiones simultáneas por la última silla se serializan sobre esa única fila. La primera
gana; las demás, al obtener el bloqueo, ya leen seats_sold = capacity y reciben 409. Es síncrono,
determinista y sin reintentos. Además, la CHECK ck_no_oversell respalda la regla desde el motor.
"""
import datetime as dt
import uuid

from psycopg import errors as pg_errors

from app.config import settings
from app.db import pool


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def create_flight(flight_id: str, route: str, flight_date: dt.date, capacity: int, price_cents: int) -> dict:
    origin, destination = route.split("-")
    with pool.connection() as conn:
        try:
            conn.execute(
                "INSERT INTO flight (flight_id, route, origin, destination, flight_date, capacity, price_cents) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (flight_id, route, origin, destination, flight_date, capacity, price_cents))
        except pg_errors.UniqueViolation:
            raise Conflict(f"flight {flight_id} already exists")
    return {"flight_id": flight_id, "route": route, "flight_date": flight_date.isoformat(),
            "capacity": capacity, "price_cents": price_cents}


def search_flights(origin: str, destination: str, flight_date: dt.date) -> list[dict]:
    # Lectura simple sobre el índice ix_flight_search; no toma bloqueos, así que nunca espera
    # a una reserva en curso (la disponibilidad se verifica de verdad al reservar).
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT flight_id, route, flight_date, capacity - seats_sold AS seats_available, price_cents "
            "FROM flight WHERE origin = %s AND destination = %s AND flight_date = %s "
            "AND seats_sold < capacity ORDER BY flight_id",
            (origin, destination, flight_date)).fetchall()
    for r in rows:
        r["flight_date"] = r["flight_date"].isoformat()
    return rows


def create_reservation(flight_id: str, passenger_name: str, fare_class: str) -> dict:
    reservation_id = uuid.uuid4().hex
    with pool.connection() as conn:
        with conn.transaction():
            # SET LOCAL: el límite aplica solo a esta transacción, no contamina la conexión del pool.
            conn.execute(f"SET LOCAL lock_timeout = {int(settings.lock_timeout_ms)}")
            f = conn.execute(
                "SELECT capacity, seats_sold, price_cents FROM flight WHERE flight_id = %s FOR UPDATE",
                (flight_id,)).fetchone()
            if f is None:
                raise NotFound(f"flight {flight_id} not found")
            if f["seats_sold"] >= f["capacity"]:
                raise Conflict("no seats left")
            conn.execute("UPDATE flight SET seats_sold = seats_sold + 1 WHERE flight_id = %s", (flight_id,))
            conn.execute(
                "INSERT INTO reservation (reservation_id, flight_id, passenger_name, fare_class, price_cents) "
                "VALUES (%s, %s, %s, %s, %s)",
                (reservation_id, flight_id, passenger_name, fare_class, f["price_cents"]))
    return {"reservation_id": reservation_id, "flight_id": flight_id,
            "status": "CONFIRMED", "passenger_name": passenger_name}


def get_reservation(reservation_id: str) -> dict:
    with pool.connection() as conn:
        r = conn.execute(
            "SELECT reservation_id, flight_id, status, passenger_name, fare_class "
            "FROM reservation WHERE reservation_id = %s", (reservation_id,)).fetchone()
    if r is None:
        raise NotFound(f"reservation {reservation_id} not found")
    return r
