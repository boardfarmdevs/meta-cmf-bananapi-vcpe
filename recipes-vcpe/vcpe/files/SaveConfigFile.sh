#!/bin/sh

echo "$@" > /tmp/SaveConfigFile.txt

SOURCE_FILE="$1"
cp "$SOURCE_FILE" /nvram/ConfigFile

cat /nvram/ConfigFile >> /tmp/SaveConfigFile.txt
