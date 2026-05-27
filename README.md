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

- **InfluxDB (banco de dados temporal)**
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

## Comece por aqui

Você pode usar o middleware de duas formas principais e complementar com os guias de suporte abaixo.

### <a id="execucao-docker-make"></a>Execução com Docker e Make

Fluxo recomendado para subir a stack completa com Docker Compose e `make`.

[Abrir guia de execução com Docker e Make](docs/demo-make.md)

### <a id="instalacao-manual"></a>Instalação manual

Fluxo para subir cada serviço separadamente fora do compose principal.

[Abrir guia de instalação manual](docs/instalacao-manual.md)

### <a id="fluxo-thingsboard"></a>Fluxo com ThingsBoard

Cenário funcional para cadastro de gateway, descoberta de devices e vínculo com DTDL.

[Abrir guia de fluxo com ThingsBoard](docs/fluxo-thingsboard.md)

### <a id="configuracoes-importantes"></a>Configurações importantes

Resumo de parâmetros operacionais relevantes (como `DEFAULT_INACTIVITY_TIMEOUT`).

[Abrir configurações importantes](docs/configuracoes-importantes.md)

### <a id="relatorios-influxdb"></a>Relatórios InfluxDB

Consultas e relatórios para análise de latência e métricas temporais.

[Abrir documentação de relatórios InfluxDB](docs/README.md)

### <a id="changelog-tecnico"></a>Changelog técnico

Registro de mudanças de autenticação, parser e migrações recentes.

[Abrir changelog técnico](docs/changelog.md)

## Visão geral

O middleware conecta dispositivos físicos, gateway IoT, modelos DTDL e camadas de persistência relacional, grafo e séries temporais. A arquitetura segue quatro blocos principais:

- `Orchestrator`: coordena os modelos de gêmeos digitais e a integração com o gateway IoT.
- `Facade`: abstrai a comunicação com ThingsBoard ou outro gateway compatível.
- `Core`: concentra a lógica central, autenticação, configurações e cadastros.
- `Utils`: reúne utilitários compartilhados.


