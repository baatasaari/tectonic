#!/usr/bin/env bash
set -euo pipefail

# Sigstore keyless signing depends on short-lived external services (OIDC,
# Fulcio and Rekor). Retry transient failures, while keeping the CI job bounded.
max_attempts="${SIGSTORE_MAX_ATTEMPTS:-3}"
retry_delay="${SIGSTORE_RETRY_DELAY_SECONDS:-5}"

if [[ "$#" -eq 0 ]]; then
  echo "usage: $0 <signing command> [arguments ...]" >&2
  exit 64
fi

if ! [[ "$max_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "SIGSTORE_MAX_ATTEMPTS must be a positive integer" >&2
  exit 64
fi

if ! [[ "$retry_delay" =~ ^[0-9]+$ ]]; then
  echo "SIGSTORE_RETRY_DELAY_SECONDS must be a non-negative integer" >&2
  exit 64
fi

for ((attempt = 1; attempt <= max_attempts; attempt++)); do
  if "$@"; then
    exit 0
  fi

  if ((attempt == max_attempts)); then
    echo "Sigstore signing failed after ${max_attempts} attempts." >&2
    exit 1
  fi

  echo "Sigstore signing attempt ${attempt}/${max_attempts} failed; retrying in ${retry_delay}s." >&2
  sleep "$retry_delay"
done
