#!/usr/bin/env bash
# Acceptance wrapper used by CI/manual campaigns on an installed LXD lab.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
profile=${1:-chain}

case "$profile" in
    chain|branch) ;;
    *) echo "usage: $0 [chain|branch]" >&2; exit 2 ;;
esac

exec "$here/../multihop-backhaul.sh" test "$profile"
