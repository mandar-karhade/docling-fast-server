#!/usr/bin/env bash
set -euo pipefail

VERSION="latest"
PORT=8000
# Defaults aligned with current deployment model: 1 HTTP worker; CPU workers via MAX_WORKERS
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
MAX_WORKERS="${MAX_WORKERS:-12}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --v|--version)
      VERSION="${2:-}"
      if [[ -z "$VERSION" ]]; then
        echo "Error: --v requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --p|--port)
      PORT="${2:-}"
      if [[ -z "$PORT" ]]; then
        echo "Error: --port requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --uw|--uvicorn-workers)
      UVICORN_WORKERS="${2:-}"
      if [[ -z "$UVICORN_WORKERS" ]]; then
        echo "Error: --uvicorn-workers requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --mw|--max-workers)
      MAX_WORKERS="${2:-}"
      if [[ -z "$MAX_WORKERS" ]]; then
        echo "Error: --max-workers requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --help)
      echo "Usage: $0 --v <version> [--port <host_port>] [--uvicorn-workers <n>] [--max-workers <n>]" >&2
      exit 0
      ;;
    *)
      echo "Usage: $0 --v <version> [--port <host_port>] [--uvicorn-workers <n>] [--max-workers <n>]" >&2
      exit 1
      ;;
  esac
done

IMAGE="legendofmk/docling-cpu-api:${VERSION}"

echo "Pulling image: ${IMAGE}"
docker pull "$IMAGE"

echo "Running: ${IMAGE} on host port ${PORT} -> container 8000"
docker run \
  -p "${PORT}:8000" \
  -e OPENAI_API_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY not set}" \
  -e OMP_NUM_THREADS="${OMP_NUM_THREADS:-24}" \
  -e UVICORN_WORKERS="${UVICORN_WORKERS}" \
  -e MAX_WORKERS="${MAX_WORKERS}" \
  "$IMAGE"


