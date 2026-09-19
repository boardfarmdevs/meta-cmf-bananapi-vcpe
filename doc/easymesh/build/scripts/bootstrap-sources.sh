#!/usr/bin/env bash
set -euo pipefail

layer=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
workspace=${TREE:-$(dirname "$layer")}
manifest=$layer/doc/easymesh/build/manifest.xml
jobs=${BUILD_THREADS:-$(nproc)}

command -v repo >/dev/null 2>&1 || {
    echo 'repo is missing; follow the host setup in doc/easymesh/build/README.md' >&2
    exit 1
}
test -f "$manifest"
mkdir -p "$workspace"
cd "$workspace"

if [ ! -d .repo ]; then
    repo init -u https://code.rdkcentral.com/r/manifests -b kirkstone -m rdkb-bpi-nosrc.xml
fi
install -m 0644 "$manifest" .repo/manifests/manifest.xml
repo init -m manifest.xml
repo sync -j"$jobs" --no-clone-bundle

python3 - "$manifest" "$workspace" <<'PY'
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as tree

manifest, workspace = map(pathlib.Path, sys.argv[1:])
for project in tree.parse(manifest).findall('project'):
    directory = workspace / project.get('path', project.get('name'))
    expected = project.get('revision')
    actual = subprocess.check_output(['git', '-C', directory, 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise SystemExit(f'Pinned source mismatch: {directory}: {actual} != {expected}')
print('Pinned upstream source tree verified.')
PY

git -C "$layer" status --porcelain
