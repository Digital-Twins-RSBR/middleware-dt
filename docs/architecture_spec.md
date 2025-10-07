# Architecture Specification (Technology-Agnostic)

Version: 1.0

Date: 2025-10-03

Author: Generated from codebase analysis

---

## Purpose and scope

This specification describes a technology-agnostic architecture for a middleware that mediates between physical IoT gateways and digital twin models. The goal is to describe conceptual components, their responsibilities, interactions, data flows, and non-functional considerations in sufficient detail that the architecture can be implemented using different technology stacks.

The architecture is inspired by the existing repository layout that separates concerns into three primary modules: `core`, `facade`, and `orchestrator`. This document re-frames these modules as conceptual components and expands on the design, interfaces, and deployment considerations.


## Goals and non-goals

Goals

- Provide a modular architecture that separates configuration/authn from device integration and from model orchestration.
- Support both synchronous and asynchronous interaction patterns to balance latency and reliability.
- Enable automatic mapping between digital twin properties and physical device properties using semantic techniques while allowing manual intervention.
- Be adaptable for different back-ends (relational DB, graph DB, time-series DB) and different gateway protocols.

Non-goals

- This document does not prescribe exact libraries, frameworks or programming languages. It intentionally remains implementation-agnostic.
- It does not define complete data schemas for every entity (some example fields are provided for clarity).


## Conceptual Components


The architecture decomposes into six conceptual components (three map closely to the repo modules). Each component is described with responsibilities, interfaces, data contracts, suggested patterns, and important behaviors.

1. DT Gateway (API gateway for the middleware)
2. Configuration & Auth Service (conceptual `core`)
3. Device Facade (conceptual `facade`)
4. Model Orchestrator (conceptual `orchestrator`)
5. Session & Connection Manager (shared utility)
6. Telemetry & Events Sink (time-series / events)

Each component is described below.


### 0. DT Gateway (API Gateway)

Purpose

Provide a single, well-defined API surface for external clients and users to interact with the middleware. The DT Gateway acts as a façade for HTTP/REST (or GraphQL) access and centralizes cross-cutting functionality such as authentication, authorization, rate limiting, request composition, and API versioning.

Responsibilities

- Expose a stable external API for interacting with models, instances, devices, and telemetry.
- Centralize authentication and authorization policies for external users and clients. It should validate tokens and forward identity context to downstream components.
- Implement routing and request composition: forward or orchestrate requests to the Configuration Service, Device Facade, and Orchestrator as needed.
- Apply cross-cutting policies: rate limiting, quota enforcement, request logging, tracing, and API versioning.
- Provide API aggregation endpoints: combine data from multiple internal services (e.g., return a DT instance along with its associated device bindings and recent telemetry) in a single response.
- Support synchronous and asynchronous patterns: accept commands that execute immediately (synchronous) or return a task id for background processing (asynchronous).

Suggested Interfaces

- `GET /v1/dt/instances/{id}` — retrieve a digital twin instance (optionally include device bindings and recent telemetry).
- `POST /v1/dt/instances` — create an instance (forwards to Orchestrator API).
- `POST /v1/devices/{id}/rpc` — invoke device RPC (forwards to Device Facade with policy enforcement).
- `POST /v1/parse-model` — submit a model for parsing (forwards to Orchestrator parser orchestration).
- `POST /v1/propagate/{instance_property_id}` — request propagation; returns a job id if asynchronous.

Design notes

- The gateway should be stateless, enabling horizontal scaling behind a load balancer.
- It should propagate caller identity and request tracing headers to internal services for observability and auditability.
- Prefer an API gateway product or a lightweight reverse-proxy with programmable hooks (e.g., Envoy with filters, Kong, API management platforms, or custom middleware) depending on organizational needs.
- Consider implementing API-specific caching for read-heavy endpoints to improve latency and reduce downstream load.



### 1. Configuration & Auth Service

Purpose

Centralize runtime configuration for external gateways and parser services, and provide lightweight authentication helpers for internal use.

Responsibilities

- Persist gateway connection configurations (gateway identifier, endpoint addresses, credentials, optional TLS configuration).
- Persist DTDL / model parser client endpoints.
- Provide an internal API for acquiring short-lived credentials or tokens for gateways (e.g., obtain JWTs from ThingsBoard or other gateway software).
- Provide access control for administrative operations (create/edit gateway entries, enable/disable parser clients).

Suggested Interfaces

- Administrative CRUD API for gateway and parser entries.
- `GetToken(gateway_id) -> Token` operation (synchronous) that returns a short-lived credential usable by the Device Facade.
- Optional: Token cache with TTL to avoid repeated auth calls.

Data Contracts

- Gateway record (example): { id, name, endpoint_url, username, password_or_secret_ref, tls_config }
- Parser client record (example): { id, name, endpoint_url, active_flag }

Design notes

- Secrets management: prefer storing secrets in an encrypted store or leverage a secrets manager. The service should avoid logging plaintext credentials.
- Token fetching: implement exponential backoff and a fast-fail fallback strategy (e.g., return an explicit error rather than blocking indefinitely).


### 2. Device Facade

Purpose

Encapsulate integration with physical gateways (e.g., ThingsBoard, MQTT brokers, CoAP or custom APIs), model devices and device properties locally, and provide RPC and telemetry instrumentation.

Responsibilities

- Device discovery: query gateway endpoints to obtain device inventory and create/update local device representations.
- Device model: maintain Device and Property entities that represent the physical device state and characteristics.
- RTC interactions: perform RPC calls (commands and reads) to devices, handling retries, timeouts and fallbacks.
- Telemetry formatting: format and publish telemetry/inactivity events to the Telemetry Sink.
- Provide an API for higher layers (Orchestrator) to query device inventory and trigger RPCs.

Suggested Interfaces

- `DiscoverDevices(gateway_id, filter) -> [Device]` — returns devices discovered in the gateway and synchronizes local state.
- `CallRPC(device_id, method, params, timeout) -> RPCResult` — perform an RPC and return structured result or error.
- `ListDeviceProperties(device_id) -> [Property]` — returns local property descriptors (including RPC read/write methods when present).
- Events: publish `DeviceDiscovered`, `PropertyUpdated`, `DeviceInactive` events to the telemetry/event sink.

Design notes

- Latency posture: the facade should support low-latency calls with configurable timeouts and retries. Provide graceful fallback behavior (e.g. cached/mock responses) for high-availability scenarios.
- Bulk operations: discovery and sync should use bulk-write patterns to reduce DB overhead.
- Idempotency: operations that create/update local representations must be idempotent to tolerate retries.


### 3. Model Orchestrator

Purpose

Manage digital twin models and their instances. Provide model parsing orchestration and link digital twin properties to physical devices when applicable.

Responsibilities

- Store canonical model definitions (e.g., DTDL or other model formats) and a parsed, normalized representation used for instance generation.
- Request and coordinate parsing services (external or embedded) to convert high-level model specs into elements and relationships.
- Materialize Digital Twin Instances (hierarchical instances) from parsed models, creating instance properties and relationships.
- Provide semantic binding: suggest or perform automatic mappings between DT properties and device properties using a pluggable similarity mechanism (embedding-based, rule-based, or deterministic heuristics).
- Propagation: when a causal DT property changes, orchestrator may propagate the change to the associated physical device property via the Device Facade.

Suggested Interfaces

- `ParseModel(model_spec) -> ParsedModel` — delegates to a parser service and normalizes output.
- `CreateInstance(model_id, instance_spec) -> Instance` — materializes a hierarchical instance, creates instance-level properties.
- `SuggestBindings(instance_id) -> [BindingSuggestion]` — returns candidate device-property bindings with confidence scores.
- `PropagateProperty(instance_property_id, value, options) -> PropagationResult` — optional synchronous or asynchronous propagation to device.

Design notes

- Binding strategies must be pluggable: allow simple name-matching, ontology-based mapping, or ML-based semantic matching.
- Human-in-the-loop: expose an approval workflow for high-confidence or low-confidence suggestions to avoid incorrect automatic mappings.
- Consistency model: decide whether propagations are synchronous (blocking) or asynchronous: blocking propagation provides immediate device consistency, asynchronous propagation improves throughput and resilience.


### 4. Session & Connection Manager (shared utility)

Purpose

Provide an optimized manager for HTTP, MQTT or other protocol sessions to gateways, reducing connection churn and enabling global coordination in multi-process deployments.

Responsibilities

- Provide pooled or singleton sessions for gateway endpoints to reduce TCP/TLS handshake costs.
- Coordinate sessions across processes or instances if needed (e.g., via Redis locks or coordination keys).
- Provide policy configuration for timeouts, retries, and pool sizes.

Suggested Interfaces

- `GetSession(gateway_id) -> SessionHandle`
- `CloseSession(gateway_id)`

Design notes

- Multi-process deployments: use a coordination mechanism to avoid creating independent pools per process when global limits are required.
- URLLC considerations: in ultra-low-latency setups, use tuned timeouts and small connection pools; otherwise prefer default larger pools for throughput.


### 5. Telemetry & Events Sink

Purpose

Store telemetry time-series and events such as device telemetry points, inactivity events and propagation traces.

Responsibilities

- Provide an ingest endpoint supporting line-protocol or structured events.
- Preserve event timestamping rules (received timestamp vs event timestamp).
- Provide query and aggregation interfaces for analysis and monitoring.

Design notes

- Use a time-series database for telemetry (InfluxDB, TimescaleDB, or cloud equivalents) and a log/event store for application events (Elasticsearch, CloudWatch, etc.).
- Telemetry writes should be non-blocking for synchronous control paths where possible. Consider batching or asynchronous workers.


## Data flows and sequences

This section describes canonical sequences between components and their data contracts.

### Device discovery

1. Operator or scheduler triggers `DiscoverDevices(gateway_id)` on Device Facade.
2. Device Facade requests a token from Configuration & Auth Service: `GetToken(gateway_id)`.
3. Device Facade queries the gateway API (e.g., `/api/tenant/devices`) and receives a device list.
4. Device Facade synchronizes local Device and Property records using idempotent bulk operations.
5. Device Facade publishes `DeviceDiscovered` events to Telemetry/Events Sink.

### DTDL parsing and instance creation

1. Author provides a model specification to Orchestrator via `ParseModel` or `CreateInstance`.
2. Orchestrator calls the parser service (remote or embedded) and receives a normalized `ParsedModel`.
3. Orchestrator persists `ParsedModel` and creates `ModelElement` and `ModelRelationship` records.
4. `CreateInstance` materializes a `DigitalTwinInstance` and `DigitalTwinInstanceProperty` rows for each model element.

### Semantic binding and propagation

1. Orchestrator calls `SuggestBindings(instance_id)` which queries candidate device properties from Device Facade and computes similarity scores.
2. Orchestrator stores suggestions and, optionally, automatically binds if score >= threshold or if operator approves.
3. When a causal DT property changes and is bound to a device property, Orchestrator calls `PropagateProperty(...)`.
   - If synchronous: Orchestrator calls Device Facade `CallRPC(device_id, method, params)` and waits for the result.
   - If asynchronous: Orchestrator emits a propagation event; a worker consumes it and calls Device Facade.
4. Device Facade calls external gateway RPC endpoints and updates the device property value; it publishes `PropertyUpdated` and telemetry to the Telemetry Sink.


## Cross-cutting concerns

### Security

- Secrets handling: keep credentials in an encrypted store or external secrets manager.
- Authentication: internal APIs must be protected (mutual TLS, OAuth, or token-based auth).
- Auditing: log model changes and property propagations for traceability.

### Reliability and availability

- Use retry policies with backoff for remote calls, but keep low-latency RPC paths tuned separately.
- Provide queuing/backpressure for operations that can be performed asynchronously.

### Observability

- Instrument counts for parser calls, binding suggestions, propagation success/failure, and fallback/mock usage.
- Track latency percentiles for RPCs and parsing.

### Scalability

- Partition by gateway or system context for horizontal scaling.
- Use stateless workers for parsing and propagation; store state in persistent stores.


## Suggested interfaces (APIs) summary

- GetToken(gateway_id) -> { token, expires_at }
- DiscoverDevices(gateway_id, params) -> { created, updated }
- CallRPC(device_id, method, params, timeout) -> { status, body }
- ParseModel(model_spec) -> ParsedModel
- CreateInstance(model_id, instance_spec) -> Instance
- SuggestBindings(instance_id) -> [ { property_id, device_property_id, score } ]
- PropagateProperty(instance_property_id, value, mode=synchronous|asynchronous) -> { status }

DT Gateway (external API) examples:

- GET /v1/dt/instances/{id} -> { instance, bindings?, recent_telemetry? }
- POST /v1/dt/instances -> { instance_id }
- POST /v1/devices/{id}/rpc -> { task_id | immediate_result }
- POST /v1/parse-model -> { parse_job_id | parsed_model }
- POST /v1/propagate/{instance_property_id} -> { job_id }


## Implementation options

- Persistence: relational DB for canonical models and instances; optional graph DB for relationship-heavy queries (Neo4j) and time-series DB for telemetry.
- Parser: external microservice or library that transforms DTDL into a normalized JSON used by the orchestrator.
- Binding engine: simple name matching + tokenization, or ML-based (embedding) service. Provide a pluggable adapter.


## Risks and mitigations

- Incorrect automatic bindings: mitigate via human-in-the-loop approval and conservative confidence thresholds.
- Gateway auth changes: cache tokens with TTL and implement clear error handling.
- Latency vs correctness trade-offs: allow configuration per-operation for timeouts and sync/async behavior.


## Next steps

- Create a short set of integration tests that exercise: discovery, model parsing, instance creation and a propagation roundtrip to a mocked gateway.
- Define concrete data schemas and an example of a model JSON and parsed output.
- Add a small operator UI mockup for reviewing binding suggestions.

---

End of specification.
