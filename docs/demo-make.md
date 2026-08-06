# Execução com Docker e Make

Este guia descreve o fluxo recomendado para subir a demo do middleware com o `Makefile`. Esse caminho sobe a pilha completa e já inclui middleware, nginx, simulator, client, PostgreSQL, Neo4j, InfluxDB, Redis e parser DTDL.

[Voltar para a documentação principal](../README.md#execucao-docker-make)

## Fluxo rápido (primeira execução)

```bash
cp .env.example .env
make build-with-deps
make up
make healthcheck
make seed-house
```

Esse caminho cobre bootstrap de dependências (quando houver submodules), build e subida da stack completa.

Se `iot_simulator` e `middts-client` nao existirem na raiz do projeto, `make build-with-deps` tenta criar as pastas automaticamente com `git clone`.

## 1. Pré-requisitos

- Docker
- Docker Compose v2 com o comando `docker compose`
- `make`

Se estiver em WSL e seu usuário ainda não tiver acesso ao socket do Docker, rode os comandos com `sudo`.

Bootstrap de dependencias:

```bash
make deps
```

Com submodules, esse comando executa `git submodule update --init --recursive`.

Sem submodules, ele tenta clonar automaticamente:

- `https://github.com/Digital-Twins-RSBR/iot_simulator.git`
- `https://github.com/Digital-Twins-RSBR/middts-client.git`

O bootstrap tenta fazer clone anonimo. Se o seu ambiente injetar configuracoes/credenciais Git e ainda assim o clone falhar, faca o clone manualmente ou aponte `SIMULATOR_CONTEXT` e `CLIENT_CONTEXT` para pastas locais existentes.

Ou faca tudo em um comando:

```bash
make build-with-deps
```

Se o simulador estiver em uma pasta irma (por exemplo `../iot_simulator`) em vez de `./iot_simulator`, o `Makefile` tenta detectar isso automaticamente. Se necessario, voce pode sobrescrever manualmente:

```bash
make SIMULATOR_CONTEXT=../iot_simulator build
```

Da mesma forma para o client:

```bash
make CLIENT_CONTEXT=../middts-client build
```

Se voce nao usa submodule, o fluxo recomendado e deixar `make deps` ou `make build-with-deps` criar essas pastas automaticamente. Se preferir, voce ainda pode usar os overrides de contexto.

## 2. Preparar o ambiente

Crie o arquivo `.env` a partir do template:

```bash
cp .env.example .env
```

Defaults úteis da demo em `.env.example`:

- Middleware: `http://localhost:8000`
- Simulator: `http://localhost:8001`
- Django admin / JWT: `middts` / `middts123`
- PostgreSQL: `middts` / `middts`
- Neo4j: `neo4j` / `middts123`
- InfluxDB token: `middts_token`
- ThingsBoard alvo padrão: `demo.thingsboard.io`

No fluxo atual, não e obrigatorio ajustar variaveis de ThingsBoard no `.env` para subir a stack.

As credenciais e o endpoint efetivo usados nas operacoes do middleware e do simulador sao definidos pelo `GatewayIOT` ativo cadastrado na aplicacao (admin/API). Assim, variaveis como `MIDDLEWARE_THINGSBOARD_HOST`, `MIDDLEWARE_TB_PORT` e `THINGSBOARD_PASSWORD` ficam opcionais e servem apenas para compatibilidade em etapas de bootstrap.

## 3. Subir a demo

Build do ambiente:

```bash
make build
```

Subida dos serviços:

```bash
make up
```

O `make up` sobe os profiles `simulator` e `client` por padrão.

Observação: o container do middleware executa migrações, coleta de estáticos e bootstrap do superusuário durante a inicialização.

## 4. Verificar saúde do ambiente

```bash
make healthcheck
```

O healthcheck valida:

- middleware
- simulator
- client
- parser DTDL
- InfluxDB
- Neo4j
- PostgreSQL
- Redis

## 5. Carregar o cenário demo

```bash
make seed-house
```

Esse comando cria o contexto de sistema e os modelos DTDL usados na demo.

Se você já tiver um gateway IoT configurado no banco e quiser carregar o cenário e disparar a descoberta de devices em seguida:

```bash
make seed-house-devices
```

Se quiser apenas redescobrir dispositivos dos gateways já cadastrados:

```bash
make discover-devices
```

Observação: `discover-devices` depende de pelo menos um `GatewayIOT` cadastrado. O caminho suportado hoje para isso é o Django admin em `/admin`.

Antes de usar `discover-devices`, confirme que existe um `GatewayIOT` válido cadastrado no admin e com credenciais corretas para o ThingsBoard alvo.

## 6. Acessar a aplicação

- Middleware: `http://localhost:8000`
- Swagger / OpenAPI: `http://localhost:8000/api/docs`
- Schema OpenAPI JSON: `http://localhost:8000/api/openapi.json`
- Django admin: `http://localhost:8000/admin`
- Simulator: `http://localhost:8001`
- Client: `http://localhost:8002`
- Parser Swagger: `http://localhost:8082/swagger/index.html`
- Neo4j Browser: `http://localhost:7474`
- InfluxDB: `http://localhost:8086`

Credenciais padrão do admin e da autenticação JWT:

```text
usuario: middts
senha: middts123
```

## 7. Obter um token JWT

Exemplo com `curl`:

```bash
curl -X POST "http://localhost:8000/api/core/token/?username=middts&password=middts123"
```

O retorno contém `access` e `refresh`. Use o `access` como Bearer token nos endpoints protegidos.

## 8. Fluxo mínimo da demo

1. Entrar em `http://localhost:8000/api/docs`.
2. Gerar um JWT em `POST /api/core/token/`.
3. Consultar `GET /api/orchestrator/systems/`.
4. Criar ou listar modelos DTDL em `/api/orchestrator/systems/{system_id}/dtdlmodels/`.
5. Criar instâncias em `/api/orchestrator/systems/{system_id}/instances/`.
6. Se houver gateway configurado, rodar `make discover-devices` e usar os endpoints do módulo `facade`.

## 9. Comandos operacionais úteis

- `make logs`
- `make restart`
- `make shell`
- `make migrate`
- `make collectstatic`
- `make down`
- `make clean`
- `make fullclean`

## 10. Troubleshooting rápido

- Se `make healthcheck` falhar no Postgres por porta ocupada, ajuste `DB_HOST_PORT` no `.env`.
- Se mudanças no `.env` não refletirem em serviços com volume persistente, rode `make clean` e depois suba novamente.
- Se `discover-devices` não encontrar nada, confirme primeiro no `/admin` se existe um `GatewayIOT` válido.
- O arquivo `middts.sql` é um dump histórico e não faz parte do fluxo atual da demo baseada em migrações e `make`.
- Se `make build` falhar por contexto ausente do simulador/client, rode `make deps` ou `make build-with-deps`. Se os repositorios estiverem em outro local, informe os caminhos com `SIMULATOR_CONTEXT` e `CLIENT_CONTEXT`.
