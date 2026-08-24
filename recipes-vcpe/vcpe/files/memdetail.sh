#!/bin/sh

# BusyBox /bin/sh compatible process and VMA memory breakdown.
# Usage: memdetail [-n number_of_entries] PID [PID ...]

LC_ALL=C
export LC_ALL

TOP=12

case "$1" in
    -n|--top)
        if [ "$#" -lt 2 ]; then
            echo "Missing value after $1" >&2
            exit 2
        fi
        TOP="$2"
        shift 2
        ;;
esac

case "$TOP" in
    ''|*[!0-9]*|0)
        echo "Top count must be a positive integer" >&2
        exit 2
        ;;
esac

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 [-n top_count] PID [PID ...]" >&2
    exit 2
fi

show_summary()
{
    pid="$1"
    file="/proc/$pid/smaps_rollup"

    if [ ! -r "$file" ]; then
        echo "  $file is not readable"
        return
    fi

    awk '
        function row(label, value) {
            printf "  %-22s %10d %10.2f\n",
                   label, value + 0, (value + 0) / 1024
        }

        /^Rss:/             { rss=$2 }
        /^Pss:/             { pss=$2 }
        /^Pss_Anon:/        { pss_anon=$2; have_types=1 }
        /^Pss_File:/        { pss_file=$2; have_types=1 }
        /^Pss_Shmem:/       { pss_shmem=$2; have_types=1 }
        /^Shared_Clean:/    { shared_clean=$2 }
        /^Shared_Dirty:/    { shared_dirty=$2 }
        /^Private_Clean:/   { private_clean=$2 }
        /^Private_Dirty:/   { private_dirty=$2 }
        /^Swap:/            { swap=$2 }
        /^SwapPss:/         { swap_pss=$2 }
        /^AnonHugePages:/   { anon_huge=$2 }

        END {
            printf "  %-22s %10s %10s\n", "METRIC", "KiB", "MiB"
            row("RSS", rss)
            row("PSS", pss)
            if (have_types) {
                row("  anonymous PSS", pss_anon)
                row("  file-backed PSS", pss_file)
                row("  shmem PSS", pss_shmem)
            }
            row("private RSS", private_clean + private_dirty)
            row("  private clean", private_clean)
            row("  private dirty", private_dirty)
            row("shared RSS", shared_clean + shared_dirty)
            row("swap", swap)
            row("swap PSS", swap_pss)
            if (anon_huge > 0)
                row("anonymous huge pages", anon_huge)
        }
    ' "$file"
}

emit_mappings()
{
    pid="$1"
    grouped="$2"

    awk -v grouped="$grouped" '
        function reset_values() {
            size=0; rss=0; pss=0
            private_clean=0; private_dirty=0
            shared_clean=0; shared_dirty=0; swap=0
        }
        function flush(    private, shared, key) {
            if (!have_mapping)
                return
            private = private_clean + private_dirty
            shared = shared_clean + shared_dirty
            if (grouped) {
                key = name
                total_size[key] += size
                total_rss[key] += rss
                total_pss[key] += pss
                total_private[key] += private
                total_shared[key] += shared
                total_swap[key] += swap
            } else {
                printf "%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\t%s\n",
                       pss, rss, private, shared, size, swap, perms, address, name
            }
        }
        /^[0-9a-fA-F]+-[0-9a-fA-F]+[[:space:]]/ {
            flush()
            have_mapping=1
            reset_values()
            address=$1
            perms=$2
            name=$0
            for (i=1; i<=5; i++)
                sub(/^[^[:space:]]+[[:space:]]*/, "", name)
            sub(/^[[:space:]]+/, "", name)
            sub(/[[:space:]]+$/, "", name)
            if (name == "")
                name="[anonymous]"
            next
        }
        /^Size:/            { size=$2 }
        /^Rss:/             { rss=$2 }
        /^Pss:/             { pss=$2 }
        /^Private_Clean:/   { private_clean=$2 }
        /^Private_Dirty:/   { private_dirty=$2 }
        /^Shared_Clean:/    { shared_clean=$2 }
        /^Shared_Dirty:/    { shared_dirty=$2 }
        /^Swap:/            { swap=$2 }
        END {
            flush()
            if (grouped) {
                for (key in total_pss) {
                    printf "%d\t%d\t%d\t%d\t%d\t%d\t-\t-\t%s\n",
                           total_pss[key], total_rss[key], total_private[key],
                           total_shared[key], total_size[key], total_swap[key], key
                }
            }
        }
    ' "/proc/$pid/smaps" 2>/dev/null
}

print_table()
{
    printf "  %10s %10s %10s %10s %10s %10s %-5s %-17s %s\n" \
           "PSS_KB" "RSS_KB" "PRIV_KB" "SHRD_KB" "SIZE_KB" "SWAP_KB" \
           "PERM" "ADDRESS" "MAPPING"

    awk -F '\t' '{
        printf "  %10d %10d %10d %10d %10d %10d %-5s %-17s %s\n",
               $1, $2, $3, $4, $5, $6, $7, $8, $9
    }'
}

for pid in "$@"; do
    case "$pid" in
        ''|*[!0-9]*)
            echo "Skipping invalid PID: $pid" >&2
            continue
            ;;
    esac

    if [ ! -d "/proc/$pid" ]; then
        echo "PID $pid does not exist" >&2
        continue
    fi

    cmd=$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
    if [ -z "$cmd" ]; then
        cmd="[$(cat "/proc/$pid/comm" 2>/dev/null)]"
    fi

    echo
    echo "================================================================"
    echo "PID $pid: $cmd"
    echo "================================================================"
    echo
    echo "Process-wide summary:"
    show_summary "$pid"

    if [ ! -r "/proc/$pid/smaps" ]; then
        echo
        echo "  /proc/$pid/smaps is not readable"
        continue
    fi

    echo
    echo "Top $TOP mapped objects, combined by pathname:"
    emit_mappings "$pid" 1 | sort -nr | head -n "$TOP" | print_table

    echo
    echo "Top $TOP individual VMAs:"
    emit_mappings "$pid" 0 | sort -nr | head -n "$TOP" | print_table
done
