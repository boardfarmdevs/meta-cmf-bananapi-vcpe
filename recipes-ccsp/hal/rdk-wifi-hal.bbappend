CFLAGS_append = " -Wno-error=format"

FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# Upstream commit 07a0822e (RDKB-62554, STA MLO connection) uses
# DEFAULT_MLD_ALLOWED_PHY without ever defining it, breaking the build.
SRC_URI += "file://0001-wifi_hal_nl80211-define-DEFAULT_MLD_ALLOWED_PHY.patch"

# get_rdk_radio_indices() requires the runtime-detected phy index to match
# InterfaceMap.json's hardcoded "phy_index": 0 -- true on real BananaPi
# hardware (one physical chip, always index 0), false under mac80211_hwsim in
# an LXD container (keeps its host-side hwsim index, e.g. 40; the kernel
# refuses to rename any wiphy to "phy0" while the host's real WiFi hardware
# already holds that name). See patch header for the full trace
# (map_rdk_radios_and_indexes -> "Failure to fetch radio map for the phy!" ->
# wifi_hal_init aborts -> onewifi.service never comes up).
SRC_URI += "file://0002-get_rdk_radio_indices-dont-match-phy_index-single-phy.patch"

# Same phy_index-vs-InterfaceMap.json-config mismatch, different function: this one left
# radio->interface_map completely empty (every interface skipped, set_interface_properties
# returns -1 for all of them), which crashed something downstream that assumes at least one
# interface exists per radio -- the actual segfault this session was chasing (dmesg:
# repeating write-fault in librdk_wifihal.so right after init_nl80211's interface dump,
# on every systemd Restart=always cycle). See patch header for the full trace.
SRC_URI += "file://0003-set_interface_properties-dont-match-phy_index-single-phy.patch"

# HWSIM_RADIO scopes capability adaptations to the virtual target. Spectrum
# management is intentionally left enabled: the old 0006 suppression was an
# exploratory START_AP workaround superseded by the malformed-ACL diagnosis.
CFLAGS_append = " -DHWSIM_RADIO"

# Embedded hostapd otherwise retains a departed hwsim AP peer for five minutes,
# masking a future authorization edge when a steering test returns to that AP.
# Use normal hostapd liveness probing with a bounded lab-only aging interval.
SRC_URI += "file://0030-hwsim-bound-ap-station-inactivity-aging.patch"

# THE actual root cause of "-95 Operation not supported" on VAP beacon-start
# (0004/0005/0006 above and ccsp-one-wifi's 0004/0005 all turned out to be red
# herrings, or genuinely-wrong-but-not-blocking defaults): nl80211_put_acl()
# sends NL80211_ATTR_MAC_ADDRS as a bare u32 when ACL is disabled, violating
# its kernel netlink attribute policy (expects NLA_NESTED). Not hwsim-specific
# -- a real, universal bug -- so applied unconditionally, no HWSIM_RADIO gate.
# Root-caused via a raw netlink capture, decoded with pyroute2's own nl80211
# attribute parser, and confirmed against a plain-hostapd control test that
# succeeded on the same wiphy with the same channel/security config minus this
# attribute. See patch header for the full trace.
SRC_URI += "file://0007-nl80211_put_acl-fix-MAC_ADDRS-attribute-type.patch"

# 0007 fixed the "disabled ACL" branch's attribute-type bug (universal, no HWSIM_RADIO
# gate needed), but mesh_backhaul VAPs (mac_filter_enable=true) reach the OTHER,
# already-correctly-nested "enabled" branch and STILL get -EOPNOTSUPP: confirmed via a
# second raw netlink capture that mac80211_hwsim advertises no MAC ACL capability at
# all, so cfg80211 rejects any ACL_POLICY/MAC_ADDRS pair regardless of whether it's
# well-formed. This one IS hwsim-specific (real hardware supports ACL), so it's gated
# behind HWSIM_RADIO -- skips nl80211_put_acl() entirely rather than fixing its content.
SRC_URI += "file://0008-skip-acl-under-hwsim.patch"

# THE final blocker for the EasyMesh backhaul link. STA-mode management-frame
# registration includes WLAN_FC_STYPE_BEACON (EasyMesh+BananaPi only), which
# cfg80211/mac80211_hwsim rejects with -EINVAL on a managed interface. That
# aborts nl80211_register_mgmt_frames(), so wifi_drv_set_operstate() returns
# early and never sets interface->vap_configured = true -- and the global event
# dispatcher silently drops EVERY driver event for that interface, including
# NL80211_CMD_AUTHENTICATE. Net effect: 802.11 auth succeeds on the air, but
# wpa_supplicant's SME never sees EVENT_AUTH, so it never associates and the
# connect just times out and retries forever. See patch header for the full trace.
SRC_URI += "file://0010-dont-register-beacon-frames-on-sta-under-hwsim.patch"

# Last blocker for the backhaul DATA path. wifi_drv_set_operstate() in this HAL was
# repurposed into a VAP-configuration callback and never sends IFLA_OPERSTATE, so a
# fully-associated, 4-way-handshake-complete station stays IF_OPER_DORMANT forever.
# Linux holds a dormant bridge port in the non-forwarding "disabled" state, so zero
# traffic crossed the 4-addr/WDS backhaul despite the link being up and bridged.
# Not HWSIM-gated: this is a real, universal gap. See patch header for the full trace.
SRC_URI += "file://0011-set-sta-operstate-up-so-bridge-forwards.patch"

# platform_create_vap() (controller-only code path: only ever called with a real map once
# EasyMesh is actually creating/enabling VAPs) dereferences its `map` argument with no NULL
# check, behind an MLD/802.11be-only branch that mac80211_hwsim doesn't implement -- so this
# was apparently never exercised with an actual map before. Confirmed via core dump: read
# fault at a small offset matching &((wifi_vap_info_map_t*)NULL)->vap_array[0].
#
# Applied via do_patch_append (not plain SRC_URI) because the target file
# (platform/banana-pi/platform.c) lives one directory *above* S ("${WORKDIR}/git/src"),
# and `patch` refuses diff paths containing ".." for safety -- so apply it with an explicit
# `-d` one level up instead.
PLATFORM_CREATE_VAP_NULL_PATCH := "${THISDIR}/${BPN}/0004-platform_create_vap-guard-against-NULL-map.patch"

# Second, distinct bug in the same function: once `map` is non-NULL, the loop can still
# reach for_each_mld_link(link_bss, hapd), which expands to a raw `hapd->mld->links`
# dereference with no NULL check inside the macro itself. Under mac80211_hwsim no real
# MLO/802.11be link negotiation ever runs, so hapd->mld is never allocated even though
# wifi_hal_is_mld_enabled() can still return true from static config alone. Every other
# for_each_mld_link call site in this codebase (see src/wifi_hal_hostapd.c) already guards
# with "hapd->mld != NULL" first; this applies the same established guard here. Confirmed
# via a second core dump, after 0004 alone was verified compiled-in but insufficient.
PLATFORM_CREATE_VAP_MLD_NULL_PATCH := "${THISDIR}/${BPN}/0005-platform_create_vap-guard-against-NULL-hapd-mld.patch"

# THE actual root cause of the EasyMesh backhaul link never associating (0007/0008
# fixed the beacon-start blocker; both sides confirmed beaconing/scanning correctly
# after that): platform_get_ssid_default()/platform_get_keypassphrase_default() are
# supposed to source the backhaul AP's (not just the backhaul STA's) SSID/passphrase
# from EasymeshCfg.json -- platform_get_ssid_default()'s own comment already says
# "mesh STA or mesh backhaul" -- but the actual `if` only ever checked
# is_wifi_hal_vap_mesh_sta(), never is_wifi_hal_vap_mesh_backhaul(). So the backhaul
# AP silently broadcast the same generic SSID as every other VAP instead of
# "mesh_backhaul", and the extender's own scan-based SSID filter correctly (if
# frustratingly) never matched it. Confirmed via the extender's wifiCtrl.txt +  a
# raw netlink capture of the scan-complete event: kernel-level scanning/multicast
# event delivery both work fine, the mismatch was purely the broadcast SSID itself.
PLATFORM_BACKHAUL_SSID_PATCH := "${THISDIR}/${BPN}/0009-backhaul-ssid-passphrase-for-mesh-backhaul-ap.patch"
PLATFORM_WDS_STA_METRICS_PATCH := "${THISDIR}/${BPN}/0026-include-wds-children-in-associated-station-stats.patch"
# mac80211_hwsim can retain an AUTHORIZED AP station row after a client has
# reassociated elsewhere.  Filter those inactive rows at the associated-device
# provider boundary; physical builds retain their native liveness policy.
PLATFORM_HWSIM_STA_LIVENESS_PATCH := "${THISDIR}/${BPN}/0028-hwsim-filter-inactive-associated-station-rows.patch"
# Under hwsim an old AP can retain an authorized station row for the full
# fallback interval after a roam.  Query protocol-positive ownership from the
# read-only wmediumd endpoint: a known different owner is stale immediately,
# while known-local and unknown rows preserve legitimate idle-client behavior.
PLATFORM_HWSIM_ASSOC_OWNERSHIP_PATCH := "${THISDIR}/${BPN}/0033-hwsim-filter-stale-peers-by-medium-ownership.patch"

python do_patch_append() {
    import subprocess, os
    s = d.getVar('S')
    git_dir = os.path.dirname(s)
    bb.note("meta-cmf-bananapi-vcpe: applying NULL-map guard to platform_create_vap")
    with open(d.getVar('PLATFORM_CREATE_VAP_NULL_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
    bb.note("meta-cmf-bananapi-vcpe: applying NULL-hapd->mld guard to platform_create_vap")
    with open(d.getVar('PLATFORM_CREATE_VAP_MLD_NULL_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
    bb.note("meta-cmf-bananapi-vcpe: fixing backhaul AP SSID/passphrase defaults")
    with open(d.getVar('PLATFORM_BACKHAUL_SSID_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
    bb.note("meta-cmf-bananapi-vcpe: including WDS child interfaces in station stats")
    with open(d.getVar('PLATFORM_WDS_STA_METRICS_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
    bb.note("meta-cmf-bananapi-vcpe: filtering inactive hwsim station rows")
    with open(d.getVar('PLATFORM_HWSIM_STA_LIVENESS_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
    bb.note("meta-cmf-bananapi-vcpe: filtering stale hwsim peers by medium ownership")
    with open(d.getVar('PLATFORM_HWSIM_ASSOC_OWNERSHIP_PATCH'), 'rb') as f:
        subprocess.run(['patch', '-p1', '-N', '-d', git_dir], stdin=f, check=True)
}
# The *_PATCH variables hold absolute paths, so referencing them from do_patch put
# this layer's checkout location into its basehash and no two trees could share
# sstate for this recipe. The file-checksums below are what makes the patches'
# contents an input; the paths themselves are not one.
do_patch[vardepsexclude] += "PLATFORM_CREATE_VAP_NULL_PATCH \
    PLATFORM_CREATE_VAP_MLD_NULL_PATCH PLATFORM_BACKHAUL_SSID_PATCH \
    PLATFORM_WDS_STA_METRICS_PATCH PLATFORM_HWSIM_STA_LIVENESS_PATCH \
    PLATFORM_HWSIM_ASSOC_OWNERSHIP_PATCH"
do_patch[file-checksums] += "${PLATFORM_CREATE_VAP_NULL_PATCH}:True"
do_patch[file-checksums] += "${PLATFORM_CREATE_VAP_MLD_NULL_PATCH}:True"
do_patch[file-checksums] += "${PLATFORM_BACKHAUL_SSID_PATCH}:True"
do_patch[file-checksums] += "${PLATFORM_WDS_STA_METRICS_PATCH}:True"
do_patch[file-checksums] += "${PLATFORM_HWSIM_STA_LIVENESS_PATCH}:True"
do_patch[file-checksums] += "${PLATFORM_HWSIM_ASSOC_OWNERSHIP_PATCH}:True"

# InterfaceMap_em.json (BananaPi R4's EasyMesh interface map) groups every radio's
# primary VAP (wifi0/wifi1/wifi2 -> private_ssid_*) under "MldName": "mld0", a real
# hardware MLO (802.11be multi-link) grouping. mac80211_hwsim implements no MLO at
# all -- the mld0 interface never actually comes up ("Failed to get MAC address for
# interface mld0", ENODEV) -- yet wifi_hal still routes the primary VAP's beacon-start
# through an MLO-flavored nl80211 call because of this static mapping, which hwsim
# rejects outright: "Failed to set beacon parameter for interface: wifi0 error: -95
# (Operation not supported)". Every other (non-primary) VAP on the same radio then
# fails too, cascading from the radio being left in a broken state. Confirmed this is
# unrelated to 802.11ax/be capability (see ccsp-one-wifi patch 0004): the failure
# persists even with he_enabled=0, plain HT20 -- it's specifically the MLD grouping.
#
# Strip "MldName": "mld0" lines from the WORKDIR copy before
# meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/hal/rdk-wifi-hal.bbappend's
# do_install_append (higher layer priority, runs after ours within the same
# accumulated do_install task) installs it as /usr/ccsp/wifi/InterfaceMap.json. Only
# ever removes whole "\"MldName\": \"mld0\"," lines (own line, comma-terminated),
# which keeps the JSON valid without needing a real JSON parser in a shell function.
do_install_prepend() {
    for fn in InterfaceMap.json InterfaceMap_em.json; do
        f="${WORKDIR}/$fn"
        [ -f "$f" ] || continue
        grep -q '"MldName"' "$f" || continue
        sed -i '/"MldName":[[:space:]]*"mld0",/d' "$f"
        bbnote "meta-cmf-bananapi-vcpe: stripped MldName:mld0 grouping from $fn (mac80211_hwsim has no MLO support)"
    done
}

# Source-level fix for the OneWifi crash that made the EasyMesh leaf lose its fronthaul
# VAP configuration the moment WSC M2 was applied. nl80211_disconnect_event() forwards
# every NL80211_CMD_DISCONNECT into the supplicant even for interfaces that never had a
# session, whose embedded wpa_s therefore has NULL wpa_sm/drv_priv. Two distinct SIGSEGVs
# were traced to this one call site (the second only reachable once the first was
# guarded), which is why this fixes the call site rather than the callees -- notably
# wifi_drv_set_operstate() dereferences its priv argument before any check it could
# contain would run. Uses this file's own existing "wpa_sm != NULL" marker for whether a
# session exists. Not hwsim-specific, so ungated. See patch header for both minidump
# stacks and the faulting instructions.
SRC_URI += "file://0012-dont-notify-supplicant-of-disconnect-when-uninitialized.patch"

# THE reason the EasyMesh leaf had no data path: nl80211_create_bridge() decides to use
# Open vSwitch based on /sys/module/openvswitch existing -- a host-global kernel module,
# which inside an LXD container is not even this container's property -- and then, when
# the OVS calls fail because no ovsdb-server is running here, falls through to its
# "ovs bridge mapping is created" log and returns success without enslaving anything.
# wifi_hal reported "Sta wifi1.3 interface added successfully to bridge:brlan0" while
# brlan0 contained only eth1_virt_end. Also require ovs-vsctl's default db socket, and
# return an error instead of success when ovs_add_br() fails. See patch header.
SRC_URI += "file://0013-dont-take-ovs-path-when-ovs-userspace-is-absent.patch"

# Same bug as 0011 (dormant bridge port never forwards), on the AP side, and only
# reachable once 0013 made enslavement actually happen. Every AP VAP sat in the bridge as
# a disabled port, so EAPOL coming back from a station was dropped on ingress and no
# 4-Way Handshake could ever complete -- fronthaul clients and the EasyMesh backhaul STA
# failed identically with reason 15. Reproduced with a plain wpa_supplicant client on a
# separate hwsim radio to confirm it is not mesh-specific. See patch header.
SRC_URI += "file://0014-set-bridge-port-operstate-up-on-enslave.patch"

# Last blocker for the EasyMesh mesh forming without manual intervention: the AP_VLAN
# netdev for a 4-addr/WDS station (wifi1.1.sta1) is only enslaved to the bridge in the
# branch of wifi_drv_set_wds_sta() that creates it. If it already exists -- which it does
# whenever the AP side restarted without running the teardown path, and always in this
# container setup because the hwsim phy outlives the container -- it is re-enabled but
# never re-bridged, so the associated leaf has no data path and AP-Autoconfiguration times
# out. Enslaving it by hand made the leaf receive WSC M2 immediately. See patch header.
SRC_URI += "file://0015-re-enslave-existing-wds-sta-interface-to-bridge.patch"

SRC_URI += "file://0017-fix-ap-eapol-rx-when-mlo-configured-but-not-established.patch"

# THE reason a controller could never apply an EasyMesh-provided SSID to its own
# radios: VAP reconfiguration fails outright. Two defects in one code path, which
# only work when fixed together.
#
# restart_interface() zeroes interface->beacon_set and calls start_bss() without
# ever issuing NL80211_CMD_STOP_AP. beacon_set is what selects START_AP over
# SET_BEACON, so the HAL asks mac80211 to START an AP that is already running and
# gets -114 EALREADY. Adding the stop is not enough on its own, because the stop
# is itself rejected with -34 ERANGE: wifi_hal_get_mld_link_id() returns the data
# model's unset marker (255, as seen in "MLD_Link_ID": 255) while the caller's
# not-applicable test only knows about -1, so an invalid NL80211_ATTR_MLO_LINK_ID
# of 255 is emitted and nl80211 range-checks it to 0..14 and rejects the whole
# message. Same underlying condition as 0017 -- MLD configured but never
# established -- in a different code path.
#
# With both fixed the controller's radios finally take private_ssid, giving a
# shared fronthaul ESS across both nodes and both bands. See patch header.
SRC_URI += "file://0018-fix-vap-reconfiguration-stop-ap-and-clamp-mlo-link-id.patch"

# mac80211_hwsim VAPs are configured in two stages: OneWifi first creates the
# AP and then applies the EasyMesh-provisioned BSS.  The latter performs a
# STOP_AP/START_AP cycle.  Release the old management-frame and EAPOL receive
# paths before that restart; start_bss() then creates one fresh working set.
# Doing a second refresh after start_bss() collides with its live registration
# and leaves a beaconing AP unable to authenticate clients.  The independent
# spurious-frame subscription remains untouched.  No host-side synchronization
# service or post-start OneWifi restart is required.
SRC_URI += "file://0029-hwsim-refresh-frame-registrations-after-ap-restart.patch"

# Radio/WIPHY reconfiguration has a separate AP stop/start path which bypasses
# restart_interface().  Refresh the hwsim management and EAPOL receive sockets
# there as well; otherwise a radio update can leave a BSS beaconing while Open
# System Authentication requests never reach embedded hostapd.
SRC_URI += "file://0031-hwsim-refresh-frame-registrations-during-wiphy-reconfigure.patch"

# Releasing the stale sockets must also clear the HAL's vap_configured guard.
# Otherwise start_bss() calls set_operstate(1), which returns early without
# rebuilding either receive path.  Cover both AP restart implementations.
SRC_URI += "file://0032-hwsim-rearm-operstate-after-frame-refresh.patch"

# wifi_hal_send_mgmt_frame() used a broadcast address as the BSSID of every
# unicast management action frame.  cfg80211 rejects the resulting AP frame
# with -EINVAL, so a steering request can reach the correct source VAP and
# still put no BTM Request on air.
SRC_URI += "file://0019-wifi_hal_send_mgmt_frame-use-the-interface-BSSID.patch"

# MLO can be configured in the data model without an established link under
# hwsim.  The action-frame path guessed link_id 0 in that state and bypassed
# the existing validated accessor, causing another NL80211 -EINVAL.
SRC_URI += "file://0020-wifi_hal_send_mgmt_frame-use-validated-MLO-link-id.patch"

# Every kernel DEL_STATION notification was reflected back into hostapd as
# EVENT_DISASSOC -- including removals hostapd itself had just ordered.  Its
# clean-slate removal of a stale kernel entry during a returning client's
# authentication then echoed back ~10 ms later and destroyed the fresh
# session, so steering a client back to a previous AP always failed on the
# first attempt (deauth reason 6 on the reassoc).  Upstream gates this
# synthesis on device_ap_sme; this HAL is always userspace-SME.
SRC_URI += "file://0021-dont-reflect-kernel-del-station-back-as-a-disassociation.patch"

SRC_URI += "file://0022-single-phy-let-START_AP-set-each-radio-channel.patch"

# Create the 4-address WDS STA netdev when the backhaul station AUTHORIZES, not at
# association -- companion to rdk-wifi-libhostap 0003/0004 (which defer the hostapd side so
# pre-auth EAPOL M4 is not diverted to the WDS netdev -> reason 15). Driven from the HAL's
# SET_STATION(authorized) path because a leftover WDS netdev suppresses UNEXPECTED_4ADDR.
SRC_URI += "file://0023-create-wds-sta-on-authorization-not-association.patch"

# An associated-device callback is an authoritative edge for OneWifi and
# EasyMesh. Emit it only when hostapd actually enables AUTHORIZED, after the
# kernel accepts that transition; later flag maintenance on a retained hwsim
# station must not manufacture another association.
SRC_URI += "file://0027-notify-association-only-on-authorization-edge.patch"

# The standard non-associated STA query reaches wifi_getNASta(), but the
# generic HAL has no provider.  For HWSIM_RADIO only, read frequency-qualified
# SNR from wmediumd's separately mounted read-only metrics endpoint and expose
# it as candidate-link RCPI.  Physical targets retain their native provider.
SRC_URI += "file://0024-hwsim-read-candidate-rcpi-from-wmediumd.patch"

# NL80211_STA_INFO_CHAIN_SIGNAL is optional.  Fall back to the standard
# aggregate signal attribute so EasyMesh associated-STA and backhaul metrics
# do not become invalid RCPI 255 on drivers that omit per-chain samples.
SRC_URI += "file://0025-read-standard-station-signal-when-chain-signal-is-absent.patch"
