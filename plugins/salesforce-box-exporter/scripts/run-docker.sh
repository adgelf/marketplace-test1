#!/usr/bin/env bash
# =============================================================================
# run-docker.sh — Example helper to run the Salesforce → Box exporter in Docker
# =============================================================================
# Usage:
#   ./run-docker.sh [exporter args]
#   ./run-docker.sh --since=2024-01-01
#   ./run-docker.sh --include-types=account --since=2024-06-01
#   ./run-docker.sh --retry-from-report=export-errors-1718000000000.json
#
# Prerequisites:
#   - Docker installed and running
#   - box_config.json available on the host (BOX_CONFIG_HOST_PATH)
#   - Environment variables set (or a .env file)
#
# Set these environment variables before running (or export them):
#   export SF_CLIENT_ID=...
#   export SF_CLIENT_SECRET=...
#   export SF_USERNAME=...
#   export SF_PASSWORD=...
#   export SF_SECURITY_TOKEN=...
#   export BOX_ROOT_FOLDER_ID=...
#   export BOX_CONFIG_HOST_PATH=/absolute/path/to/box_config.json
# =============================================================================

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-salesforce-box-exporter}"
BOX_CONFIG_HOST_PATH="${BOX_CONFIG_HOST_PATH:-$(pwd)/config/box_config.json}"
BOX_CONFIG_CONTAINER_PATH="/run/secrets/box_config.json"
OUTPUT_DIR="${OUTPUT_DIR:-$(pwd)/export-output}"

# ---------------------------------------------------------------------------
# Validate required environment variables (all read from the environment —
# no credentials are stored in this script)
# ---------------------------------------------------------------------------
required_vars=(
  SF_CLIENT_ID
  SF_CLIENT_SECRET
  SF_USERNAME
  SF_PASSWORD
  SF_SECURITY_TOKEN
  BOX_ROOT_FOLDER_ID
)
missing=()
for var in "${required_vars[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
  fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: The following required environment variables are not set:"
  for var in "${missing[@]}"; do
    echo "  $var"
  done
  echo
  echo "Export them before running this script, e.g.:"
  echo "  export SF_CLIENT_ID=..."
  exit 1
fi

if [[ ! -f "$BOX_CONFIG_HOST_PATH" ]]; then
  echo "ERROR: box_config.json not found at: $BOX_CONFIG_HOST_PATH"
  echo "Set BOX_CONFIG_HOST_PATH to the correct path."
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "Starting Salesforce → Box export..."
echo "  Image: $IMAGE_NAME"
echo "  box_config: $BOX_CONFIG_HOST_PATH"
echo "  Output dir: $OUTPUT_DIR"
echo "  Args: $*"
echo

docker run --rm \
  -e SF_CLIENT_ID \
  -e SF_CLIENT_SECRET \
  -e SF_USERNAME \
  -e SF_PASSWORD \
  -e SF_SECURITY_TOKEN \
  -e BOX_CONFIG_PATH="$BOX_CONFIG_CONTAINER_PATH" \
  -e BOX_ROOT_FOLDER_ID \
  -e BOX_APP_USER_ID="${BOX_APP_USER_ID:-}" \
  -e EXPORT_WORKER_THREADS="${EXPORT_WORKER_THREADS:-4}" \
  -v "${BOX_CONFIG_HOST_PATH}:${BOX_CONFIG_CONTAINER_PATH}:ro" \
  -v "${OUTPUT_DIR}:/opt/exporter/export-output" \
  "$IMAGE_NAME" \
  "$@"

echo
echo "Export finished. Check $OUTPUT_DIR for any error reports."
