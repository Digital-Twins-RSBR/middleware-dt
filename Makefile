COMPOSE = docker compose -f docker-compose.yml

PHONY: help build up down restart logs migrate collectstatic shell sim-up sim-down update db-backup deploy clean fullclean seed-house discover-gateways

help:

# Dispara a descoberta de dispositivos para todos os gateways via API REST.
# Passe ARGS para enviar opções adicionais ao comando (ex: ARGS="--gateway-ids=1,2 --dry-run").
discover-gateways:
	$(COMPOSE) exec -T middleware python manage.py discover_all_gateways --base-url http://localhost:8000 $(ARGS)
	@echo "Usage: make <target>"
	@echo "Targets: build up down restart logs migrate collectstatic shell sim-up sim-down update db-backup deploy clean fullclean seed-house"

build:
	# Build all services including the simulator profile by default
	$(COMPOSE) --profile simulator build --pull --no-cache

up:
	# Bring up all services including simulator by default. To avoid starting simulator,
	# run `$(COMPOSE) up -d` without the profile or use the `sim-down` target.
	$(COMPOSE) --profile simulator up -d

down:
	$(COMPOSE) down

clean:
	# Stop and remove containers, networks and volumes defined in compose, then prune dangling volumes
	$(COMPOSE) down -v --remove-orphans || true
	@echo "Pruning dangling Docker volumes (non-destructive for images)..."
	docker volume prune -f || true

fullclean:
	# Destructive: remove containers, images and volumes for a full reset of the environment
	@echo "FULL CLEAN: stopping compose, removing images and volumes. This is destructive."
	$(COMPOSE) down --rmi all -v --remove-orphans || true
	@echo "Running docker system prune -a --volumes (may free a lot of space)..."
	docker system prune -a --volumes -f || true

restart:
	$(COMPOSE) restart middleware nginx

logs:
	$(COMPOSE) logs -f --tail=200

migrate:
	$(COMPOSE) exec -T middleware python manage.py migrate

collectstatic:
	$(COMPOSE) exec -T middleware python manage.py collectstatic --noinput

shell:
	$(COMPOSE) exec -T middleware bash

sim-up:
	$(COMPOSE) --profile simulator up -d

sim-down:
	$(COMPOSE) --profile simulator down

update:
	@git pull --ff-only || true
	$(COMPOSE) pull
	$(COMPOSE) up -d --remove-orphans --build middleware nginx
	$(MAKE) migrate
	$(MAKE) collectstatic

db-backup:
	@echo "Run on host to create DB dump:\n  docker exec -t $$(docker compose -f docker-compose.yml ps -q db) pg_dump -U ${POSTGRES_USER:-postgres} middts > middts.sql"

deploy: update
	@echo "Deploy finished. Verify services with: make logs"

# Restore DB from middts.sql (run on host)
db-restore:
	@echo "Run on host to restore DB dump (middts.sql):"
	@echo "  cat middts.sql | docker exec -i $$(docker compose -f docker-compose.yml ps -q db) psql -U ${POSTGRES_USER:-postgres} middts"

# Carrega o cenário House 2.0 (SystemContext + 8 DTDLModels) via API REST.
# Requer que o middleware esteja UP. Passe ARGS="--force" para recriar modelos existentes.
seed-house:
	$(COMPOSE) exec -T middleware python manage.py load_house_scenario --base-url http://localhost:8000 $(ARGS)

# Simple healthcheck for main services
healthcheck:
	@echo "Checking HTTP endpoints..."
	@curl -fsS --max-time 5 http://localhost:8000/ >/dev/null && echo "middleware: OK" || echo "middleware: FAIL"
	@curl -fsS --max-time 5 http://localhost:8001/ >/dev/null && echo "simulator: OK" || echo "simulator: FAIL"
	@curl -fsS --max-time 5 http://localhost:8082/swagger/index.html >/dev/null && echo "parser: OK" || echo "parser: FAIL"
	@curl -fsS --max-time 5 http://localhost:8086/health >/dev/null && echo "influxdb: OK" || echo "influxdb: FAIL"
	@curl -fsS --max-time 5 http://localhost:7474/ >/dev/null && echo "neo4j: OK" || echo "neo4j: FAIL"
	@docker compose -f docker-compose.yml exec -T db pg_isready -U $${POSTGRES_USER:-postgres} >/dev/null 2>&1 && echo "postgres: OK" || echo "postgres: FAIL"
	@docker compose -f docker-compose.yml exec -T redis redis-cli PING >/dev/null 2>&1 && echo "redis: OK" || echo "redis: FAIL"
	@echo "docker compose ps:"
	@docker compose -f docker-compose.yml ps

# Rollback to a provided image tag (local override). Set ROLLBACK_IMAGE env, e.g. ROLLBACK_IMAGE=myrepo/middleware:20260412
rollback:
	@if [ -z "$(ROLLBACK_IMAGE)" ]; then \
		echo "Set ROLLBACK_IMAGE env var to the image you want to roll back to (e.g. myrepo/middleware:tag)"; exit 1; \
	fi
	@echo "Pulling $(ROLLBACK_IMAGE) and tagging as local middleware image..."
	@docker pull $(ROLLBACK_IMAGE) || true
	@docker tag $(ROLLBACK_IMAGE) middleware-dt_middleware:latest || true
	@docker compose -f docker-compose.yml up -d --no-deps --force-recreate middleware
	@echo "Rollback invoked; verify with: make logs"
