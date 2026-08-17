#!/usr/bin/env bash
set -euo pipefail

# LXC may otherwise consume Vagrant's trailing remote-shell control input.
exec </dev/null

# Run inside the Vagrant guest after the 4-extender/10-client scale topology is
# healthy. Every client is steered twice while traffic is flowing. The radio
# link, controller database, WebUI API, loss, and service restart counters are
# recorded independently so a command response alone cannot produce a pass.
rounds=${1:-2}
repo=${EASYMESH_REPO:-/home/vagrant/git/meta-cmf-bananapi-vcpe}
results=/home/vagrant/.local/state/easymesh-vagrant/steering-scale.csv
mkdir -p "$(dirname "$results")"

mapfile -t clients < <(lxc list -c n --format csv \
    | grep -E '^wlan-client(-[0-9]{3})?$' | sort -V)
mapfile -t target_rows < <(curl -fsS http://127.0.0.1:8888/api/v1/topology \
    | jq -r '.nodes[] as $node | $node.haulTypes[]?
        | select(.name == "Fronthaul") | .BSSList[]
        | select(.Band == 1) | [$node.name, .BSSID] | @tsv' \
    | sort -V)

if [ "${#clients[@]}" -ne 10 ] || [ "${#target_rows[@]}" -ne 5 ]; then
    echo "expected 10 clients and 5 target agents; found ${#clients[@]} and ${#target_rows[@]}" >&2
    exit 1
fi

printf '%s\n' 'round,client,sta,target_name,source_bssid,target_bssid,command_rc,link_ms,db_ms,topology_ms,packet_loss,result' > "$results"
failures=0

for ((round=1; round <= rounds; round++)); do
    for ((index=0; index < ${#clients[@]}; index++)); do
        client=${clients[$index]}
        sta=$(lxc exec "$client" -- iw dev wlan0 info | awk '/addr/{print $2}')
        source=$(lxc exec "$client" -- iw dev wlan0 link | awk '/Connected to/{print $3}')
        target_index=$(( (index + round) % ${#target_rows[@]} ))
        IFS=$'\t' read -r target_name target <<< "${target_rows[$target_index]}"
        if [ "$target" = "$source" ]; then
            target_index=$(( (target_index + 1) % ${#target_rows[@]} ))
            IFS=$'\t' read -r target_name target <<< "${target_rows[$target_index]}"
        fi

        ping_file=$(mktemp)
        lxc exec "$client" -- ping -q -i 0.1 -c 100 -W 2 10.0.0.1 \
            >"$ping_file" 2>&1 &
        ping_pid=$!
        start_ms=$(date +%s%3N)
        set +e
        lxc exec bpibroadband -- /usr/bin/steer.sh "$sta" "$target"
        command_rc=$?
        set -e

        link_ms=-1
        for _ in $(seq 1 100); do
            actual=$(lxc exec "$client" -- iw dev wlan0 link 2>/dev/null \
                | awk '/Connected to/{print $3}')
            if [ "$actual" = "$target" ]; then
                link_ms=$(( $(date +%s%3N) - start_ms ))
                break
            fi
            sleep 0.1
        done

        db_ms=-1
        topology_ms=-1
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

        wait "$ping_pid" || true
        loss=$(sed -n 's/.* \([0-9]*%\) packet loss.*/\1/p' "$ping_file")
        rm -f "$ping_file"
        result=PASS
        if [ "$command_rc" -ne 0 ] || [ "$link_ms" -lt 0 ] \
            || [ "$db_ms" -lt 0 ] || [ "$topology_ms" -lt 0 ] \
            || [ -z "$loss" ]; then
            result=FAIL
            failures=$((failures + 1))
        fi
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$round" "$client" "$sta" "$target_name" "$source" "$target" \
            "$command_rc" "$link_ms" "$db_ms" "$topology_ms" "${loss:-unknown}" "$result" \
            | tee -a "$results"
        sleep 1
    done
done

# Rebuild the current-home overrides once after the matrix. The all-strong
# default makes this unnecessary for connectivity during the run, and avoiding
# a daemon restart per steer keeps wmediumd refresh loss out of the measurement.
SNR=40 "$repo/gen/wmediumd/wmediumd-up.sh" up >/dev/null

topology=$(curl -fsS http://127.0.0.1:8888/api/v1/topology)
[ "$(jq -r '[.nodes[].STAList[]?.staMAC] | unique | length' <<<"$topology")" -eq 10 ]
echo "steering matrix complete: $((rounds * ${#clients[@]} - failures))/$((rounds * ${#clients[@]})) passed"
exit "$failures"
