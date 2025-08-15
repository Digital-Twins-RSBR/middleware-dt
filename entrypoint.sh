#!/bin/sh
set -e

# Carrega .env se existir
if [ -f "/middleware-dt/.env" ]; then
	echo "Carregando variáveis de /middleware-dt/.env"
	set -a
	. /middleware-dt/.env
	set +a
fi

# Garante que SECRET_KEY exista no .env e no ambiente
ENV_FILE="/middleware-dt/.env"
if ! grep -q '^SECRET_KEY=' "$ENV_FILE" 2>/dev/null; then
	SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n' | tr -d '=+/')
	echo "SECRET_KEY=$SECRET_KEY" >> "$ENV_FILE"
	echo "[entrypoint] SECRET_KEY gerado e adicionado ao .env"
else
	SECRET_KEY=$(grep '^SECRET_KEY=' "$ENV_FILE" | cut -d'=' -f2-)
fi
export SECRET_KEY

echo "Aplicando migrações..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput || true

# Configura token do InfluxDB (opcional) via env
if [ -n "$INFLUXDB_TOKEN" ]; then
	echo "INFLUXDB_TOKEN definido (****)."
else
	echo "INFLUXDB_TOKEN não definido. Escrita no Influx pode falhar."
fi

echo "Iniciando Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 middleware_dt.wsgi:application
