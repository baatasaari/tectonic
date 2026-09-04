#!/usr/bin/env bash
set -euo pipefail

pilot_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${pilot_dir}/../.." && pwd)"
cd "$repo_root"

args=(down --remove-orphans)
if [[ "${1:-}" == "--volumes" ]]; then
  args+=(--volumes)
fi
docker compose --project-directory deploy/pilot --env-file deploy/pilot/.env "${args[@]}"

