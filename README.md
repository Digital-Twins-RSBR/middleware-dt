# middleware-dt

Este projeto apresenta a primeira versão de um middleware para gêmeos digitais, que atua como uma camada de abstração entre o [ThingsBoard](https://thingsboard.io/) (ou outro gateway IoT) e uma API para plataformas visuais de gêmeos digitais.  
A solução visa integrar dispositivos físicos cadastrados em um gateway IoT com modelos DTDL, permitindo consultas complexas, representações hierárquicas e relações causais através de bancos de dados relacionais e orientados a grafos (Neo4j).

---

## Objetivo

O objetivo principal é criar uma camada intermediária em Python para conectar e gerenciar a comunicação entre dispositivos físicos (através do gateway IoT, como o ThingsBoard) e suas contrapartes de gêmeos digitais, facilitando a integração, expansão e manutenção da solução.

---

## Arquitetura dos Dados

- **PostgreSQL (ou outro BD relacional)**  
  Armazena dados estruturados, como usuários, dispositivos, modelos e informações tabulares.

- **Neo4j (banco de dados orientado a grafos)**  
  Usado para representar gêmeos digitais (nós) e suas propriedades, além de conexões (arestas) entre gêmeos. Permite consultas complexas e análise de relacionamentos hierárquicos e causais.

- **Influx (Banco de dados temporal)**
  Usado para armazenar séries temporais, leituras de sensores e métricas históricas do middleware e dos dispositivos integrados.
---

## Arquitetura do Middleware

O middleware é organizado em camadas para facilitar manutenção, escalabilidade e evolução:

- **Orchestrator:**  
  Coordena as operações entre os modelos de gêmeos digitais (DTDL) e o gateway IoT (OE Facade).

- **Facade:**  
  Fornece uma interface unificada para comunicação com o gateway IoT (ex: ThingsBoard).

- **Core:**  
  Gerencia a lógica principal do middleware, incluindo configurações, cadastro de gateways e demais recursos centrais.

- **Utils:**  
  Conjunto de utilitários e helpers para auxiliar diversas partes do middleware.

---

## Estrutura de Diretórios (Exemplo)

    middleware-dt/
    ├── core/
    │   ├── admin.py
    │   ├── api.py
    │   ├── models.py
    │   ├── schemas.py
    │   ├── urls.py
    │   └── views.py
    │
    ├── facade/
    │   ├── admin.py
    │   ├── api.py
    │   ├── models.py
    │   ├── schemas.py
    │   ├── urls.py
    │   └── views.py
    │
    ├── middleware-dt/
    │   ├── settings_base.py
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    │
    ├── orchestrator/
    │   ├── admin.py
    │   ├── api.py
    │   ├── models.py
    │   ├── schemas.py
    │   ├── urls.py
    │   └── views.py
    │
    ├── manage.py
    └── requirements/
        ├── base.txt


Esta arquitetura modular permite fácil manutenção e expansão futura.

---


## Iniciando o Projeto

1. **Instale as dependências:**
   ```bash
   pip install -r requirements/base.txt
   ```

2. **Configure o banco de dados relacional (PostgreSQL) no arquivo middleware-dt/settings.py:**

   ```python
        DATABASES = {
                'default': {
                        'ENGINE': 'django.db.backends.postgresql',
                        'NAME': 'nomebanco',
                        'USER': 'postgres',
                        'PASSWORD': 'postgres',
                        'HOST': 'localhost',
                        'PORT': '5432',
                }
        }
   ```
3. **Configure o banco orientado a grafos (Neo4j) no middleware-dt/settings.py:**
    ```python
        from neomodel import config
        # Configuração do Neo4j
        config.DATABASE_URL = "bolt://neo4j:password@localhost:7687"
    ```

4. **Crie e aplique as migrações do banco de dados:**
    ```bash
        python manage.py makemigrations
        python manage.py migrate
    ```

5. **Crie um superusuário:**
    ```bash
        python manage.py createsuperuser
    ```
6. **Execute o servidor de desenvolvimento::**
    ```bash
        python manage.py runserver
    ```

## Instalando e Configurando Neo4j no Ubuntu
1. Adicionar a chave GPG:
```bash
curl -fsSL https://debian.neo4j.com/neotechnology.g

```

2. Adicionar o repositório do Neo4j:

```bash
echo "deb [signed-by=/usr/share/keyrings/neo4j.gpg] https://debian.neo4j.com stable 4.1" | sudo tee -a /etc/apt/sources.list.d/neo4j.list

```
3. Instalar o Neo4j:
```bash
sudo apt update
sudo apt install neo4j

```

4. Iniciar o serviço Neo4j:
```bash
sudo systemctl start neo4j.service
```
Mais detalhes: [Tutorial DigitalOcean](https://www.digitalocean.com/community/tutorials/how-to-install-and-configure-neo4j-on-ubuntu-20-04)

## Executando o Neo4j em um Container Docker

```bash
docker run -d \
  --name neo4j-container \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:latest
```

**Dica (WSL): Se estiver utilizando WSL, adicione no arquivo /etc/wsl.conf:**
```
[network]
generateResolvConf = false
```

Esta documentação oferece uma visão geral da arquitetura, instalação e primeiros passos no uso do middleware-dt. Conforme o projeto evoluir, serão adicionados mais detalhes, endpoints específicos, exemplos de requisições e melhores práticas de desenvolvimento.

## Fluxo de Uso do Middleware - Test Case thingsboard
1. Cadastrando dispositivos físicos no gateway IoT (ThingsBoard)
- No ThingsBoard (local, nuvem ou demo.thingsboard.io), cadastre o(s) dispositivo(s) físico(s).
- Certifique-se de que o ThingsBoard esteja conectado ao dispositivo físico, permitindo enviar chamadas RPC e monitorar o estado.
    
2. Conectando o dispositivo físico ao middleware-dt
- Acesse http://{endereco_middleware}/admin e cadastre o gateway IoT.
- Pela API do middleware-dt, importe os dispositivos do gateway IoT:

  - Endpoint: /gatewaysiot/{gateway_id}/discover-devices
  - O middleware irá cadastrar localmente os dispositivos encontrados no gateway IoT.

3. Associando o dispositivo ao modelo DTDL do gêmeo digital
- Importe o modelo DTDL para o middleware-dt:

  - Endpoint: /import-dtdl/
  - Envie um JSON do modelo DTDL. O middleware criará a representação interna.

- Crie uma instância desse modelo relacionando-a ao dispositivo físico já cadastrado no middleware.

4. Outros comandos úteis
- Executar um container de uma API auxiliar parser DTDL:
```bash
docker run -p 8082:8080 -p andregustavoo/parserwebapi:latest
```
- Ouvir eventos do gateway:
```bash
python manage.py listen_gateway
```

## Uso da API do Middleware
A API do middleware estará disponível para operações de consulta, criação e relação entre dispositivos físicos e seus gêmeos digitais. A documentação detalhada dos endpoints será disponibilizada conforme o projeto evoluir.


## 📖 Leitura Complementar

Para avaliação usando do Middts criamos um cenário no [HomeAssistant](https://www.home-assistant.io/). Para mais informações  consulte o [Cenário de testes usando o HomeAssistant](docs/HomeAssistant.md).


<!-- # Caso de teste:

1) Cadastrando dispositivos físicos no gateway IOT(Thingsboard)
        a) Em uma instancia do thingsboard(local, em núvem ou usando o ambiente demonstrativo https://demo.thingsboard.io) cadastre o(s) 
        dispositivo(s) e faça-os conectar com o dispositivo físico.
                - Com isso o thingsboard teria acesso a enviar chamadas RPCs e verificar o estado do dispositivo. 
                - ** IMPORTANTE: Talvez precisemos definir algum padrão ou achar algum padrão de desenvolvimento do código nos dispositivos

2) Conectando dispositivo físico a uma instância sua no middleware:
        a) No middleware-dt faça o cadastro do gateway IOT para conexão e abstração (http://{endereco_middleware}/admin).
                - O objetivo principal do middleware-dt é ser uma camada de abstração entre o gêmeo digital e o dispositivo. No modelo proposto estamos abstraindo o gateway IOT do thingsboard para conexão com o dispositivo, e estamos oferecendo uma camada de api para se comunicar com o gêmeo digital propriamente dito.
        b) Usando a api do middleware-dt importe os dados dos dispositivos físicos do gateway para cadastro.
                - Usando o endpoint: /gatewaysiot/{gateway_id}/discover-devices - O middleware percorre os dispositivos do thingsboard e cadastra-os 
                no middleware.

3) Conectando Instancia do dispositivo a uma instancia do modelo(DTDL) do gêmeo digital:
        a) Importe o modelo DTDL para o middleware-dt usando o endpoint:  /import-dtdl/
                - Recebe um json e cria o modelo no middleware-dt
        b) Crie uma instância desse modelo relacionando-a com a instância do dispositivo físico no middleware-dt
                - Ao criar uma instancia do modelo dtdl você pode relacionar a uma instancia do dispositivo físico.

4) #docker run -p 8082:8080 -p <porta>:8081 andregustavoo/parserwebapi:latest
5) python manage.py listen_gateway -->


# Configurações Importantes:
O device type e o device do módulo facade tem o campo inactivityTimeout que é o responsável por definir o tempo de inatividade de um device. O tempo padrão que o MidDits vai usar pode ser redefinido no Settings a partir da configuração DEFAULT_INACTIVITY_TIMEOUT.

Sensores críticos: 15-30 segundos
Dispositivos de baixa prioridade: 120-300 segundos
Dispositivos com bateria limitada: 300-600 segundos




# Tutorial da Versão Demo com `make`

O fluxo recomendado da demo usa apenas os alvos do `Makefile`. O `Makefile` é o arquivo principal de subida da solução: ele sobe o stack completo (middleware + simulator + client), aplica as migrações, expõe a documentação Swagger e carrega o cenário `House 2.0` no middleware.

O client web está incluído no fluxo principal de build/subida (`make build` e `make up`) e fica disponível em `http://localhost:8002`. Os alvos `make client-build` e `make client-up` continuam disponíveis para operações isoladas do client.

O simulador agora fica em `middleware-dt/iot_simulator`, no mesmo padrão do client. O compose usa esse caminho por padrão e ainda aceita `SIMULATOR_CONTEXT` caso você queira sobrescrever o contexto de build.

## 1. Pré-requisitos

- Docker
- Docker Compose v2 com o comando `docker compose`
- `make`

Se estiver em WSL e seu usuário ainda não tiver acesso ao socket do Docker, rode os comandos com `sudo`.

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

Se você for usar outro ThingsBoard, ajuste as variáveis `MIDDLEWARE_THINGSBOARD_HOST`, `MIDDLEWARE_TB_HOST`, `MIDDLEWARE_TB_PORT`, `MIDDLEWARE_TB_SCHEME`, `THINGSBOARD_USER` e `THINGSBOARD_PASSWORD` antes da subida.

## 3. Subir a demo

Build do ambiente:

```bash
make build
```

Subida dos serviços:

```bash
make up
```

O target `make up` sobe os profiles `simulator` e `client` por padrão.

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

Para carregar o cenário `House 2.0` no middleware:

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

## 6. Acessar a aplicação

Endpoints principais da demo:

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

Exemplo para listar os sistemas pelo token:

```bash
TOKEN="<cole-o-access-token-aqui>"
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/orchestrator/systems/
```

## 8. Fluxo mínimo da demo

Depois de `make up`, `make healthcheck` e `make seed-house`, o fluxo mínimo para validar a demo é:

1. Entrar em `http://localhost:8000/api/docs`.
2. Gerar um JWT em `POST /api/core/token/`.
3. Consultar `GET /api/orchestrator/systems/`.
4. Criar ou listar modelos DTDL em `/api/orchestrator/systems/{system_id}/dtdlmodels/`.
5. Criar instâncias em `/api/orchestrator/systems/{system_id}/instances/`.
6. Se houver gateway configurado, rodar `make discover-devices` e usar os endpoints do módulo `facade`.

## 9. Comandos operacionais úteis

Logs contínuos:

```bash
make logs
```

Reiniciar middleware e nginx:

```bash
make restart
```

Abrir shell no container do middleware:

```bash
make shell
```

Aplicar migrações manualmente:

```bash
make migrate
```

Reexecutar coleta de estáticos:

```bash
make collectstatic
```

Parar os serviços:

```bash
make down
```

Limpar containers, redes e volumes do compose:

```bash
make clean
```

Reset completo do ambiente local:

```bash
make fullclean
```

## 10. Troubleshooting rápido

- Se `make healthcheck` falhar no Postgres por porta ocupada, ajuste `DB_HOST_PORT` no `.env`.
- Se mudanças no `.env` não refletirem em serviços com volume persistente, rode `make clean` e depois suba novamente.
- Se `discover-devices` não encontrar nada, confirme primeiro no `/admin` se existe um `GatewayIOT` válido.
- O arquivo `middts.sql` é um dump histórico e não faz parte do fluxo atual da demo baseada em migrações e `make`.

## 11. Stack local

- `middleware`: Django + Gunicorn
- `nginx`: proxy reverso e exposição HTTP
- `simulator`: simulador IoT
- `client`: interface web de consumo do MiddTS
- `db`: PostgreSQL
- `redis`: cache/sessões
- `neo4j`: grafo
- `influxdb`: séries temporais
- `parser`: parser DTDL

---

# Changelog

## GatewayIOT — Autenticação Centralizada

O modelo `GatewayIOT` foi estendido para suportar dois métodos de autenticação com o ThingsBoard:

- **`user_password`** — login via `POST /api/auth/login` e token JWT Bearer.
- **`api_key`** — token estático via header `X-Authorization: ApiKey <key>`.

Os campos `username`, `password` e `api_key` são opcionais dependendo do método escolhido. A validação é feita no `clean()` do model e os campos são mascarados no Django Admin.

### Centralização da lógica de autenticação

Foi criado o helper `get_gateway_auth_headers()` em `core/api.py`, que retorna os headers HTTP corretos de acordo com o método configurado no gateway ativo.  
Todos os consumidores (`facade/api.py`, `facade/models.py`, `orchestrator/management/commands/listen_gateway.py`) foram atualizados para utilizar esse helper ao invés de lógica de autenticação duplicada.

### Ação de admin: Verificar acesso ao gateway

Uma action `Verificar acesso ao gateway` foi adicionada ao admin do `GatewayIOT`. Ela realiza uma requisição de teste ao ThingsBoard com as credenciais configuradas e exibe o resultado direto na interface.

### Migrações adicionadas

- `core/migrations/0003_gatewayiot_auth_method_api_key.py`: adiciona `auth_method` e `api_key`, torna `username`/`password` opcionais.
- `core/migrations/0004_delete_dtdlparserclient.py`: remove o model legado `DTDLParserClient` do banco.

---

## Parser DTDL — Microsserviço Interno

O `DTDLParserClient` (cadastro via admin de qual instância do parser usar) foi removido do fluxo operacional.  
O parser agora é tratado como um microsserviço interno, configurado exclusivamente via variável de ambiente:

```
DTDL_PARSER_URL=http://parser:8080/api/DTDLModels/parse/
```

O helper `core/parser_client.py` expõe a função `get_dtdl_parser_url()`, utilizada em `orchestrator/models.py` e `orchestrator/admin.py`.  
O modelo `DTDLParserClient` foi removido do admin, da API pública e, finalmente, do banco via migration.  
O serviço `parser` continua rodando como container interno no `docker-compose.yml` e **não é exposto como cadastro gerenciável pelo usuário**.


