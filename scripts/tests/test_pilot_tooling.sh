#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

bash -n deploy/pilot/up.sh deploy/pilot/down.sh deploy/pilot/postgres/01-databases.sh
python3 -m py_compile deploy/pilot/generate_env.py deploy/pilot/verify.py

grep -q '^deploy/pilot/.env$' .gitignore
grep -q '^deploy/pilot/state/$' .gitignore
grep -q '127.0.0.1:8081:8081' deploy/pilot/docker-compose.yml

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  env_file="$(mktemp)"
  trap 'rm -f "$env_file"' EXIT
  printf '%s\n' 'PILOT_POSTGRES_PASSWORD=test-password' \
    'TECTONIC_JWT_SHARED_SECRET=test-jwt-secret' >"$env_file"
  docker compose --project-directory deploy/pilot --env-file "$env_file" config --quiet
else
  echo "docker compose unavailable; static checks completed"
fi

echo "pilot tooling tests passed"
