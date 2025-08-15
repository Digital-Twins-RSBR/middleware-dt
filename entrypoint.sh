#!/bin/sh
set -e

# Carrega .env se existir

# Carrega .env de forma robusta, exportando cada variável
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

# Aguarda Postgres ficar acessível
POSTGRES_HOST="${POSTGRES_HOST:-10.10.2.10}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
echo "Verificando Postgres em ${POSTGRES_HOST}:${POSTGRES_PORT}..."
for i in $(seq 1 30); do
	if PGPASSWORD="${POSTGRES_PASSWORD:-tb}" pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "${POSTGRES_USER:-tb}" >/dev/null 2>&1; then
		echo "Postgres disponível após ${i}s"; break
	fi
	echo "Aguardando Postgres (${i}s)..."; sleep 1
	if [ "$i" = "30" ]; then
		echo "[ERRO] Postgres não respondeu em 30s"; exit 1
	fi
done

# Ajusta ALLOWED_HOSTS dinamicamente se não definido
if ! grep -q '^ALLOWED_HOSTS=' "$ENV_FILE" 2>/dev/null; then
	HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
	echo "ALLOWED_HOSTS=localhost,127.0.0.1,$HOST_IP,*" >> "$ENV_FILE"
	export ALLOWED_HOSTS="localhost,127.0.0.1,$HOST_IP,*"
fi

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
