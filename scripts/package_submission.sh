#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <8-digit-student-id> <report-pdf> <demo-mp4>" >&2
  exit 2
}

[[ $# -eq 3 ]] || usage
student_id="$1"
report_pdf="$2"
demo_mp4="$3"
[[ "$student_id" =~ ^[0-9]{8}$ ]] || usage
[[ -f "$report_pdf" && "$report_pdf" == *.pdf ]] || usage
[[ -f "$demo_mp4" && "$demo_mp4" == *.mp4 ]] || usage

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
submission_dir="$repo_root/submission"
code_zip="$submission_dir/A1_Code_${student_id}.zip"
outer_zip="$submission_dir/A1_${student_id}.zip"
report_name="A1_Report_${student_id}.pdf"
demo_name="A1_Demo_${student_id}.mp4"

if rg -l '\[LIVE EVIDENCE NEEDED\]' "$repo_root/docs/evidence" >/dev/null; then
  echo "Refusing to package while live evidence is still marked incomplete." >&2
  exit 1
fi

if [[ -e "$code_zip" || -e "$outer_zip" ]]; then
  echo "Refusing to overwrite an existing submission archive." >&2
  exit 1
fi

source "$repo_root/.venv/bin/activate"
ruff check "$repo_root/backend"
mypy "$repo_root/backend/app"
pytest "$repo_root/backend/tests" -q
npm --prefix "$repo_root/frontend" run lint
npm --prefix "$repo_root/frontend" run typecheck
npm --prefix "$repo_root/frontend" run contract:check
npm --prefix "$repo_root/frontend" test -- --run
npm --prefix "$repo_root/frontend" run build
npm --prefix "$repo_root/frontend" run e2e

staging_root="$(mktemp -d)"
trap 'rm -rf "$staging_root"' EXIT
code_stage="$staging_root/code"
outer_stage="$staging_root/outer"
mkdir -p "$code_stage" "$outer_stage" "$submission_dir"

rsync -a "$repo_root/" "$code_stage/" \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.env.local' \
  --exclude '.mypy_cache/' \
  --exclude '.pytest_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.superpowers/' \
  --exclude '.venv/' \
  --exclude 'artifacts/generated/' \
  --exclude 'data-1.zip' \
  --exclude 'frontend/.sample-pdf-build/' \
  --exclude 'frontend/dist/' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/playwright-report/' \
  --exclude 'frontend/test-results/' \
  --exclude 'learning_contract_spring_2026.docx' \
  --exclude 'submission/' \
  --exclude 'tmp/' \
  --exclude '*.pyc' \
  --exclude '__pycache__/'

if rg -l --hidden 'sk-[A-Za-z0-9_-]{20,}' "$code_stage" >/dev/null; then
  echo "Potential API key found in staged code; archive not created." >&2
  exit 1
fi

(cd "$code_stage" && zip -qr "$code_zip" .)
cp "$report_pdf" "$outer_stage/$report_name"
cp "$demo_mp4" "$outer_stage/$demo_name"
cp "$code_zip" "$outer_stage/$(basename "$code_zip")"
(cd "$outer_stage" && zip -qr "$outer_zip" .)

if unzip -Z1 "$code_zip" | rg '(^|/)(\.env|\.env\.local|node_modules|\.venv)(/|$)' >/dev/null; then
  echo "Forbidden secret or dependency path found in code archive." >&2
  exit 1
fi

expected_outer="$(printf '%s\n' "$report_name" "$demo_name" "$(basename "$code_zip")" | sort)"
actual_outer="$(unzip -Z1 "$outer_zip" | sed '/\/$/d' | sort)"
if [[ "$actual_outer" != "$expected_outer" ]]; then
  echo "Outer archive contents do not match the required three files." >&2
  exit 1
fi

echo "Created $outer_zip"
