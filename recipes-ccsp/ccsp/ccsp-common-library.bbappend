FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://0001-fix-ansc-ipv6-compatible.patch"

CFLAGS_remove = " -U_ANSC_IPV6_COMPATIBLE_"
CFLAGS_append = " -D_ANSC_IPV6_COMPATIBLE_ -DSERCOMM_FIX_ANSC_IPV6_COMPATIBLE_"

vcpe_fix_vendor_id() {
    vendor_h="${D}${includedir}/ccsp/ccsp_vendor.h"
    if [ -f "$vendor_h" ]; then
        sed -i 's|#define CONFIG_VENDOR_ID .*|#define CONFIG_VENDOR_ID "FFFFFF"|' "$vendor_h"
    fi
}
do_install[postfuncs] += "vcpe_fix_vendor_id"

# Revert bpir4's After=PsmSsp.service on gwprovapp -- 25s circular wait:
# PsmSsp's utopiaInitCheck.sh polls /tmp/utopia_inited which gwprovapp creates.
vcpe_fix_gwprovapp_after() {
    svc="${D}${systemd_unitdir}/system/gwprovapp.service"
    if [ -f "$svc" ]; then
        sed -i 's/^After=PsmSsp.service$/After=securemount.service/' "$svc"
    fi
}
do_install[postfuncs] += "vcpe_fix_gwprovapp_after"

# mac80211_hwsim moves an entire wiphy with an LXD physical NIC.  OneWifi
# creates AP/STA virtual interfaces on that wiphy but does not delete them when
# it stops.  LXD therefore returns a "dirty" phy to the host, then on the next
# container start moves every retained sibling into the new namespace.  Its
# attempt to rename the assigned pool interface to wlan0 fails because a stale
# OneWifi wlan0 already exists, leaving the container in ABORTING/STOPPED state.
#
# Delete only child netdevs on OneWifi shutdown and retain the physical pool
# interface owned by LXD.  It is normally wlan0.  If an earlier dirty start
# already collided, LXD's assigned interface still has its temporary phys*
# name; retain that instead and remove the stale wlan0 so the same shutdown
# repairs the radio.  On host/VM reboot the module recreates the pool, while a
# normal lxc stop/restart now returns a reusable one-netdev phy.
vcpe_clean_hwsim_vifs_on_onewifi_stop() {
    svc="${D}${systemd_unitdir}/system/onewifi.service"
    if [ -f "$svc" ] && ! grep -q 'vcpe-hwsim-child-cleanup' "$svc"; then
        sed -i '/^ExecStopPost=/i ExecStopPost=/bin/sh -c '\''\: vcpe-hwsim-child-cleanup; keep=wlan0; for d in /sys/class/net/phys*/phy80211; do [ -e "$d" ] || continue; keep=$(basename $(dirname "$d")); break; done; for d in /sys/class/net/*/phy80211; do [ -e "$d" ] || continue; n=$(basename $(dirname "$d")); [ "$n" = "$keep" ] || iw dev "$n" del 2>/dev/null || true; done; [ "$keep" = wlan0 ] || ip link set "$keep" name wlan0'\''' "$svc"
        bbnote "meta-cmf-bananapi-vcpe: OneWifi stop removes hwsim child interfaces before LXD reclaims the phy"
    fi
}
do_install[postfuncs] += "vcpe_clean_hwsim_vifs_on_onewifi_stop"
