#!/usr/bin/env bash
# Acceptance wrapper used by CI/manual campaigns on an installed LXD lab.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)

usage() {
    cat <<'EOF'
Usage:
  ./gen/tests/multihop-backhaul-test.sh star
  ./gen/tests/multihop-backhaul-test.sh branch
  ./gen/tests/multihop-backhaul-test.sh chain
  ./gen/tests/multihop-backhaul-test.sh -h|--help

Profiles:
  star    Agent-1 -> {bpiap-003,bpiap-002,bpiap-001,bpiap}
  branch  Agent-1 -> bpiap-003 -> {bpiap-002,bpiap-001}; bpiap-002 -> bpiap
  chain   Agent-1 -> bpiap-003 -> bpiap-002 -> bpiap-001 -> bpiap

The selected topology remains active after a successful test. Results are
written below tmp/test-results/multihop/.

Related commands:
  ./gen/tests/multihop-backhaul.sh status
  ./gen/tests/multihop-backhaul.sh restore

See gen/tests/README.md for concepts, operation, verification and options.
EOF
}

if [ "$#" -eq 0 ]; then
    usage
    exit 0
fi

if [ "$#" -ne 1 ]; then
    usage >&2
    exit 2
fi

case "$1" in
    -h|--help|help)
        usage
        exit 0
        ;;
    star|branch|chain)
        profile=$1
        ;;
    *)
        echo "unknown profile: $1" >&2
        echo >&2
        usage >&2
        exit 2
        ;;
esac

exec "$here/multihop-backhaul.sh" test "$profile"
