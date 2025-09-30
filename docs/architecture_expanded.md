Architecture and component details — middleware-dt

This document expands the architecture diagram and explains the procedures used by the three main modules: `core`, `facade`, and `orchestrator`. The text is written in English and suitable for inclusion in a scientific article.

1. Overview

The middleware is organized in three principal modules:

- core: configuration and small utility APIs (gateway and DTDL parser clients, authentication helpers).
- facade: gateway and device adapter layer; responsible for obtaining tokens, issuing RPCs, synchronizing device metadata, and writing telemetry to InfluxDB.
- orchestrator: model-driven layer that stores and parses DTDL models, generates Digital Twin instances, performs semantic binding between DT properties and real devices, and optionally persists a graph representation in Neo4j.

These modules interact with external services:
- ThingsBoard (or other gateway) for device metadata, RPC endpoints and telemetry ingestion;
- InfluxDB for long-term telemetry and event storage;
- an external DTDL parser service used to convert raw DTDL into a parsed representation convenient for model materialization.


2. Core (configuration & auth)

Purpose and responsibilities
- Store configuration: `GatewayIOT` and `DTDLParserClient` models.
- Expose small REST/Ninja endpoints to create/list/get these records.
- Offer a small helper to fetch a JWT token for a configured gateway via `get_jwt_token_gateway()`.

Key data shape (examples)
- GatewayIOT: {name, url, username, password}
- DTDLParserClient: {name, url, active}

Typical usage
1. An administrator registers a gateway endpoint (ThingsBoard URL + credentials) via the `core` API.
2. Other modules (facade) call `core`'s `get_jwt_token_gateway()` to obtain a short-lived JWT and perform authenticated requests against ThingsBoard.

Failure modes and handling
- If a gateway is unreachable or credentials are wrong, `get_jwt_token_gateway()` returns an error (HTTP 400 with message). Calling modules must detect and either retry with backoff or mark the gateway/device as unreachable.


3. Facade (gateway/device adapter)

Purpose and responsibilities
- Model devices, device types, and properties as local Django models (`Device`, `DeviceType`, `Property`).
- Synchronize metadata and shared attributes from ThingsBoard, create local `Property` records when absent.
- Call RPC endpoints on ThingsBoard for read/write using `Property.call_rpc()`.
- Write telemetry and events to InfluxDB using a consistent line-protocol formatting helper (`format_influx_line`).
- Provide a `ThreadManager` to schedule periodic tasks (for polling telemetry or property reads).

Important procedures

A) Obtaining gateway token
- `facade` uses the `core` helper to obtain a JWT for a specific `GatewayIOT` before issuing API calls. This centralizes credentials and reduces duplication.

B) Property write flow (high-level)
1. A property on a digital twin is changed, or an external request asks to write a device property.
2. `Property.save()` detects `rpc_write_method` and calls `Property.call_rpc(RPCCallTypes.WRITE)`.
3. `call_rpc()` obtains JWT, prepares the two-way RPC payload, and issues a POST to the gateway RPC endpoint. Calls are executed using a session helper with retries and timeouts.
4. If configured, the middleware records a sent timestamp and writes a monitoring measurement to InfluxDB (best-effort).
5. On success, the `Property.value` may be updated with the response payload.

C) Telemetry and InfluxDB
- Telemetry data and inactivity events are written to InfluxDB with tags (e.g., sensor, source) and numeric fields to allow efficient aggregation and alerting.
- Writes to InfluxDB are best-effort; failures do not block RPCs but are logged.

Robustness and retries
- `Property.call_rpc()` catches `requests` timeouts and returns pseudo-responses with status codes (503/504) to allow upper layers to implement retry or degradation.
- Session creation for gateway calls centralizes timeout and retry policies (`get_session_for_gateway`).


4. Orchestrator (models, instances and semantic binding)

Purpose and responsibilities
- Persist DTDL model specifications and a parsed representation returned by an external DTDL parser.
- Materialize `ModelElement` and `ModelRelationship` rows from the parsed specification.
- Create `DigitalTwinInstance` objects (hierarchical instances) and populate `DigitalTwinInstanceProperty` objects representing each model element for every instance.
- Attempt to automatically bind DT properties to actual `facade.Property` records using a semantic similarity method based on sentence embeddings.
- Optionally persist a graph in Neo4j for visualization and graph queries.

Key procedures

A) DTDL parsing & materialization
1. A `DTDLModel` is created with a JSON `specification` containing an `@id`.
2. `DTDLModel.create_parsed_specification()` selects an active `DTDLParserClient` from `core` and POSTs payload {id, specification} to the parser URL.
3. On success, the returned JSON is stored in `parsed_specification` and `create_dtdl_models()` iterates model elements and relationships to create `ModelElement` and `ModelRelationship` rows.

Errors and recoverability
- If the parser is unreachable or returns non-JSON, the method raises an error and the model creation must be retried after the parser becomes available.

B) Instance creation
- `DigitalTwinInstance.save()` guarantees a human-friendly name when none is provided and creates `DigitalTwinInstanceProperty` rows for each `ModelElement`.
- A management command (`replicate_and_create_instances`) demonstrates how to create N replicas of a hierarchical template by calling the orchestrator API internally.

C) Semantic binding
- `DigitalTwinInstanceProperty.suggest_device_binding()` builds a textual context for the DT property including its hierarchy, model name and property schema.
- It computes embeddings via `SentenceTransformer('all-MiniLM-L6-v2')` for the DT property and for candidate device properties (device name, type, metadata, property name and type).
- Cosine similarity is used to find the best match. A conservative threshold of 0.60 is used to accept an automated binding.
- When a binding is made and the property is marked causal, writing to the DT property propagates down to the bound `facade.Property`, triggering the RPC write flow.

Caveats and validation
- Semantic binding relies on textual metadata and property names; in deployments with sparse metadata the automatic matching rate may be low.
- Threshold tuning and a human-in-the-loop verification step are recommended for production use to avoid incorrect bindings.


5. Contracts and data shapes (short)

- get_jwt_token_gateway(gateway_id) -> {token: string} | error
- DTDLModel.specification -> stored JSON with '@id'
- DTDLModel.parsed_specification -> JSON containing 'modelElements' and 'modelRelationships'
- DigitalTwinInstanceProperty.device_property -> nullable FK to `facade.Property`


6. Recommendations for experiments (for the article)

- Measure RPC latency distribution and RPC success rate to size retry/backoff parameters.
- Evaluate semantic-binding precision/recall with annotated ground truth; vary threshold and record human verification effort.
- Compare using InfluxDB as the evaluation data store vs an alternative TSDB for your telemetry workload.


7. Short code fragments (illustrative)

Getting a gateway JWT (from `core/api.py`):

```python
response = requests.post(f"{gateway.url}/api/auth/login", json={"username": gateway.username, "password": gateway.password})
if response.status_code == 200:
    token = response.json().get('token')
```

Issuing a two-way RPC (simplified):

```python
session = get_session_for_gateway(gateway.id)
response = session.post(f"{gateway.url}/api/rpc/twoway/{device.identifier}", json={"method": prop.rpc_write_method, "params": prop.get_value()}, headers=headers, timeout=8)
```

Semantic binding (high level):

```python
dt_embedding = model.encode(dt_text, convert_to_tensor=True)
for candidate in Property.objects.filter(digitaltwininstanceproperty__isnull=True):
    device_embedding = model.encode(candidate_text, convert_to_tensor=True)
    score = float(util.cos_sim(dt_embedding, device_embedding)[0][0])
    if score > best_score:
        best_match = candidate
```


8. Summary paragraph (article-ready)

The middleware is organized as three decoupled layers. The `core` module centralizes configuration and authentication utilities used by adapters. The `facade` module implements a robust gateway adapter that handles token management, RPCs with timeouts and retries, and best-effort telemetry forwarding to InfluxDB. The `orchestrator` module is model-driven: it imports DTDL models through an external parser, materializes model elements and relationships, generates hierarchical digital twin instances, and attempts to bind these logical properties to physical devices using semantic similarity. This design separates concerns (configuration, device integration, and model orchestration), simplifies testing and scaling, and allows targeted improvements (e.g., adding a caching token service, improving RPC retry strategies, or improving semantic binding models).
