#!/usr/bin/env bash
set -euo pipefail

for database in \
  identity_and_access multi_tenancy llm_gateway intent_detection knowledge_base \
  tool_orchestration guardrails human_oversight billing_and_metering auditability \
  observability conversational_engine workflow_engine agentic_rag vector_db; do
  psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    --command "CREATE DATABASE \"${database}\""
done

