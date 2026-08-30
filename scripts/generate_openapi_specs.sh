#!/usr/bin/env bash
# Regenerates docs/openapi/<module>.json for every module by importing that
# module's own FastAPI app (each module's own .venv) and dumping app.openapi()
# -- the platform's real, live spec, not a hand-maintained copy. Offline: no
# database connection is made (SQLAlchemy engines are lazy), so this only
# needs each module's own `.venv` with its own dependencies installed
# (`uv venv && uv pip install -e ".[dev]"` inside that module, same as every
# other command in this repo).
#
# Usage: ./scripts/generate_openapi_specs.sh [module-name ...]
#   (no args regenerates every module)
set -euo pipefail
cd "$(dirname "$0")/.."

OUT_DIR="docs/openapi"
mkdir -p "$OUT_DIR"

declare -A PKG=(
  [a2a]=a2a_gateway [agent-cards]=agent_cards [agent-marketplace]=agent_marketplace
  [agentic-rag]=agentic_rag [auditability]=auditability [billing-and-metering]=billing_and_metering
  [context-engineering]=context_engineering [conversational-engine]=conversational_engine
  [data-source-plugins]=data_source_plugins [deployment-strategy]=deployment_strategy
  [evaluation-framework]=evaluation_framework [finops]=finops [graph-db]=graph_db
  [guardrails]=guardrails [human-oversight]=human_oversight [identity-and-access]=identity_and_access
  [intent-detection]=intent_detection [knowledge-base]=knowledge_base [llm-gateway]=llm_gateway
  [llmops]=llmops [long-term-memory]=long_term_memory [mcp]=mcp_gateway [multi-modality]=multi_modality
  [multi-tenancy]=multi_tenancy [observability]=observability [promptops]=promptops
  [regulatory-compliance]=regulatory_compliance [sdk-and-developer-portal]=sdk_and_developer_portal
  [secrets-and-credential-management]=secrets_and_credential_management [sentinel-agents]=sentinel_agents
  [short-term-memory]=short_term_memory [tool-orchestration]=tool_orchestration [vector-db]=vector_db
  [workflow-engine]=workflow_engine
)

DUMP_SCRIPT="$(mktemp)"
cat > "$DUMP_SCRIPT" << 'PYEOF'
import importlib, json, sys, warnings
warnings.filterwarnings("ignore")
pkg, out = sys.argv[1], sys.argv[2]
mod = importlib.import_module(f"{pkg}.main")
app = mod.app if hasattr(mod, "app") else mod.create_app()
with open(out, "w") as f:
    json.dump(app.openapi(), f, indent=2)
print(f"OK {pkg}: {len(app.openapi().get('paths', {}))} paths")
PYEOF

targets=("${@:-${!PKG[@]}}")
for m in "${targets[@]}"; do
  pkg="${PKG[$m]:?unknown module: $m}"
  ( cd "modules/$m" && PYTHONPATH=src .venv/bin/python "$DUMP_SCRIPT" "$pkg" "../../$OUT_DIR/${m}.json" )
done

rm -f "$DUMP_SCRIPT"
