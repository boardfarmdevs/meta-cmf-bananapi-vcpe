#!/usr/bin/env bash
# The lab's extenders on a wired backhaul (EASYMESH_WIRED_EXTENDERS, default 1): the
# controller's wired LAN port, then bpiap-004 with gen/wired-extender.sh, which also points
# the room service at the rooms with it (worlds-wired). The runtime starts it after the
# medium at every boot. The rooms know one wired extender (extender_5).
set -euo pipefail
exec </dev/null

count=${EASYMESH_WIRED_EXTENDERS:-1}
gen=${EASYMESH_GEN:-/home/easymesh/git/meta-cmf-bananapi-vcpe/gen}
[[ "$count" =~ ^[01]$ ]] || { echo "EASYMESH_WIRED_EXTENDERS must be 0 or 1" >&2; exit 2; }
[ "$count" -eq 1 ] || { echo 'no wired extender'; exit 0; }

"$gen/wired-extender.sh" lanport
"$gen/wired-extender.sh" up 4
"$gen/wired-extender.sh" status
