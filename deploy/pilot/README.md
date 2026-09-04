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
ignored. The external model is intentionally deterministic; the next pilot
ticket adds an opt-in real OpenAI-compatible provider without changing this
default.

