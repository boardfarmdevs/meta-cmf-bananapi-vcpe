#!/bin/bash

easymesh_profile_name() {
    case "${1:-unified}" in
        100|unified) printf 'unified\n' ;;
        *) echo 'one appliance provides capacity for 100 clients; select the active roster in the room viewer' >&2; return 2 ;;
    esac
}

easymesh_profile_release_name() {
    printf '%s\n' "${EASYMESH_LXD_NAME:-${EASYMESH_LAB_NAME:-easymesh}}"
}

easymesh_thin_release_name() {
    printf '%s-thin\n' "$(easymesh_profile_release_name)"
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
