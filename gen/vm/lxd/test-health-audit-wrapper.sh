#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/checkout/gen/tests/lib" "$temporary/installed"
printf '%s\n' 'audit_helper=loaded' > "$temporary/checkout/gen/tests/lib/helper.sh"
cat > "$temporary/checkout/gen/tests/health-audit.sh" <<'AUDIT'
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib/helper.sh"
test "$audit_helper" = loaded
test "$HEALTH_EXPECT_CLIENTS" = 20
test "$1" = 'argument with spaces'
exit 19
AUDIT
chmod +x "$temporary/checkout/gen/tests/health-audit.sh"
install -m 0755 "$root/gen/vm/scripts/guest/easymesh-health-audit" "$temporary/installed/audit"
set +e
EASYMESH_REPO="$temporary/checkout" HEALTH_EXPECT_CLIENTS=20 \
    "$temporary/installed/audit" 'argument with spaces'
result=$?
set -e
test "$result" = 19
grep -Fq '[easymesh-health-audit]=gen/vm/scripts/guest/easymesh-health-audit' "$root/gen/vm/lxd/build.sh"
grep -Fq '"$repo/gen/vm/scripts/guest/easymesh-health-audit"' "$root/gen/vm/scripts/80-redeploy-accepted-lab.sh"
printf '%s\n' 'PASS: installed audit resolves checkout helpers and preserves profile, arguments and exit status'
