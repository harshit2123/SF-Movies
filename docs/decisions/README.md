# Decision Log

Architecture Decision Records. Each is written in the same commit as the code it
justifies, in the format **Context → Decision → Alternatives considered → Tradeoffs**.

| ADR | Decision |
|---|---|
| [0001](0001-dataset-shape.md) | Dataset shape — coordinates present upstream, the 86-row gap |
| [0002](0002-no-geocoding.md) | **No geocoding** — why the usual Nominatim step is unnecessary |
| [0003](0003-no-websockets.md) | **No WebSockets** — batch data, HTTP GET is correct |
| [0004](0004-sqlite-and-search.md) | SQLite over Postgres; substring search over trigram |
| [0005](0005-hosting.md) | Fly.io for the API, Vercel for the SPA — *superseded by 0007* |
| [0006](0006-scope-cuts.md) | Deliberate scope cuts, each with its trigger to revisit |
| [0007](0007-single-vercel-deployment.md) | **One Vercel project**, database baked in at build time |
