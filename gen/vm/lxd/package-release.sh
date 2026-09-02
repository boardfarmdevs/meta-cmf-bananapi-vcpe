#!/usr/bin/env bash
set -euo pipefail

# Turn one exported bundle directory into the single file handed to Google
# Drive.  The VM backup is already zstd-compressed, so the outer tar is left
# uncompressed to avoid wasting hours and temporary storage on recompression.

bundle=${1:-$(pwd)}
bundle=$(realpath "$bundle")
[ -d "$bundle" ] || { echo "bundle directory is missing: $bundle" >&2; exit 1; }
[ -f "$bundle/release.json" ] || { echo "release.json is missing from $bundle" >&2; exit 1; }
[ -f "$bundle/SHA256SUMS" ] || { echo "SHA256SUMS is missing from $bundle" >&2; exit 1; }
(
    cd "$bundle"
    sha256sum -c SHA256SUMS
)

parent=$(dirname "$bundle")
leaf=$(basename "$bundle")
case "$leaf" in
    rdkeasymesh-0831-thin|prplmesh-0831-thin)
        default_output=$parent/$leaf.tar
        ;;
    *)
        default_output=$parent/$leaf-bundle.tar
        ;;
esac
output=${2:-$default_output}
case "$output" in
    "$bundle"/*) echo 'output must not be inside the bundle being archived' >&2; exit 2 ;;
esac
tar -C "$parent" -cf "$output" "$leaf"
(
    cd "$(dirname "$output")"
    sha256sum "$(basename "$output")" > "$(basename "$output").sha256"
)
ls -lh "$output" "$output.sha256"
