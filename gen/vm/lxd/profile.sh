#!/bin/bash

easymesh_profile_name() {
    case "${1:-unified}" in
        100|unified) printf 'unified\n' ;;
        *) echo '0913 uses one appliance with capacity for 100 clients; select the active roster in the room viewer' >&2; return 2 ;;
    esac
}

easymesh_profile_release_name() {
    printf 'rdkeasymesh-%s\n' "${EASYMESH_RELEASE_ID:-0913}"
}

easymesh_thin_release_name() {
    printf 'rdkeasymesh-%s-thin\n' "${EASYMESH_RELEASE_ID:-0913}"
}

easymesh_profile_clients() {
    easymesh_profile_name "${1:-unified}" >/dev/null || return
    printf '100\n'
}

easymesh_profile_radios() {
    easymesh_profile_name "${1:-unified}" >/dev/null || return
    printf '128\n'
}

easymesh_profile_cpus() {
    easymesh_profile_name "${1:-unified}" >/dev/null || return
    printf '8\n'
}

easymesh_profile_memory() {
    easymesh_profile_name "${1:-unified}" >/dev/null || return
    printf '16GiB\n'
}

easymesh_profile_disk() {
    easymesh_profile_name "${1:-unified}" >/dev/null || return
    printf '96GiB\n'
}
