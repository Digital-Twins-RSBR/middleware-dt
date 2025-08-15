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

# Corrige DJANGO_SETTINGS_MODULE se antigo nome estiver presente
if [ "${DJANGO_SETTINGS_MODULE}" = "middleware-dt.settings" ]; then
	export DJANGO_SETTINGS_MODULE=middleware_dt.settings
fi

# Permite adiar inicialização completa quando usado em topologia (Containernet)
if [ "${DEFER_START:-0}" = "1" ]; then
	echo "[entrypoint] DEFER_START=1 -> aguardando start externo (tail infinito)"
	tail -f /dev/null
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

# Aguarda Postgres ficar acessível (multi-host fallback)
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
PRIMARY_HOST="${POSTGRES_HOST:-}"
FALLBACK_HOSTS="10.0.0.10 10.10.2.10"
HOST_CANDIDATES="${PRIMARY_HOST} ${FALLBACK_HOSTS}"
echo "[db-wait] Interfaces disponíveis:"; ip -brief addr || true
echo "[db-wait] Testando hosts candidatos: ${HOST_CANDIDATES}"
FOUND_HOST=""
for H in $HOST_CANDIDATES; do
	[ -z "$H" ] && continue
	echo "[db-wait] Tentando host $H:${POSTGRES_PORT}";
	for i in $(seq 1 15); do
		# Primeiro teste rápido de reachability (ping 1 pacote, 1s timeout)
		ping -c1 -W1 "$H" >/dev/null 2>&1 || echo "[db-wait][diag] ping falhou para $H"
		# Exporta H para o processo Python
		H="$H" python - <<'PY'
import os, psycopg2, sys, socket
host = os.getenv('H') or ''
if not host:
	print('host vazio - não definido corretamente')
	sys.exit(1)
try:
	conn = psycopg2.connect(
		dbname=os.getenv('POSTGRES_DB','thingsboard'),
		user=os.getenv('POSTGRES_USER','tb'),
		password=os.getenv('POSTGRES_PASSWORD','tb'),
		host=host,
		port=int(os.getenv('POSTGRES_PORT','5432')),
		connect_timeout=2
	)
	conn.close()
	sys.exit(0)
except Exception as e:
	msg = str(e).replace('\n',' ')[:180]
	print(msg)
	sys.exit(1)
PY
		if [ $? -eq 0 ]; then
			echo "[db-wait] Conectado a $H:${POSTGRES_PORT} após ${i}s"
			FOUND_HOST="$H"
			break
		fi
		sleep 1
	done
	[ -n "$FOUND_HOST" ] && break
done

if [ -z "$FOUND_HOST" ]; then
	echo "[ERRO] Nenhum host PostgreSQL acessível. Verifique se a topologia (Containernet) está ativa antes de rodar este entrypoint manualmente."
	echo "[DICA] Rode o script de topologia e depois deixe o middts subir automaticamente."
	exit 1
fi

# Exporta o host resolvido (caso diferente do fornecido originalmente) e persiste no .env
if ! grep -q '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null; then
	echo "POSTGRES_HOST=$FOUND_HOST" >> "$ENV_FILE"
elif [ -n "$FOUND_HOST" ] && [ "$(grep '^POSTGRES_HOST=' "$ENV_FILE" | cut -d'=' -f2-)" != "$FOUND_HOST" ]; then
	sed -i "s/^POSTGRES_HOST=.*/POSTGRES_HOST=$FOUND_HOST/" "$ENV_FILE"
fi
export POSTGRES_HOST="$FOUND_HOST"
echo "[db-wait] Usando POSTGRES_HOST=$POSTGRES_HOST"

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
