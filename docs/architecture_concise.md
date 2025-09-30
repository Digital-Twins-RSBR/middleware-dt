Concise architecture summary — middleware-dt

The middleware is structured into three core layers:

- core: stores gateway and DTDL parser configuration, exposes a helper to fetch gateway JWT tokens.
- facade: gateway adapter layer that models devices/properties, issues RPCs to gateways, and writes telemetry to InfluxDB. It centralizes token usage and handles timeouts/retries.
- orchestrator: model-driven layer that parses DTDL via an external parser, materializes model elements, creates twin instances, and performs semantic binding between DT properties and physical device properties.

Key interactions
- `core` -> provides tokens for `facade`.
- `facade` -> interacts with ThingsBoard (RPC, metadata) and InfluxDB (telemetry).
- `orchestrator` -> parses models (external parser) and binds DT properties to `facade.Property` records using embeddings.

Short recommendations for paper
- Use the concise summary as a single-paragraph description in the System Architecture section.
- Use the compact diagram (provided in the repository) as a small figure (width 0.45\textwidth) when explaining the layered design.

