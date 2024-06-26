# middleware-dt

Versão inicial da proposta de um middleware para digital twins O objetivo original aqui será desenvolver um middleware em Python para atuar como uma camada de abstração entre o ThingsBoard e uma API para plataformas visuais de gêmeos digitais.

Vamos esboçar a arquitetura desse middleware, prevendo as camadas que um middleware padrão precisa.

Arquitetura do Middleware
    Camadas Principais

        - Orchestrator: Responsável pela coordenação das operações entre a representação do gêmeo digital (em DTDL) e a fachada do gateway IoT (OE Facade).
        - OE Facade: Uma interface para comunicação com a API do ThingsBoard (ou outro gateway IoT).
        - DTOs (Data Transfer Objects): Objetos que encapsulam os dados que trafegam entre as camadas.
        - Services: Serviços que implementam a lógica de negócio e operam sobre os DTOs.
        - API Layer: Uma camada de interface RESTful para a interação com plataformas visuais de gêmeos digitais.
        - Utils: Utilitários e helpers que são usados em várias partes do middleware.

Esboço de Implementação

    Estrutura de Diretórios
        middleware-dt/
            │
            ├── middleware/
            │   ├── __init__.py
            │   ├── admin.py
            │   ├── apps.py
            │   ├── models.py
            │   ├── serializers.py
            │   ├── urls.py
            │   ├── views.py
            │
            ├── middleware-dt/
            │   ├── __init__.py
            │   ├── asgi.py
            │   ├── settings.py
            │   ├── urls.py
            │   ├── wsgi.py
            │
            ├── manage.py
            └── requirements/
                ├── base.txt



Essa arquitetura é modular e escalável, facilitando futuras expansões e manutenções.

Passos para Executar

    Instale as dependências:

            pip install -r requirements/base.txt
    
    Configure o banco de dados no middlwware_dt/settings.py.

    Crie as migrações e migre o banco de dados:

            python manage.py makemigrations
            python manage.py migrate

    Crie um superusuário:
            python manage.py createsuperuser
    
    Execute o servidor:
            python manage.py runserver

