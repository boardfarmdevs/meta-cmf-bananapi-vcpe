#!/usr/bin/env bash

# Profile metadata shared by the LXD-VM builder and release tooling.  Ready
# appliances have one immutable client roster.  The universal thin appliance
# selects exactly one roster during import and locks it before provisioning.

easymesh_profile_name() {
    case "${1:-20}" in
        20|small)  printf 'small\n' ;;
        50|medium) printf 'medium\n' ;;
        100|stress) printf 'stress\n' ;;
        *)
            echo "invalid EasyMesh profile: $1 (expected 20, 50 or 100)" >&2
            return 2
            ;;
    esac
}

easymesh_profile_clients() {
    case "$(easymesh_profile_name "${1:-20}")" in
        small) printf '20\n' ;;
        medium) printf '50\n' ;;
        stress) printf '100\n' ;;
    esac
}

easymesh_profile_release_name() {
    printf 'rdkeasymesh-%s-%s\n' \
        "$(easymesh_profile_clients "${1:-20}")" \
        "${EASYMESH_RELEASE_ID:-0903}"
}

easymesh_thin_release_name() {
    printf 'rdkeasymesh-%s-thin\n' "${EASYMESH_RELEASE_ID:-0903}"
}

easymesh_profile_radios() {
    case "$(easymesh_profile_name "${1:-20}")" in
        small) printf '32\n' ;;
        medium) printf '64\n' ;;
        stress) printf '128\n' ;;
    esac
}

easymesh_profile_cpus() {
    case "$(easymesh_profile_name "${1:-20}")" in
        small) printf '6\n' ;;
        medium) printf '8\n' ;;
        stress) printf '12\n' ;;
    esac
}

easymesh_profile_memory() {
    case "$(easymesh_profile_name "${1:-20}")" in
        small) printf '8GiB\n' ;;
        medium) printf '12GiB\n' ;;
        stress) printf '20GiB\n' ;;
    esac
}

easymesh_profile_disk() {
    case "$(easymesh_profile_name "${1:-20}")" in
        small) printf '64GiB\n' ;;
        medium) printf '72GiB\n' ;;
        stress) printf '96GiB\n' ;;
    esac
}
