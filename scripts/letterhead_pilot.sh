#!/usr/bin/env bash
set -euo pipefail

TS="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="docs/marketplace/pilot-runs"
OUT_FILE="$OUT_DIR/letterhead-pilot-$TS.md"
mkdir -p "$OUT_DIR"

START="$(date +%s)"

STATUS_OUTPUT="$(agentplan chain "$1" --status 2>&1 || true)"
IMPORT_OUTPUT="$(agentplan issue import "$1" --label agentplan --state open 2>&1 || true)"
CHAIN_OUTPUT="$(AGENTPLAN_CI=1 agentplan chain "$1" --max-tickets "${2:-5}" 2>&1 || true)"
VERIFY_OUTPUT="$(agentplan artifact verify "$1" 2>&1 || true)"

END="$(date +%s)"
DURATION="$((END - START))"

{
  echo "# Letterhead Pilot Run"
  echo
  echo "- Timestamp: $TS"
  echo "- Project: $1"
  echo "- Duration (s): $DURATION"
  echo
  echo "## Chain Status"
  echo '```text'
  echo "$STATUS_OUTPUT"
  echo '```'
  echo
  echo "## Issue Import"
  echo '```text'
  echo "$IMPORT_OUTPUT"
  echo '```'
  echo
  echo "## Chain Run"
  echo '```text'
  echo "$CHAIN_OUTPUT"
  echo '```'
  echo
  echo "## Artifact Verify"
  echo '```text'
  echo "$VERIFY_OUTPUT"
  echo '```'
} > "$OUT_FILE"

echo "Wrote pilot report: $OUT_FILE"
