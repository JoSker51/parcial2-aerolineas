#!/bin/bash
# User-data de la EC2 (Amazon Linux 2023): PostgreSQL local + API/frontend como servicio systemd.
# __BUCKET__ y __ATHENA_OUTPUT__ los reemplaza infra/04_ec2.sh.
set -euxo pipefail

dnf install -y postgresql15-server python3.11 python3.11-pip tar
postgresql-setup --initdb
cat > /var/lib/pgsql/data/pg_hba.conf <<'EOF'
local   all  postgres                 peer
local   all  all                      scram-sha-256
host    all  all      127.0.0.1/32    scram-sha-256
host    all  all      ::1/128         scram-sha-256
EOF
# Solo escucha en localhost: la base NO es alcanzable desde internet (el SG tampoco abre 5432).
sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" /var/lib/pgsql/data/postgresql.conf
systemctl enable --now postgresql

# Contraseña generada en la propia máquina: nunca pasa por el repo ni por la consola.
DB_PASS="$(openssl rand -hex 16)"
sudo -u postgres psql -c "CREATE USER airline WITH PASSWORD '${DB_PASS}';"
sudo -u postgres createdb -O airline airline

cat > /etc/airline.env <<EOF
DATABASE_URL=postgresql://airline:${DB_PASS}@localhost:5432/airline
AWS_REGION=us-east-1
ATHENA_DATABASE=airline_analytics
ATHENA_WORKGROUP=primary
ATHENA_OUTPUT=__ATHENA_OUTPUT__
EOF
chmod 600 /etc/airline.env

mkdir -p /opt/airline
aws s3 cp s3://__BUCKET__/code/backend.tar.gz /opt/airline/backend.tar.gz
tar -xzf /opt/airline/backend.tar.gz -C /opt/airline
python3.11 -m venv /opt/airline/venv
/opt/airline/venv/bin/pip install -q -r /opt/airline/backend/requirements.txt

cat > /etc/systemd/system/airline.service <<'EOF'
[Unit]
Description=Airline API + frontend (parcial 2)
After=network-online.target postgresql.service
Requires=postgresql.service

[Service]
EnvironmentFile=/etc/airline.env
WorkingDirectory=/opt/airline/backend
# 2 procesos = 2 vCPU de la t3.small.
ExecStart=/opt/airline/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
User=nobody

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now airline
