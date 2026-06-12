#!/bin/sh
# Build the lcm-webapp OCI image for linux/386 and push to ghcr.io.
#
# Prereqs:
#   1. Logged into ghcr.io:
#        echo "$GHCR_PAT" | docker login ghcr.io -u robvogelaar --password-stdin
#      (PAT needs `write:packages`)
#   2. binfmt set up for cross-arch builds (only once per host):
#        docker run --privileged --rm tonistiigi/binfmt --install all
#   3. A buildx builder (one-time):
#        docker buildx create --name xb --use --bootstrap
#
# Usage:  ./build-and-push.sh [tag]    # default tag = "latest"
set -eu

TAG=${1:-latest}
IMG=ghcr.io/robvogelaar/lcm-webapp
here=$(cd "$(dirname "$0")" && pwd)

echo ">> building $IMG:$TAG for linux/386"
docker buildx build \
    --platform linux/386 \
    -t "$IMG:$TAG" \
    -t "$IMG:latest" \
    --push \
    "$here"

echo
echo ">> pushed:"
echo "   $IMG:$TAG"
echo "   $IMG:latest"
echo
echo "Next step on the build host (this same machine):"
echo "  $here/../from-registry/from-registry.sh \\"
echo "      $IMG:$TAG \\"
echo "      $here/../hello-app/out"
echo
echo "Then on vCPE-002:"
echo '  UUID=$(uuidgen | sed "s/^\\(.\\{14\\}\\)./\\15/")'
echo "  ba-cli \"Device.SoftwareModules.InstallDU( \\"
echo "      URL=http://192.168.2.150:8888/lcm-webapp.tar, \\"
echo '      UUID=$UUID, \\'
echo "      ExecutionEnvRef=Device.SoftwareModules.ExecEnv.1.)\""
