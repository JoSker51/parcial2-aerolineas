-- Esquema transaccional del parcial 2. Deliberadamente mínimo: el contrato A.1 solo necesita
-- vuelos con capacidad y reservas confirmadas. El modelo de 26 tablas del parcial 1 (holds,
-- itinerarios, pagos, B2B) no lo exige ningún requisito de este parcial.

CREATE TABLE IF NOT EXISTS flight (
    flight_id    TEXT PRIMARY KEY,
    route        TEXT    NOT NULL,                 -- 'AAA-BBB'
    origin       TEXT    NOT NULL,                 -- derivados de route para indexar la búsqueda
    destination  TEXT    NOT NULL,
    flight_date  DATE    NOT NULL,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    seats_sold   INTEGER NOT NULL DEFAULT 0,
    price_cents  BIGINT  NOT NULL CHECK (price_cents > 0),
    -- Última línea de defensa contra la sobreventa (igual que ck_inventory_no_oversell del
    -- parcial 1): aunque un bug saltara el bloqueo, el motor abortaría la transacción.
    CONSTRAINT ck_no_oversell CHECK (seats_sold BETWEEN 0 AND capacity)
);

-- R1: la búsqueda filtra siempre por (origen, destino, fecha).
CREATE INDEX IF NOT EXISTS ix_flight_search ON flight (origin, destination, flight_date);

CREATE TABLE IF NOT EXISTS reservation (
    reservation_id TEXT PRIMARY KEY,
    flight_id      TEXT        NOT NULL REFERENCES flight (flight_id),
    passenger_name TEXT        NOT NULL,
    fare_class     TEXT        NOT NULL CHECK (fare_class IN ('ECONOMY', 'BUSINESS')),
    status         TEXT        NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN ('CONFIRMED', 'CANCELLED')),
    price_cents    BIGINT      NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reservation_flight ON reservation (flight_id);
