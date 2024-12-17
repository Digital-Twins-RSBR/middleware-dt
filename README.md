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
docker run -p 8082:8080 -p <porta>:8081 andregustavoo/parserwebapi:latest
```
- Ouvir eventos do gateway:
```bash
python manage.py listen_gateway
```

## Uso da API do Middleware
A API do middleware estará disponível para operações de consulta, criação e relação entre dispositivos físicos e seus gêmeos digitais. A documentação detalhada dos endpoints será disponibilizada conforme o projeto evoluir.


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
        