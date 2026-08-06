# Changelog

[Voltar para a documentação principal](../README.md#changelog-tecnico)

## GatewayIOT — Autenticação Centralizada

O modelo `GatewayIOT` foi estendido para suportar dois métodos de autenticação com o ThingsBoard:

- `user_password` — login via `POST /api/auth/login` e token JWT Bearer.
- `api_key` — token estático via header `X-Authorization: ApiKey <key>`.

Os campos `username`, `password` e `api_key` são opcionais dependendo do método escolhido. A validação é feita no `clean()` do model e os campos são mascarados no Django Admin.

### Centralização da lógica de autenticação

Foi criado o helper `get_gateway_auth_headers()` em `core/api.py`, que retorna os headers HTTP corretos de acordo com o método configurado no gateway ativo. Todos os consumidores (`facade/api.py`, `facade/models.py`, `orchestrator/management/commands/listen_gateway.py`) foram atualizados para utilizar esse helper ao invés de lógica de autenticação duplicada.

### Ação de admin: Verificar acesso ao gateway

Uma action `Verificar acesso ao gateway` foi adicionada ao admin do `GatewayIOT`. Ela realiza uma requisição de teste ao ThingsBoard com as credenciais configuradas e exibe o resultado direto na interface.

### Migrações adicionadas

- `core/migrations/0003_gatewayiot_auth_method_api_key.py`: adiciona `auth_method` e `api_key`, torna `username`/`password` opcionais.
- `core/migrations/0004_delete_dtdlparserclient.py`: remove o model legado `DTDLParserClient` do banco.

## Parser DTDL — Microsserviço Interno

O `DTDLParserClient` (cadastro via admin de qual instância do parser usar) foi removido do fluxo operacional. O parser agora é tratado como um microsserviço interno, configurado exclusivamente via variável de ambiente:

```text
DTDL_PARSER_URL=http://parser:8080/api/DTDLModels/parse/
```

O helper `core/parser_client.py` expõe a função `get_dtdl_parser_url()`, utilizada em `orchestrator/models.py` e `orchestrator/admin.py`. O modelo `DTDLParserClient` foi removido do admin, da API pública e, finalmente, do banco via migration. O serviço `parser` continua rodando como container interno no `docker-compose.yml` e não é exposto como cadastro gerenciável pelo usuário.
