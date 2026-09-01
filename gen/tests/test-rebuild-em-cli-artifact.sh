#!/bin/sh
set -eu

tmp=$(mktemp -d /tmp/test-rebuild-em-cli.XXXXXX)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

repo="$tmp/repo"
work="$tmp/work"
source_dir="$work/git/src/rdkb-cli"
mock="$tmp/mock"
artifact_dir="$repo/recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh"

mkdir -p "$repo/gen" "$source_dir/static" \
    "$work/recipe-sysroot/usr/include/ccsp" \
    "$work/recipe-sysroot-native/usr/bin/i686-rdk-linux" \
    "$work/build/src/rdkb-cli/.libs" "$artifact_dir" "$mock"
cp "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/rebuild-em-cli-artifact.sh" \
    "$repo/gen/rebuild-em-cli-artifact.sh"

for source in backhaul_signal.go candidate_rejection.go helper.go main.go; do
    printf 'package main\n' >"$source_dir/$source"
done
printf 'package main\n' >"$source_dir/candidate_rejection_test.go"
printf '<html></html>\n' >"$source_dir/static/index.html"
printf 'console.log("test")\n' >"$source_dir/static/script.js"
touch "$work/recipe-sysroot/usr/include/ccsp/wifi_webconfig.h" \
    "$work/recipe-sysroot-native/usr/bin/i686-rdk-linux/i686-rdk-linux-gcc" \
    "$work/build/src/rdkb-cli/.libs/libemcli.so"

archive_seed="$tmp/archive-seed"
mkdir -p "$archive_seed/static"
printf 'old helper\n' >"$archive_seed/onewifi_em_cli"
tar -czf "$artifact_dir/em-cli.tar.gz" -C "$archive_seed" .

cat >"$mock/go" <<'EOF'
#!/bin/sh
set -eu
out=
previous=
: >"$FAKE_GO_LOG"
for argument in "$@"; do
    if [ "$previous" = -o ]; then
        out=$argument
    fi
    case "$argument" in
        *.go) printf '%s\n' "$argument" >>"$FAKE_GO_LOG" ;;
    esac
    previous=$argument
done
[ -n "$out" ]
printf 'mock ELF 32-bit Intel 80386 UnassociatedSTAErrors\n' >"$out"
chmod 0755 "$out"
EOF
chmod 0755 "$mock/go"

cat >"$mock/file" <<'EOF'
#!/bin/sh
echo "$1: ELF 32-bit LSB executable, Intel 80386"
EOF
chmod 0755 "$mock/file"

FAKE_GO_LOG="$tmp/go-sources" GO_BIN="$mock/go" PATH="$mock:$PATH" \
    "$repo/gen/rebuild-em-cli-artifact.sh" "$work" >/dev/null

expected="$tmp/expected-sources"
printf '%s\n' backhaul_signal.go candidate_rejection.go helper.go main.go >"$expected"
cmp "$expected" "$tmp/go-sources"
if grep -q '_test.go' "$tmp/go-sources"; then
    echo "test source leaked into production Go build" >&2
    exit 1
fi

unpacked="$tmp/unpacked"
mkdir -p "$unpacked"
tar -xzf "$artifact_dir/em-cli.tar.gz" -C "$unpacked"
grep -a -q 'UnassociatedSTAErrors' "$unpacked/onewifi_em_cli"

echo "PASS rebuild-em-cli compiles every production Go source and validates schema"
