# Tectonic support-agent pilot

This is the smallest sellable Tectonic deployment: 15 real platform modules,
Postgres, Redis and the two external systems that remain deterministic in a
demo (the model provider and merchant order API).

## Start

Prerequisites: Docker Engine with Compose v2, Python 3.12, 8 GB free memory and
ports 8080-8085, 8088-8089, 8093, 8095, 8098-8099, 8109-8110, 8112 and 9200.

```bash
make pilot-up
```

The command generates local credentials, builds and migrates every module,
starts the phase-one control plane, creates the tenant and virtual key, starts
the dependent data/workflow plane, loads the knowledge and workflow fixtures,
and runs the acceptance verifier.

```bash
make pilot-health
make pilot-verify
make pilot-down
make pilot-reset       # also deletes local pilot databases and credentials
```

Generated credentials and seed state stay under `deploy/pilot/` and are git
ignored. The external model is intentionally deterministic by default.

## Use a real model provider

Edit `deploy/pilot/.env` before startup:

```dotenv
PILOT_LLM_MODE=openai
PILOT_LLM_BASE_URL=https://your-openai-compatible-provider.example/v1
PILOT_LLM_API_KEY=your-provider-key
PILOT_LLM_CHAT_MODEL=your-chat-model
PILOT_LLM_EMBEDDING_MODEL=your-embedding-model
```

The API key is passed only to the provider-adapter container and is never
written to seed state or logs. The adapter maps Tectonic's logical agents to
the configured provider model, forces JSON-only task contracts, validates the
returned structure and rejects malformed responses. Leave the embedding model
empty to keep deterministic local embeddings while using a real chat model.
