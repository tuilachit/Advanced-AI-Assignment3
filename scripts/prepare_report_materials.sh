#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <8-digit-student-id>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
student_id="$1"
[[ "$student_id" =~ ^[0-9]{8}$ ]] || usage

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="$repo_root/submission/A1_Report_Materials_${student_id}"

if [[ -e "$destination" ]]; then
  echo "Refusing to overwrite existing report materials: $destination" >&2
  exit 1
fi

mkdir -p \
  "$destination/01_System/source_code" \
  "$destination/02_Setup" \
  "$destination/03_Evidence"

rsync -a \
  --exclude '.sample-pdf-build/' \
  --exclude 'dist/' \
  --exclude 'node_modules/' \
  --exclude 'playwright-report/' \
  --exclude 'test-results/' \
  "$repo_root/backend" \
  "$repo_root/frontend" \
  "$repo_root/scripts" \
  "$destination/01_System/source_code/"

cp "$repo_root/docs/architecture/data-flow.png" \
  "$destination/01_System/architecture_diagram.png"
cp "$repo_root/README.md" "$destination/02_Setup/README.md"
cp "$repo_root/backend/requirements.txt" "$destination/02_Setup/requirements.txt"
cp "$repo_root/.env.example" "$destination/02_Setup/config.example"
rsync -a "$repo_root/docs/evidence/" "$destination/03_Evidence/"

echo "Prepared $destination"
