#!/usr/bin/env bash
set -euo pipefail

pilot_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${pilot_dir}/../.." && pwd)"
cd "$repo_root"

python3 deploy/pilot/generate_env.py
mkdir -p deploy/pilot/state
chmod 700 deploy/pilot/state

set -a
source deploy/pilot/.env
set +a

compose=(docker compose --project-directory deploy/pilot --env-file deploy/pilot/.env)
phase1=(postgres redis external-mocks identity-and-access multi-tenancy llm-gateway
  intent-detection knowledge-base tool-orchestration guardrails human-oversight
  billing-and-metering auditability observability conversational-engine)

"${compose[@]}" up --build -d "${phase1[@]}"
python3 deploy/pilot/verify.py --phase phase1 --health-only

"${compose[@]}" run --rm seed phase1
virtual_key="$(python3 -c 'import json; print(json.load(open("deploy/pilot/state/seed.json"))["llm_gateway_virtual_key_id"])')"
printf 'LLM_GATEWAY_VIRTUAL_KEY=%s\n' "$virtual_key" >deploy/pilot/.env.runtime
chmod 600 deploy/pilot/.env.runtime
set -a
source deploy/pilot/.env.runtime
set +a

"${compose[@]}" up --build -d vector-db agentic-rag workflow-engine
python3 deploy/pilot/verify.py --phase full --health-only
"${compose[@]}" run --rm seed phase2
"${compose[@]}" run --rm workflow-definition
python3 deploy/pilot/verify.py --phase full

echo "Tectonic pilot is ready. Conversational API: http://localhost:8081"

