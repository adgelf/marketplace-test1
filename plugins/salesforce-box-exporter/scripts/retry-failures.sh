#!/usr/bin/env bash
# =============================================================================
# retry-failures.sh — Re-run only the failed items from a previous export
# =============================================================================
# Usage:
#   ./retry-failures.sh export-errors-1718000000000.json
#
# This reads the error report and passes it to the exporter via
# --retry-from-report. The exporter will only re-attempt the specific files
# listed in the error report (by Salesforce ID), scoped to the parent accounts
# and object types referenced in that report.
# =============================================================================

set -euo pipefail

JAR="${JAR:-target/salesforce-box-exporter-1.0.0-SNAPSHOT-shaded.jar}"
CONFIG="${CONFIG:-config/application.properties}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <error-report.json>"
  echo "Example: $0 export-errors-1718000000000.json"
  exit 1
fi

REPORT_FILE="$1"

if [[ ! -f "$REPORT_FILE" ]]; then
  echo "ERROR: Error report not found: $REPORT_FILE"
  exit 1
fi

if [[ ! -f "$JAR" ]]; then
  echo "ERROR: Jar not found at $JAR. Run 'mvn package' first, or set JAR=path/to/exporter.jar"
  exit 1
fi

FAILED_COUNT=$(python3 -c "import json,sys; data=json.load(open('$REPORT_FILE')); print(len(data))" 2>/dev/null || echo "?")
echo "Retrying $FAILED_COUNT failed item(s) from: $REPORT_FILE"
echo

java -jar "$JAR" \
  --config="$CONFIG" \
  --retry-from-report="$REPORT_FILE" \
  "$@"
