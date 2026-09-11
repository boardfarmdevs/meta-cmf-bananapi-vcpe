#!/usr/bin/env bash
set -euo pipefail

directory=$(realpath "${1:?usage: bash package-release.sh RELEASE_DIRECTORY [OUTPUT_DIRECTORY]}")
destination=$(realpath -m "${2:-$(dirname "$directory")}")
jq -e '.stack == "rdkeasymesh" and .provider == "virtualbox"' "$directory/release.json" >/dev/null
release_id=$(jq -r .release_id "$directory/release.json")
[[ "$release_id" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]
name=rdkeasymesh-$release_id-virtualbox
box=$name.box
test "$(jq -r .box "$directory/release.json")" = "$box"
(cd "$directory"; sha256sum -c SHA256SUMS)
mkdir -p "$destination"
test ! -e "$destination/$name.tar"
files=("$box" "$box.sha256" Vagrantfile README.md release.json source-release.json \
    adapter-files.sha256 adapter-source.tar.gz package-release.sh)
for optional in ACCEPTANCE.md acceptance.json; do
    [ ! -f "$directory/$optional" ] || files+=("$optional")
done
(cd "$directory"; sha256sum "${files[@]}" > SHA256SUMS)
tar -cf "$destination/$name.tar" --transform "s|^|$name/|" -C "$directory" \
    "${files[@]}" SHA256SUMS
(cd "$destination"; sha256sum "$name.tar" > "$name.tar.sha256")
printf 'Windows bundle: %s/%s.tar\nExtract it and run vagrant up --provider=virtualbox.\n' "$destination" "$name"
