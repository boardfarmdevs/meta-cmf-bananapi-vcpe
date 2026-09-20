#!/usr/bin/env bash

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    echo "source $0 [lab-name]" >&2
    exit 2
fi

easymesh_lab_name=${1:-${EASYMESH_LAB_NAME:-easymesh}}
case "$easymesh_lab_name" in
    [a-z0-9][a-z0-9-]* ) ;;
    *) echo 'lab name must use lowercase letters, numbers and hyphens' >&2; return 2 ;;
esac

if [ -n "${EASYMESH_PORT_BASE:-}" ]; then
    easymesh_port_base=$EASYMESH_PORT_BASE
else
    easymesh_hash=$(printf '%s' "$easymesh_lab_name" | cksum | awk '{print $1}')
    easymesh_port_base=$((20000 + (easymesh_hash % 1000) * 10))
fi
case "$easymesh_port_base" in
    ''|*[!0-9]*) echo 'EASYMESH_PORT_BASE must be an integer' >&2; return 2 ;;
esac
[ "$easymesh_port_base" -ge 1024 ] && [ "$easymesh_port_base" -le 65530 ] || {
    echo 'EASYMESH_PORT_BASE must leave six usable TCP ports' >&2; return 2;
}

export EASYMESH_LAB_NAME=$easymesh_lab_name
export EASYMESH_LXD_NAME=${EASYMESH_LXD_NAME:-$easymesh_lab_name}
export EASYMESH_LXD_STORAGE=${EASYMESH_LXD_STORAGE:-$easymesh_lab_name-pool}
export EASYMESH_PORT_BASE=$easymesh_port_base
export EASYMESH_WEBUI_PORT=${EASYMESH_WEBUI_PORT:-$((easymesh_port_base + 0))}
export WMEDIUMD_CONSOLE_PORT=${WMEDIUMD_CONSOLE_PORT:-$((easymesh_port_base + 1))}
export EASYMESH_ROOM_DEMO_PORT=${EASYMESH_ROOM_DEMO_PORT:-$((easymesh_port_base + 2))}
export LAB_LXD_UI_PORT=${LAB_LXD_UI_PORT:-$((easymesh_port_base + 3))}
export LAB_GRAFANA_PORT=${LAB_GRAFANA_PORT:-$((easymesh_port_base + 4))}
export LAB_OUTER_METRICS_PORT=${LAB_OUTER_METRICS_PORT:-$((easymesh_port_base + 5))}

printf 'lab=%s vm=%s pool=%s ports=%s-%s\n' \
    "$EASYMESH_LAB_NAME" "$EASYMESH_LXD_NAME" "$EASYMESH_LXD_STORAGE" \
    "$EASYMESH_WEBUI_PORT" "$LAB_OUTER_METRICS_PORT"
