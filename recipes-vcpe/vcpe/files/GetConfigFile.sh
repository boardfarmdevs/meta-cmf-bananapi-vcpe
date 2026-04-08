#!/bin/sh

echo "$@" > /tmp/GetConfigFile.txt

DEST_FILE="$1"
cp /nvram/ConfigFile "$DEST_FILE"

cat /nvram/ConfigFile >> /tmp/GetConfigFile.txt
