#!/bin/bash
# wlan-client.sh - stand up a lightweight WLAN client (a dedicated Wi-Fi station,
# NOT another mvx) that associates to an mvx CPE's AP over mac80211_hwsim. Uses
# one radio from the hwsim pool (returns to the pool on delete).
#
#   wlan-client.sh build-image                       # build the self-contained wlan-client-base image
#   wlan-client.sh [-i NNN] [--cohort NAME] [--security MODE] [--band BAND]
#                  [--build-image]
#                  up [ssid] [psk]  # create client and connect
#   wlan-client.sh [-i NNN] status                   # print association state
#   wlan-client.sh [-i NNN] down                     # tear down (radio returns to the pool)
#
# The client runs from a pre-built, self-contained image (alias 'wlan-client-base',
# override with WLAN_CLIENT_IMAGE) that bakes in everything a station needs:
#   * iw + wpa_supplicant runtime libs (libnl3, openssl)
#   * a CONFIG_WNM wpa_supplicant at /usr/local/sbin/wpa_supplicant-wnm so the
#     station HONORS 802.11v BTM steers (EasyMesh-directed roaming) -- the stock
#     Alpine binary has no BSS-TM handler and silently drops steers.
#   * an openrc local.d autostart that (re)connects from /etc/wpa.conf on boot.
# So `up` needs no runtime apk and no in-container compile (the old flow's flaky
# parts). `build-image` builds it once from the minimal Alpine base + the committed
# WNM binary (gen/wpa_supplicant/wpa_supplicant-wnm); `up --build-image` forces a
# rebuild, and `up` auto-builds it the first time if the alias is missing.
#
# -i NNN gives the client an instance suffix so several can run side by side, each
# with its own container, profile, MAC and radio (e.g. -i 1 -> wlan-client-001).
source "$(dirname "$0")/gen-util.sh"

HERE="$(cd "$(dirname "$0")" && pwd)"
BASE_IMG="${WLAN_CLIENT_IMAGE:-wlan-client-base}"   # the self-contained client image
SRC_IMG="${WLAN_CLIENT_SRC_IMAGE:-alpine}"          # minimal base to build it from
WNMBIN="$HERE/wpa_supplicant/wpa_supplicant-wnm"    # committed CONFIG_WNM supplicant
WMD_PIDF=${WMEDIUMD_PIDFILE:-/run/meta-cmf-wmediumd/wmediumd.pid}

INST=""; FORCE_BUILD=0; COHORT=""; SECURITY="auto"; BAND="auto"
while true; do
    case "$1" in
        -i)
            # Force decimal interpretation. Recursive status calls pass the
            # normalized value (for example 010), which printf otherwise treats
            # as octal and silently turns wlan-client-010 into client 008.
            if [[ "$2" =~ ^[0-9]+$ ]]; then
                INST=$(printf "%03d" "$((10#$2))")
            else
                INST="$2"
            fi
            shift 2
            ;;
        --cohort)      COHORT="$2"; shift 2;;
        --security)    SECURITY="$2"; shift 2;;
        --band)        BAND="$2"; shift 2;;
        --build-image) FORCE_BUILD=1; shift;;
        --wnm)         shift;;   # deprecated: WNM is baked into wlan-client-base now (accepted, ignored)
        *)             break;;
    esac
done

CT="wlan-client${INST:+-$INST}"
PROFILE="$CT"

# Initialize a container without physical hwsim devices in its profile, attach
# the requested radios to the stopped instance, and only then start it. LXD 6.7
# on rev130 can wedge image materialization if a physical hwsim NIC is already
# present during `lxc init`. $1=image $2=container [$3=profile] [$4=radio count]
_lxc_launch() {
    local img="$1" ct="$2" prof="${3:-}" radios="${4:-0}" try i r
    for try in 1 2 3; do
        # A failed start leaves the profile device behind. Remove it before the
        # next init so every retry observes the same WLAN-free init ordering.
        if [ -n "$prof" ] && [ "$radios" -gt 0 ]; then
            for r in $(seq 0 $((radios - 1))); do
                lxc profile device remove "$prof" "wlan$r" >/dev/null 2>&1 || true
            done
        fi
        if timeout 90 lxc init "$img" "$ct" ${prof:+-p "$prof"} >/dev/null 2>&1; then
            [ "$radios" -le 0 ] || hwsim_attach_radios "$prof" "$radios"
            timeout 30 lxc start "$ct" >/dev/null 2>&1 || true
        fi
        for i in $(seq 1 30); do lxc exec "$ct" -- true 2>/dev/null && return 0; sleep 1; done
        echo "  $ct did not come up (try $try) -- killing + retrying" >&2
        lxc delete -f "$ct" 2>/dev/null; sleep 2
    done
    return 1
}

_lxc_remove_clean() {
    local ct="$1"
    lxc info "$ct" > /dev/null 2>&1 || return 0
    lxc stop "$ct" --timeout 10 > /dev/null 2>&1 \
        || lxc stop "$ct" --force > /dev/null 2>&1 \
        || true
    lxc delete "$ct" --force > /dev/null 2>&1
}

# Build the self-contained wlan-client-base image from the minimal Alpine base.
_build_base_image() {
    local B=wlan-client-imgbuild P=wlan-client-imgbuild-profile lab_pool
    lab_pool=$(ensure_lxd_lab_pool) || return 1
    [ -f "$WNMBIN" ] || { echo "missing WNM binary: $WNMBIN (build it with wpa_supplicant/build-wnm-supplicant.sh)"; return 1; }
    lxc image info "$SRC_IMG" >/dev/null 2>&1 || { echo "source image '$SRC_IMG' missing on this host (import it first)"; return 1; }
    echo ">> building '$BASE_IMG' from '$SRC_IMG' (iw + wpa_supplicant + baked WNM + autostart)"
    lxc delete -f "$B" 2>/dev/null
    lxc profile delete "$P" 2>/dev/null
    lxc profile create "$P" >/dev/null
    lxc profile device add "$P" root disk path=/ pool="$lab_pool" >/dev/null
    lxc profile device add "$P" eth0 nic nictype=bridged parent=lxdbr0 name=eth0 >/dev/null
    _lxc_launch "$SRC_IMG" "$B" "$P" || { echo ">> could not launch builder"; lxc profile delete "$P" 2>/dev/null; return 1; }
    lxc exec "$B" -- sh -c 'ip link set eth0 up 2>/dev/null; udhcpc -i eth0 -n -q >/dev/null 2>&1 || true'
    echo ">> apk add iw wpa_supplicant"
    lxc exec "$B" -- sh -c 'apk add --no-cache iw wpa_supplicant >/dev/null 2>&1' \
        || { echo ">> apk failed in builder (no internet on eth0/lxdbr0?)"; lxc delete -f "$B"; lxc profile delete "$P" 2>/dev/null; return 1; }
    lxc file push -p "$WNMBIN" "$B/usr/local/sbin/wpa_supplicant-wnm" >/dev/null 2>&1
    lxc exec "$B" -- chmod +x /usr/local/sbin/wpa_supplicant-wnm
    lxc exec "$B" -- /usr/local/sbin/wpa_supplicant-wnm -v >/dev/null 2>&1 \
        || { echo ">> baked WNM binary does not run (missing libs) -- aborting"; lxc delete -f "$B"; lxc profile delete "$P" 2>/dev/null; return 1; }
    lxc exec "$B" -- sh -c 'mkdir -p /etc/local.d; cat > /etc/local.d/wlan.start <<'\''EOS'\''
#!/bin/sh
[ -f /etc/wpa.conf ] || exit 0
ip link set wlan0 up 2>/dev/null
[ -x /usr/local/sbin/wpa_supplicant-wnm ] && SUP=/usr/local/sbin/wpa_supplicant-wnm || SUP=wpa_supplicant
pgrep -f "$SUP" >/dev/null || $SUP -B -i wlan0 -c /etc/wpa.conf -D nl80211 >/tmp/wpa.log 2>&1
i=0; while [ $i -lt 20 ]; do iw dev wlan0 link 2>/dev/null | grep -q Connected && break; i=$((i+1)); sleep 1; done
udhcpc -i wlan0 -n -q >/dev/null 2>&1 || true
EOS
chmod +x /etc/local.d/wlan.start; rc-update add local default >/dev/null 2>&1'
    lxc stop "$B" >/dev/null 2>&1
    lxc image delete "$BASE_IMG" 2>/dev/null
    lxc publish "$B" --alias "$BASE_IMG" >/dev/null 2>&1
    lxc delete -f "$B" 2>/dev/null
    lxc profile delete "$P" 2>/dev/null
    lxc image info "$BASE_IMG" >/dev/null 2>&1 && { echo ">> published image alias '$BASE_IMG'"; return 0; }
    echo ">> publish failed"; return 1
}

case "${1:-up}" in
build-image)
    _build_base_image
    ;;
up)
    SSID="${2:-PlumeSim}"; PSK="$3"
    case "$BAND" in
        auto) FREQ_DIRECTED=; EXPECTED_FREQ= ;;
        2.4)  EXPECTED_FREQ=2437; FREQ_DIRECTED='\n scan_freq=2437\n freq_list=2437' ;;
        5)    EXPECTED_FREQ=5180; FREQ_DIRECTED='\n scan_freq=5180\n freq_list=5180' ;;
        6)    EXPECTED_FREQ=6135; FREQ_DIRECTED='\n scan_freq=6135\n freq_list=6135' ;;
        *) echo "$CT: unsupported band '$BAND' (use auto, 2.4, 5 or 6)" >&2; exit 2 ;;
    esac
    if [ "$SECURITY" = auto ]; then
        if [ -z "$PSK" ]; then
            SECURITY=open
        else
            SECURITY=wpa2
        fi
    fi
    # Current HWSIM OneWifi builds keep iot_ssid non-broadcast.  A directed
    # scan is therefore required regardless of the selected authentication
    # mode. Reset.json describes the physical-platform SAE/PMF intent, while
    # the HWSIM compatibility path deliberately advertises WPA2-PSK; auto
    # follows the observable interface contract.
    SCAN_DIRECTED=
    [ "$SSID" != iot_ssid ] || SCAN_DIRECTED='\n scan_ssid=1'
    if [ "$BAND" = 6 ] && [ "$SECURITY" != sae ]; then
        echo "$CT: 6 GHz requires --security sae and protected management frames" >&2
        exit 2
    fi
    if [ "$BAND" = 6 ] && [ "$SSID" = iot_ssid ]; then
        echo "$CT: hidden iot_ssid does not answer directed 6 GHz probes in the current HWSIM AP" >&2
        exit 2
    fi
    case "$SECURITY" in
        open)
            [ -z "$PSK" ] || { echo "$CT: open security cannot use a passphrase" >&2; exit 2; }
            NET="network={\n ssid=\"$SSID\"$SCAN_DIRECTED$FREQ_DIRECTED\n key_mgmt=NONE\n}"
            ;;
        wpa2)
            [ -n "$PSK" ] || { echo "$CT: WPA2 requires a passphrase" >&2; exit 2; }
            NET="network={\n ssid=\"$SSID\"$SCAN_DIRECTED$FREQ_DIRECTED\n psk=\"$PSK\"\n key_mgmt=WPA-PSK\n}"
            ;;
        sae)
            [ -n "$PSK" ] || { echo "$CT: SAE requires a passphrase" >&2; exit 2; }
            SAE_GLOBAL=
            [ "$BAND" != 6 ] || SAE_GLOBAL='sae_pwe=1\n'
            NET="${SAE_GLOBAL}network={\n ssid=\"$SSID\"$SCAN_DIRECTED$FREQ_DIRECTED\n sae_password=\"$PSK\"\n key_mgmt=SAE\n ieee80211w=2\n}"
            ;;
        *)
            echo "$CT: unsupported security '$SECURITY' (use auto, open, wpa2 or sae)" >&2
            exit 2
            ;;
    esac
    [ -n "$COHORT" ] || COHORT=$([ "$SSID" = iot_ssid ] && echo iot || echo private)
    LAB_POOL=$(ensure_lxd_lab_pool) || exit 1
    # ensure the self-contained image (build once, or on --build-image)
    if [ "$FORCE_BUILD" = 1 ] || ! lxc image info "$BASE_IMG" >/dev/null 2>&1; then
        _build_base_image || { echo "falling back to '$SRC_IMG' + runtime apk"; BASE_IMG="$SRC_IMG"; }
    fi
    _lxc_remove_clean "$CT"
    lxc profile delete "$PROFILE" 2>/dev/null
    lxc profile create "$PROFILE" >/dev/null
    # A lab-level runtime service owns cold-boot order. Explicitly prevent LXD
    # from restoring clients before the controller and extenders have completed
    # onboarding; the OpenRC local.d hook still reconnects whenever this
    # container is deliberately started.
    lxc profile set "$PROFILE" boot.autostart=false >/dev/null
    lxc profile set "$PROFILE" limits.memory=128MB >/dev/null
    lxc profile set "$PROFILE" limits.cpu=1 >/dev/null
    lxc profile device add "$PROFILE" root disk path=/ pool="$LAB_POOL" >/dev/null
    lxc profile device add "$PROFILE" eth0 nic nictype=bridged parent=lxdbr0 name=eth0 >/dev/null
    _lxc_launch "$BASE_IMG" "$CT" "$PROFILE" 1 || { echo "$CT: failed to launch"; exit 1; }
    # Persist intent outside the disposable rootfs so inventory, cold-start and
    # scale tooling can distinguish cohorts without relying on MAC allocation.
    lxc config set "$CT" user.easymesh.cohort "$COHORT"
    lxc config set "$CT" user.easymesh.ssid "$SSID"
    lxc config set "$CT" user.easymesh.security "$SECURITY"
    lxc config set "$CT" user.easymesh.band "$BAND"
    # base image already has iw + wpa_supplicant + the WNM binary; only apk-install
    # if we fell back to the raw Alpine base
    if [ "$BASE_IMG" = "$SRC_IMG" ]; then
        lxc exec "$CT" -- sh -c 'command -v wpa_supplicant >/dev/null && command -v iw >/dev/null || apk add --no-cache wpa_supplicant iw >/dev/null 2>&1'
        [ -f "$WNMBIN" ] && lxc file push -p "$WNMBIN" "$CT/usr/local/sbin/wpa_supplicant-wnm" 2>/dev/null && lxc exec "$CT" -- chmod +x /usr/local/sbin/wpa_supplicant-wnm 2>/dev/null
    fi
    # A running wmediumd has a fixed radio matrix.  Adding a client radio after
    # REGISTER leaves that radio outside the medium until the daemon is
    # refreshed.  Do that as part of client creation, before starting the
    # supplicant, so association and DHCP complete without an operator restart.
    # wmediumd-up.sh replaces the old daemon atomically enough for this lab and
    # preserves the caller's requested baseline SNR.
    if [ -x "$HERE/wmediumd/wmediumd-up.sh" ] &&
       [ -s "$WMD_PIDF" ] &&
       sudo kill -0 "$(cat "$WMD_PIDF")" 2>/dev/null; then
        echo "  wmediumd: refreshing active-radio matrix for $CT"
        SNR="${SNR:-40}" "$HERE/wmediumd/wmediumd-up.sh" up
    fi
    # write the per-instance config and start via the baked autostart (which also
    # persists the connection across container restarts)
    lxc exec "$CT" -- sh -c "printf '$NET\n' > /etc/wpa.conf
        [ -x /etc/local.d/wlan.start ] || { mkdir -p /etc/local.d; printf '#!/bin/sh\n[ -f /etc/wpa.conf ] || exit 0\nip link set wlan0 up\n[ -x /usr/local/sbin/wpa_supplicant-wnm ] \&\& SUP=/usr/local/sbin/wpa_supplicant-wnm || SUP=wpa_supplicant\npgrep -f \"\$SUP\" >/dev/null || \$SUP -B -i wlan0 -c /etc/wpa.conf -D nl80211 >/tmp/wpa.log 2>&1\nudhcpc -i wlan0 -n -q >/dev/null 2>&1 || true\n' > /etc/local.d/wlan.start; chmod +x /etc/local.d/wlan.start; rc-update add local default >/dev/null 2>&1; }
        /etc/local.d/wlan.start"
    # Treat a client as deployed only when both the WLAN association and DHCP
    # lease exist.  The baked startup script normally establishes both; this
    # bounded check catches a broken medium/configuration immediately.
    for n in $(seq 1 20); do
        lxc exec "$CT" -- iw dev wlan0 link 2>/dev/null | grep -q 'Connected to' && break
        sleep 1
    done
    lxc exec "$CT" -- iw dev wlan0 link 2>/dev/null | grep -q 'Connected to' || {
        echo "$CT: failed to associate with $SSID" >&2
        exit 1
    }
    if [ -n "$EXPECTED_FREQ" ]; then
        actual_freq=$(lxc exec "$CT" -- iw dev wlan0 link 2>/dev/null \
            | awk '/freq:/ {print $2; exit}')
        [ "$actual_freq" = "$EXPECTED_FREQ" ] || {
            echo "$CT: expected band $BAND ($EXPECTED_FREQ MHz), associated at ${actual_freq:-unknown}" >&2
            exit 1
        }
    fi
    if ! lxc exec "$CT" -- ip -4 -o addr show wlan0 2>/dev/null | grep -q 'inet '; then
        lxc exec "$CT" -- udhcpc -i wlan0 -n -q >/dev/null 2>&1 || true
    fi
    lxc exec "$CT" -- ip -4 -o addr show wlan0 2>/dev/null | grep -q 'inet ' || {
        echo "$CT: associated but DHCP did not provide an address" >&2
        exit 1
    }

    # Do not let a caller immediately add another station (which refreshes the
    # fixed wmediumd registration matrix) while the controller is still doing
    # the new STA capability exchange. Losing that short exchange leaves a
    # physically associated client absent from STAList/WebUI until it roams.
    # When this is a standalone WLAN test with no controller, skip the gate.
    if [ "${WAIT_EASYMESH_EXPORT:-1}" = 1 ] \
       && lxc info bpibroadband >/dev/null 2>&1 \
       && [ "$(lxc exec bpibroadband -- systemctl is-active em_ctrl 2>/dev/null || true)" = active ]; then
        sta=$(lxc exec "$CT" -- iw dev wlan0 info | awk '/addr/{print $2; exit}')
        exported=0
        # A newly started controller/agent can need more than ten seconds to
        # finish the topology notification and client-capability exchange.  A
        # short timeout turns that healthy convergence into a deployment
        # failure; keep the wait bounded, but cover one full 30-second model
        # reconciliation interval.  Tests may override the poll count without
        # bypassing the readiness contract.
        export_polls=${EASYMESH_EXPORT_POLLS:-150}
        for n in $(seq 1 "$export_polls"); do
            if [ "$(lxc exec bpibroadband -- mysql -N -ubpi -proot OneWifiMesh \
                    -e "select count(*) from STAList where MACAddress='$sta' and Associated=1" \
                    2>/dev/null || true)" = 1 ]; then
                exported=1
                break
            fi
            sleep 0.2
        done
        if [ "$exported" != 1 ]; then
            echo "$CT: associated but EasyMesh controller did not export STA $sta" >&2
            exit 1
        fi
    fi
    "$0" ${INST:+-i $INST} status
    ;;
status)
    lxc info "$CT" >/dev/null 2>&1 || { echo "$CT: not present"; exit 1; }
    echo "$CT MAC: $(lxc exec "$CT" -- cat /sys/class/net/wlan0/address 2>/dev/null)"
    lxc exec "$CT" -- sh -c 'iw dev wlan0 link 2>/dev/null | grep -E "Connected to|SSID|freq" | sed "s/^/  /"; echo "  ip: $(ip -o -4 addr show wlan0 2>/dev/null | awk "{print \$4}")"'
    ;;
down)
    _lxc_remove_clean "$CT"
    lxc profile delete "$PROFILE" 2>/dev/null
    echo "$CT removed (radio returned to pool)"
    ;;
*)
    echo "usage: $0 build-image | [-i NNN] [--security MODE] [--band auto|2.4|5|6] [--build-image] up [ssid] [psk] | status | down"; exit 1;;
esac
