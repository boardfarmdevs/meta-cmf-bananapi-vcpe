#!/bin/sh

# Instant process PSS/RSS inventory. BusyBox /bin/sh compatible and safe to
# execute or source from a diagnostic shell.

printf "%8s %10s %10s %-12s %s\n" \
       "PID" "PSS_KB" "RSS_KB" "USER" "COMMAND"

tmp="/tmp/pss.$$"

# Truncate rather than append to a stale file when this script is sourced.
: > "$tmp" || return 1 2>/dev/null || exit 1

for p in /proc/[0-9]*; do
    pid="${p#/proc/}"

    if [ -r "$p/smaps_rollup" ]; then
        pss=$(awk '/^Pss:/ { print $2; exit }' "$p/smaps_rollup" 2>/dev/null)
    elif [ -r "$p/smaps" ]; then
        pss=$(awk '/^Pss:/ { sum += $2 } END { print sum+0 }' \
                  "$p/smaps" 2>/dev/null)
    else
        continue
    fi

    [ -n "$pss" ] || pss=0

    rss=$(awk '/^VmRSS:/ { print $2; exit }' "$p/status" 2>/dev/null)
    [ -n "$rss" ] || rss=0

    uid=$(awk '/^Uid:/ { print $2; exit }' "$p/status" 2>/dev/null)
    user=$(awk -F: -v uid="$uid" '
        $3 == uid { print $1; found=1; exit }
        END { if (!found) print uid }
    ' /etc/passwd 2>/dev/null)

    cmd=$(tr '\000' ' ' < "$p/cmdline" 2>/dev/null)
    if [ -z "$cmd" ] && [ -r "$p/comm" ]; then
        cmd="[$(cat "$p/comm" 2>/dev/null)]"
    fi

    printf "%s\t%s\t%s\t%s\t%s\n" \
           "$pss" "$pid" "$rss" "$user" "$cmd" >> "$tmp"
done

sort -nr "$tmp" |
awk -F '\t' '{
    printf "%8s %10s %10s %-12s ", $2, $1, $3, $4
    for (i=5; i<=NF; i++) {
        if (i > 5)
            printf "\t"
        printf "%s", $i
    }
    printf "\n"
}'

rm -f "$tmp"
