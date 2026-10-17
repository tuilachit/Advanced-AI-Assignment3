#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d)"
trap 'rm -rf "$temporary_dir"' EXIT

"$repo_root/.venv/bin/python" "$repo_root/backend/export_openapi.py" \
  "$temporary_dir/openapi.json"

(
  cd "$repo_root/frontend"
  ./node_modules/.bin/openapi-typescript "$temporary_dir/openapi.json" \
    --output "$temporary_dir/api-schema.ts" \
    --alphabetize
)

diff -u "$repo_root/frontend/openapi.json" "$temporary_dir/openapi.json"
diff -u "$repo_root/frontend/src/generated/api-schema.ts" \
  "$temporary_dir/api-schema.ts"
