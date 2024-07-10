# middleware-dt

Versão inicial da proposta de um middleware para digital twins O objetivo original aqui será desenvolver um middleware em Python para atuar como uma camada de abstração entre o ThingsBoard e uma API para plataformas visuais de gêmeos digitais.

Vamos esboçar a arquitetura desse middleware, prevendo as camadas que um middleware padrão precisa.

Arquitetura do Middleware
    Camadas Principais

        - Orchestrator: Responsável pela coordenação das operações entre a representação do gêmeo digital (em DTDL) e a fachada do gateway IoT (OE Facade).
        - Facade: Uma interface para comunicação com a API do ThingsBoard (ou outro gateway IoT).
        - DTOs (Data Transfer Objects): Objetos que encapsulam os dados que trafegam entre as camadas, como estamos usando Django e ninja usaremos os
        models e os schemas para isso.
        - Services: Serviços que implementam a lógica de negócio e operam sobre os DTOs.
        - API Layer: Uma camada de interface RESTful para a interação com plataformas visuais de gêmeos digitais.
        - Utils: Utilitários e helpers que são usados em várias partes do middleware.

Esboço de Implementação

    Estrutura de Diretórios
        middleware-dt/
            │
            ├── facade/
            │   ├── admin.py
            |   |── api.py
            │   ├── models.py
            │   ├── schemas.py
            │   ├── urls.py
            │   ├── views.py
            │
            ├── middleware-dt/
            │   ├── settings_base.py
            │   ├── settings.py
            │   ├── urls.py
            │   ├── wsgi.py
            |
            ├── orchestrator/
            │   ├── admin.py
            |   |── api.py
            │   ├── models.py
            │   ├── schemas.py
            │   ├── urls.py
            │   ├── views.py
            │
            ├── manage.py
            └── requirements/
                ├── base.txt


Essa arquitetura é modular e escalável, facilitando futuras expansões e manutenções.

Passos para Executar:
    1) Instale as dependências:
            pip install -r requirements/base.txt
    
    2) Configure o banco de dados no middlwware_dt/settings.py.
    3) Crie as migrações e migre o banco de dados:
            python manage.py makemigrations
            python manage.py migrate
    4) Crie um superusuário:
            python manage.py createsuperuser
    5) Execute o servidor:
            python manage.py runserver



Test Case:

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
5) python manage.py listen_gateway
        
