#!/bin/sh
# Builds the runner image into whichever daemon DOCKER_HOST points at (use the DEDICATED sandbox daemon, not the host's):
#   DOCKER_HOST=tcp://localhost:2375 ./infrastructure/docker/runner/build.sh [tag]
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../../.." && pwd)"
tag="${1:-sahucodex/runner:1}"
context="$(mktemp -d)"
trap 'rm -rf "$context"' EXIT
cp "$here/Dockerfile" "$context/Dockerfile"
cp "$repo/apps/judge/sahujudge/supervisor.py" "$context/supervisor.py"
docker build --tag "$tag" "$context"
