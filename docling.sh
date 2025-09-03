#!/usr/bin/env bash
set -euo pipefail

VERSION="latest"
PORT=8000

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
    *)
      echo "Usage: $0 --v <version> [--port <host_port>]" >&2
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
  -e UVICORN_WORKERS="${UVICORN_WORKERS:-6}" \
  -e MAX_WORKERS="${MAX_WORKERS:-12}" \
  "$IMAGE"


