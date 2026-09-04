#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
helper="${repo_root}/scripts/sign_sbom_with_retry.sh"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT

attempt_file="${test_dir}/attempts"
fake_signer="${test_dir}/fake-signer"

cat >"$fake_signer" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
attempts=0
if [[ -f "$ATTEMPT_FILE" ]]; then
  attempts="$(cat "$ATTEMPT_FILE")"
fi
attempts=$((attempts + 1))
printf '%s' "$attempts" >"$ATTEMPT_FILE"
[[ "$attempts" -ge "${SUCCEED_ON_ATTEMPT:-999}" ]]
EOF
chmod +x "$fake_signer"

ATTEMPT_FILE="$attempt_file" SUCCEED_ON_ATTEMPT=2 \
  SIGSTORE_MAX_ATTEMPTS=3 SIGSTORE_RETRY_DELAY_SECONDS=0 \
  "$helper" "$fake_signer"
[[ "$(cat "$attempt_file")" == "2" ]]

rm -f "$attempt_file"
if ATTEMPT_FILE="$attempt_file" SUCCEED_ON_ATTEMPT=99 \
  SIGSTORE_MAX_ATTEMPTS=2 SIGSTORE_RETRY_DELAY_SECONDS=0 \
  "$helper" "$fake_signer"; then
  echo "expected exhausted retries to fail" >&2
  exit 1
fi
[[ "$(cat "$attempt_file")" == "2" ]]

if SIGSTORE_MAX_ATTEMPTS=invalid "$helper" true; then
  echo "expected invalid attempt count to fail" >&2
  exit 1
fi

echo "sign_sbom_with_retry tests passed"
