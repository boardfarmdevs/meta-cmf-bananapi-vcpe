#!/usr/bin/env bash
set -euo pipefail

exec </dev/null

results=/home/vagrant/.local/state/easymesh-vagrant/steering-return.csv
mkdir -p "$(dirname "$results")"
printf '%s\n' 'client,sta,direction,source_bssid,target_bssid,link_ms,db_ms,topology_ms,result' > "$results"

mapfile -t targets < <(curl -fsS http://127.0.0.1:8888/api/v1/topology \
    | jq -r '.nodes[] | .haulTypes[]? | select(.name == "Fronthaul")
        | .BSSList[] | select(.Band == 1) | .BSSID' \
    | sort -u)
[ "${#targets[@]}" -eq 5 ]

steer_and_verify() {
    local client=$1 sta=$2 direction=$3 source=$4 target=$5
    local start_ms actual db_bssid link_ms=-1 db_ms=-1 topology_ms=-1
    start_ms=$(date +%s%3N)
    lxc exec bpibroadband -- /usr/bin/steer.sh "$sta" "$target"
    for _ in $(seq 1 100); do
        actual=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
            | awk '/Connected to/{print $3}')
        if [ "$actual" = "$target" ]; then
            link_ms=$(( $(date +%s%3N) - start_ms ))
            break
        fi
        sleep 0.1
    done
    for _ in $(seq 1 100); do
        if [ "$db_ms" -lt 0 ]; then
            db_bssid=$(lxc exec bpibroadband -- mysql -N -ubpi -proot \
                OneWifiMesh -e "select BSSID from STAList where MACAddress='$sta' and Associated=1 limit 1" \
                2>/dev/null || true)
            [ "$db_bssid" = "$target" ] \
                && db_ms=$(( $(date +%s%3N) - start_ms ))
        fi
        if [ "$topology_ms" -lt 0 ] \
            && curl -fsS http://127.0.0.1:8888/api/v1/topology \
                | jq -e --arg sta "$sta" --arg target "$target" '
                    ([.nodes[]
                      | select(any(.haulTypes[]?.BSSList[]?; .BSSID == $target))
                      | .id][0]) as $target_node
                    | any(.nodes[] | select(.id == $target_node) | .STAList[]?;
                          .staMAC == $sta)' >/dev/null; then
            topology_ms=$(( $(date +%s%3N) - start_ms ))
        fi
        [ "$db_ms" -ge 0 ] && [ "$topology_ms" -ge 0 ] && break
        sleep 0.1
    done
    result=PASS
    if [ "$link_ms" -lt 0 ] || [ "$db_ms" -lt 0 ] || [ "$topology_ms" -lt 0 ]; then
        result=FAIL
    fi
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$client" "$sta" "$direction" "$source" "$target" \
        "$link_ms" "$db_ms" "$topology_ms" "$result" | tee -a "$results"
    [ "$result" = PASS ]
}

for client in wlan-client-001 wlan-client-003; do
    sta=$(lxc exec "$client" -- iw dev wlan0 info | awk '/addr/{print $2}')
    original=$(lxc exec "$client" -- iw dev wlan0 link | awk '/Connected to/{print $3}')
    away=
    for candidate in "${targets[@]}"; do
        if [ "$candidate" != "$original" ]; then
            away=$candidate
            break
        fi
    done
    [ -n "$away" ]
    steer_and_verify "$client" "$sta" away "$original" "$away"
    sleep 2
    steer_and_verify "$client" "$sta" return "$away" "$original"
    sleep 2
done

echo 'return-path steering regression: 4/4 passed'
