FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# -Werror=sign-compare on the BananaPi-only dml cache loop (e28776520,
# 2026-07-14): loop counter was declared int against an unsigned int
# num_vaps comparison.
#
# Applied via do_patch_append rather than SRC_URI because
# meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/ccsp/ccsp-one-wifi.bbappend
# (higher layer priority, applied after this one) does a hard
# "SRC_URI = ..." reassignment that would wipe out anything this layer
# appends to SRC_URI. do_patch itself is a python task (patch.bbclass),
# so the append must be python, not shell.
VAP_SVC_SIGNCOMPARE_PATCH := "${THISDIR}/${BPN}/0001-vap_svc-fix-sign-compare-in-BananaPi-dml-cache-loop.patch"
WIFI_EM_HDRLEN_PATCH := "${THISDIR}/${BPN}/0002-wifi_em-guard-IEEE80211_HDRLEN-against-hostap-redef.patch"
WIFI_DB_ONEWIFI_DB_SUPPORT_OFF_PATCH := "${THISDIR}/${BPN}/0003-wifi_db-fix-ONEWIFI_DB_SUPPORT-off-branch-build.patch"
WIFI_DB_HWSIM_STANDARDS_PATCH := "${THISDIR}/${BPN}/0004-wifi_db-disable-11ax-11be-defaults-under-hwsim.patch"
WIFI_DB_HWSIM_SAE_PATCH := "${THISDIR}/${BPN}/0005-wifi_db-disable-sae-wpa3-defaults-under-hwsim.patch"
WIFI_DB_HWSIM_NO_6GHZ_PATCH := "${THISDIR}/${BPN}/0006-wifi_db-disable-6ghz-only-under-hwsim.patch"
WIFI_DB_HWSIM_SAE_STA_PATCH := "${THISDIR}/${BPN}/0007-wifi_db-disable-sae-wpa3-sta-defaults-under-hwsim.patch"
WIFI_DB_HWSIM_20MHZ_PATCH := "${THISDIR}/${BPN}/0008-wifi_db-clamp-channelwidth-20mhz-under-hwsim.patch"
WIFI_ASSOC_RETURN_DELTA_PATCH := "${THISDIR}/${BPN}/0010-assoc-publish-returning-client-delta.patch"
WIFI_ASSOC_LIVE_SNAPSHOT_PATCH := "${THISDIR}/${BPN}/0011-assoc-mark-monitor-missing-client-inactive.patch"
WIFI_EM_DUPLICATE_AL_MAC_PATCH := "${THISDIR}/${BPN}/0012-webconfig-prefer-sta-for-duplicate-al-mac.patch"
WIFI_EM_AP_METRICS_RADIO_INDEX_PATCH := "${THISDIR}/${BPN}/0013-ap-metrics-index-radio-config-by-radio-index.patch"
WIFI_EM_CLIENT_UPTIME_PATCH := "${THISDIR}/${BPN}/0014-easymesh-copy-client-association-uptime.patch"
WIFI_NASTA_RESPONSE_NAME_PATCH := "${THISDIR}/${BPN}/0015-nasta-label-response-subdoc.patch"
WIFI_STA_BSSID_SET_PATCH := "${THISDIR}/${BPN}/0016-rbus-apply-mesh-sta-bssid.patch"
WIFI_STA_STATUS_PUBLISH_PATCH := "${THISDIR}/${BPN}/0017-publish-mesh-sta-on-connection-change.patch"
WIFI_STA_PARENT_CACHE_PATCH := "${THISDIR}/${BPN}/0018-cache-confirmed-mesh-sta-parent.patch"
WIFI_EM_EVENT_OWNERSHIP_PATCH := "${THISDIR}/${BPN}/0019-easymesh-release-encoded-event-data.patch"
WIFI_EM_ASSOC_RECONCILE_PATCH := "${THISDIR}/${BPN}/0020-hwsim-reconcile-live-associated-client-snapshots.patch"
WIFI_ASSOC_ACTIVE_PROVIDER_PATCH := "${THISDIR}/${BPN}/0021-assoc-provider-omit-inactive-cache-rows.patch"
WIFI_EM_AP_METRICS_LIVE_COUNT_PATCH := "${THISDIR}/${BPN}/0022-ap-metrics-count-live-provider-stations.patch"
python do_patch_append() {
    import os
    import subprocess
    s = d.getVar('S')
    def apply_layer_patch(stream):
        patch_data = stream.read()
        # --force also prevents GNU patch from silently ignoring an explicit
        # --reverse dry-run after it recognizes an unreversed patch.
        base = ['patch', '-p1', '--batch', '--force', '-d', s]
        # Hand-applied patches are outside BitBake's normal patch tracking.
        # A task signature change can therefore rerun do_patch against a
        # surviving, already-patched source tree.  Treat a clean full reverse
        # dry-run as "already applied".  Test reverse first: an insertion-only
        # hunk can otherwise remain a valid forward match inside the text it
        # inserted and be duplicated on every task rerun.
        reverse = subprocess.run(base + ['--dry-run', '--reverse'],
                                 input=patch_data, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        if reverse.returncode == 0:
            bb.note('meta-cmf-bananapi-vcpe: patch already applied; skipping')
            return

        forward = subprocess.run(base + ['--dry-run', '--forward'],
                                 input=patch_data, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        if forward.returncode == 0:
            subprocess.run(base + ['--forward'], input=patch_data, check=True)
            return

        bb.fatal('meta-cmf-bananapi-vcpe: patch is neither cleanly applicable '
                 'nor already applied:\n%s' %
                 forward.stdout.decode('utf-8', errors='replace'))

    bb.note("meta-cmf-bananapi-vcpe: applying sign-compare fix to vap_svc.c")
    with open(d.getVar('VAP_SVC_SIGNCOMPARE_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # Only reachable at all once rdk-wifi-libhostap is a DEPENDS (EasyMesh/em_extender
    # builds), so this is a no-op patch attempt-wise for the non-EasyMesh (broadband)
    # build -- but harmless either way since the guard is additive (#ifndef) and the
    # macro is otherwise untouched.
    bb.note("meta-cmf-bananapi-vcpe: applying IEEE80211_HDRLEN redefinition guard to wifi_em.h")
    with open(d.getVar('WIFI_EM_HDRLEN_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # wifi_db.c's ONEWIFI_DB_SUPPORT-off branch (only compiled under EasyMesh) has
    # never been built before this pass -- see patch header for the two latent bugs.
    bb.note("meta-cmf-bananapi-vcpe: fixing wifi_db.c's ONEWIFI_DB_SUPPORT-off branch")
    with open(d.getVar('WIFI_DB_ONEWIFI_DB_SUPPORT_OFF_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # init_radio_config_default() defaults to 802.11be/ax + 40MHz for the 2.4GHz radio
    # whenever _PLATFORM_BANANAPI_R4_ is defined -- true for this container too, but
    # mac80211_hwsim can't beacon HE/EHT (confirmed via wifiHal.txt: kernel error -95
    # Operation not supported on the very first VAP's beacon-start). Gated behind a new
    # HWSIM_RADIO macro (see CFLAGS_append below) so real BananaPi R4 hardware is unaffected.
    bb.note("meta-cmf-bananapi-vcpe: disabling 802.11ax/be radio defaults under hwsim")
    with open(d.getVar('WIFI_DB_HWSIM_STANDARDS_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # private_ssid_*'s default security.mode defaults to WPA3/SAE under
    # _PLATFORM_BANANAPI_R4_. Root-caused via a raw netlink capture (strace -x on the
    # exact NL80211_CMD_START_AP sendmsg, decoded byte-for-byte against nl80211.h):
    # the request carries NL80211_ATTR_SAE_PWE, which the kernel flatly rejects with
    # -EOPNOTSUPP for mac80211_hwsim -- this, not the 802.11ax/be defaults above, was
    # the actual cause of "Failed to set beacon parameter ... error: -95". See patch
    # header for the full trace.
    bb.note("meta-cmf-bananapi-vcpe: disabling WPA3/SAE security defaults under hwsim")
    with open(d.getVar('WIFI_DB_HWSIM_SAE_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # 6GHz cannot work under hwsim at all: the phy advertises the band but exposes no
    # HE capability, and 6GHz mandates HE. 2.4GHz and 5GHz both work, and both are
    # needed -- the EasyMesh controller maps the fronthaul haul onto its 2.4GHz radio,
    # so disabling that radio left the controller on the image default SSID while the
    # extender served private_ssid, and the two nodes never shared an ESS. Running both
    # bands at once requires the hwsim pool to be loaded with channels>=2 (meta-lxd
    # does this); with channels=1 the second band fails with -16 (EBUSY) on "Set freq".
    bb.note("meta-cmf-bananapi-vcpe: disabling 6GHz under hwsim (no HE capability)")
    with open(d.getVar('WIFI_DB_HWSIM_NO_6GHZ_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # 0005 disabled the WPA3/SAE defaults for the AP-side VAPs but missed the STA-side
    # equivalent in the same file, leaving the backhaul STA on WPA3-SAE+MFP-required
    # while its peer AP had been moved to WPA2-PSK. That mismatch makes
    # wpa_supplicant_set_suites() fail inside sme_send_authentication(), which returns
    # void and bails silently -- so the driver's authenticate op was never reached and
    # not a single auth frame ever hit the air. See patch header for the full trace.
    bb.note("meta-cmf-bananapi-vcpe: disabling WPA3/SAE *STA* security defaults under hwsim")
    with open(d.getVar('WIFI_DB_HWSIM_SAE_STA_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # FEATURE_SINGLE_PHY: the 5GHz(80MHz)/6GHz(160MHz) radio-width defaults make the
    # 2nd/3rd concurrent AP channel context on the one hwsim phy fail START_AP with
    # -EINVAL on Linux 7.0 (20MHz concurrent works, 80/160 does not -- host-hwsim proven).
    # Clamp to 20MHz so tri-band comes up. Pairs with rdk-wifi-hal 0022.
    bb.note("meta-cmf-bananapi-vcpe: clamping channelWidth to 20MHz under hwsim (single-phy tri-band)")
    with open(d.getVar('WIFI_DB_HWSIM_20MHZ_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # A client returning to an AP can find a stale OneWifi map entry because
    # inter-AP reassociation does not guarantee a disassociation frame at the old
    # AP. Publish a refreshed association delta for an existing entry so EasyMesh
    # learns the new owner instead of leaving the controller/WebUI stale.
    bb.note("meta-cmf-bananapi-vcpe: publishing association delta for returning clients")
    with open(d.getVar('WIFI_ASSOC_RETURN_DELTA_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # The persistent association map can retain a station after a silent roam.
    # Make the failed live-monitor lookup explicit so full snapshots can exclude
    # retained history without deleting it.
    bb.note("meta-cmf-bananapi-vcpe: marking monitor-missing association history inactive")
    with open(d.getVar('WIFI_ASSOC_LIVE_SNAPSHOT_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # Linux bridges inherit a port MAC, so the extender AL MAC can appear on
    # both brlan0 and its wireless backhaul STA.  Make the Init_dml readiness
    # check select the known STA instead of depending on getifaddrs() order.
    bb.note("meta-cmf-bananapi-vcpe: resolving duplicate EasyMesh AL MAC to the backhaul STA")
    with open(d.getVar('WIFI_EM_DUPLICATE_AL_MAC_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # AP Metrics requests can enumerate RUIDs in a different order from the
    # platform radio array.  Keep the decoded radio config indexed by physical
    # radio_index, as required by the encoder, so per-VAP/per-STA metrics are
    # not silently omitted.
    bb.note("meta-cmf-bananapi-vcpe: fixing AP-metrics radio-config indexing")
    with open(d.getVar('WIFI_EM_AP_METRICS_RADIO_INDEX_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # OneWifi already measures time associated; preserve it when translating
    # the association snapshot into the EasyMesh station data model.
    bb.note("meta-cmf-bananapi-vcpe: forwarding client association uptime to EasyMesh")
    with open(d.getVar('WIFI_EM_CLIENT_UPTIME_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # The NaSta encoder publishes a response on Device.WiFi.EM.NaStaResponse,
    # but labelled the document as the original request.  Consumers must be
    # able to distinguish the asynchronous result from the method input.
    bb.note("meta-cmf-bananapi-vcpe: labelling NaSta event payload as a response")
    with open(d.getVar('WIFI_NASTA_RESPONSE_NAME_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # Device.WiFi.STA.{i}.Bssid was registered writable but its setter ignored
    # the value.  Deliver validated writes to the existing mesh-extender BSSID
    # change state machine so a controller can select a wireless backhaul parent.
    if d.getVar('MACHINE') == 'qemux86bpiap':
        bb.note("meta-cmf-bananapi-vcpe: applying mesh-STA RBUS BSSID selection")
        with open(d.getVar('WIFI_STA_BSSID_SET_PATCH'), 'rb') as f:
            apply_layer_patch(f)
        # A confirmed mesh-STA connection updates the OneWifi cache.  Publish
        # that change as mesh_sta (not the generic dml document ignored by the
        # EasyMesh agent) so runtime reparenting updates the controller model.
        bb.note("meta-cmf-bananapi-vcpe: publishing mesh-STA connection changes")
        with open(d.getVar('WIFI_STA_STATUS_PUBLISH_PATCH'), 'rb') as f:
            apply_layer_patch(f)
        # The mesh-ext state machine previously refreshed its cached BSSID
        # only during initial connection establishment.  A live reparent is a
        # connected-to-connected transition, so cache every confirmed parent
        # before publishing the mesh_sta document above.
        bb.note("meta-cmf-bananapi-vcpe: caching confirmed live mesh-STA parents")
        with open(d.getVar('WIFI_STA_PARENT_CACHE_PATCH'), 'rb') as f:
            apply_layer_patch(f)
    # webconfig_encode() returns a separately allocated encoded buffer.  The
    # periodic EasyMesh metrics publishers released only their wrapper, leaking
    # one report every interval.  Release encoded data through the webconfig
    # ownership API, including error and less-frequent report paths.
    bb.note("meta-cmf-bananapi-vcpe: releasing encoded EasyMesh event buffers")
    with open(d.getVar('WIFI_EM_EVENT_OWNERSHIP_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # The HAL's diagnostic snapshot filters hwsim station objects retained on
    # an old AP after a roam.  Reconcile that live snapshot with OneWifi's
    # event-backed association cache, including an authoritative empty result,
    # and publish the resulting withdrawal to EasyMesh.
    bb.note("meta-cmf-bananapi-vcpe: reconciling hwsim live association snapshots")
    with open(d.getVar('WIFI_EM_ASSOC_RECONCILE_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # The cached monitor-provider path exported inactive historical rows even
    # though the direct associated-device collector filtered them.  Keep the
    # provider contract live-only so an intra-agent band roam withdraws its old
    # BSSID from EasyMesh.
    bb.note("meta-cmf-bananapi-vcpe: filtering inactive cached association rows")
    with open(d.getVar('WIFI_ASSOC_ACTIVE_PROVIDER_PATCH'), 'rb') as f:
        apply_layer_patch(f)
    # AP metrics serialized the live monitor map but bounded it with the
    # event-backed association-map count.  Count the authoritative live source
    # so stations connected before OneWifi starts remain observable.
    bb.note("meta-cmf-bananapi-vcpe: counting AP metrics from the live provider snapshot")
    with open(d.getVar('WIFI_EM_AP_METRICS_LIVE_COUNT_PATCH'), 'rb') as f:
        apply_layer_patch(f)

    # GNU patch -N can return success after skipping later hunks when an older
    # revision of this hand-applied patch left the WORKDIR only partly patched.
    # Never turn that mixed source tree into an apparently successful image.
    wifi_em = os.path.join(s, 'source/apps/em/wifi_em.c')
    with open(wifi_em, 'r', encoding='utf-8') as f:
        wifi_em_source = f.read()
    if (wifi_em_source.count('webconfig_data_free(data);') < 7 or
            wifi_em_source.count('webconfig_data_free(wb_data);') < 3):
        bb.fatal('meta-cmf-bananapi-vcpe: EasyMesh encoded-event ownership patch is incomplete; clean ccsp-one-wifi and retry')
    assoc_stats = os.path.join(s, 'source/stats/wifi_stats_assoc_client.c')
    with open(assoc_stats, 'r', encoding='utf-8') as f:
        assoc_stats_source = f.read()
    provider_start = assoc_stats_source.find(
        'int copy_assoc_client_stats_from_cache(')
    if provider_start < 0:
        bb.fatal('meta-cmf-bananapi-vcpe: associated-client cached provider is missing')
    provider_source = assoc_stats_source[provider_start:]
    if ('*stat_array_size = count;' not in provider_source or
            '*stat_array_size = sta_count;' in provider_source):
        bb.fatal('meta-cmf-bananapi-vcpe: inactive associated-client provider patch is incomplete; clean ccsp-one-wifi and retry')
    if ('vap_report->sta_cnt = hash_map_count(' not in wifi_em_source or
            '.ap_data[cache_vap_index].client_stats_map);' not in wifi_em_source):
        bb.fatal('meta-cmf-bananapi-vcpe: live AP-metrics station-count patch is incomplete; clean ccsp-one-wifi and retry')
}

# The *_PATCH variables above hold absolute paths, and being referenced from
# do_patch they go into its basehash verbatim. That is wrong in both directions:
# the layer's checkout location is not a build input (so no two trees share
# sstate for this recipe), while the patch files' *contents* are not an input at
# all -- unlike SRC_URI patches these are applied by hand, so editing one used to
# leave do_patch's hash untouched and the stale result was silently reused.
# Drop the paths from the hash and register the files' checksums instead.
do_patch[vardepsexclude] += "VAP_SVC_SIGNCOMPARE_PATCH WIFI_EM_HDRLEN_PATCH \
    WIFI_DB_ONEWIFI_DB_SUPPORT_OFF_PATCH WIFI_DB_HWSIM_STANDARDS_PATCH \
    WIFI_DB_HWSIM_SAE_PATCH WIFI_DB_HWSIM_NO_6GHZ_PATCH \
    WIFI_DB_HWSIM_SAE_STA_PATCH WIFI_DB_HWSIM_20MHZ_PATCH \
    WIFI_ASSOC_RETURN_DELTA_PATCH WIFI_ASSOC_LIVE_SNAPSHOT_PATCH \
    WIFI_EM_DUPLICATE_AL_MAC_PATCH WIFI_EM_AP_METRICS_RADIO_INDEX_PATCH \
    WIFI_EM_CLIENT_UPTIME_PATCH WIFI_NASTA_RESPONSE_NAME_PATCH \
    WIFI_STA_BSSID_SET_PATCH WIFI_STA_STATUS_PUBLISH_PATCH \
    WIFI_STA_PARENT_CACHE_PATCH WIFI_EM_EVENT_OWNERSHIP_PATCH \
    WIFI_EM_ASSOC_RECONCILE_PATCH WIFI_ASSOC_ACTIVE_PROVIDER_PATCH \
    WIFI_EM_AP_METRICS_LIVE_COUNT_PATCH"
do_patch[file-checksums] += "${VAP_SVC_SIGNCOMPARE_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_HDRLEN_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_ONEWIFI_DB_SUPPORT_OFF_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_HWSIM_STANDARDS_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_HWSIM_SAE_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_HWSIM_NO_6GHZ_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_HWSIM_SAE_STA_PATCH}:True"
do_patch[file-checksums] += "${WIFI_DB_HWSIM_20MHZ_PATCH}:True"
do_patch[file-checksums] += "${WIFI_ASSOC_RETURN_DELTA_PATCH}:True"
do_patch[file-checksums] += "${WIFI_ASSOC_LIVE_SNAPSHOT_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_DUPLICATE_AL_MAC_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_AP_METRICS_RADIO_INDEX_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_CLIENT_UPTIME_PATCH}:True"
do_patch[file-checksums] += "${WIFI_NASTA_RESPONSE_NAME_PATCH}:True"
do_patch[file-checksums] += "${WIFI_STA_BSSID_SET_PATCH}:True"
do_patch[file-checksums] += "${WIFI_STA_STATUS_PUBLISH_PATCH}:True"
do_patch[file-checksums] += "${WIFI_STA_PARENT_CACHE_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_EVENT_OWNERSHIP_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_ASSOC_RECONCILE_PATCH}:True"
do_patch[file-checksums] += "${WIFI_ASSOC_ACTIVE_PROVIDER_PATCH}:True"
do_patch[file-checksums] += "${WIFI_EM_AP_METRICS_LIVE_COUNT_PATCH}:True"

# See patch 0004 header: mac80211_hwsim can't beacon HE(802.11ax)/EHT(802.11be), so
# init_radio_config_default()'s BananaPi-R4 HE/EHT defaults are gated off under this.
CFLAGS_append = " -DHWSIM_RADIO"

# 6GHz capability gate (review P1 #2). Patch 0006 disables the 6GHz radio because the
# 6.8-lab regdomain marks 6GHz no-IR. On a 7.0 host (regtest=5/custom_03) 6GHz is
# IR-capable and beacons -- proven in doc/easymesh/Linux-7.0-hwsim-6GHz-VLP-AP-results.md.
# Set HWSIM_6GHZ_CAPABLE = "1" (in the recipe or a local.conf/distro override) to keep
# wifi2 enabled on such a host; default off preserves the 6.8 behaviour. NOTE: 6GHz also
# mandates SAE-H2E + PMF, which patches 0005/0007 currently force to WPA2 -- enabling
# 6GHz for a *standards-correct* VAP still needs the band-aware security work (P1 #3).
HWSIM_6GHZ_CAPABLE ??= "0"
CFLAGS_append = " ${@' -DHWSIM_6GHZ_CAPABLE' if d.getVar('HWSIM_6GHZ_CAPABLE') == '1' else ''}"

# -Werror=unused-variable on ~20 wifi_db_apis.c TR-181-parameter-name statics
# (WmmEnable, BeaconInterval, RTSThreshold, ...): EasyMesh's own bbappend
# (meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/ccsp/ccsp-one-wifi.bbappend)
# removes -DONEWIFI_DB_SUPPORT when DISTRO_FEATURES has EasyMesh, which drops the
# only reference to these particular statics in this translation unit. Scoped to
# EasyMesh so the non-EasyMesh (broadband) build's CFLAGS are untouched.
CFLAGS_append = " ${@bb.utils.contains('DISTRO_FEATURES', 'EasyMesh', ' -Wno-unused-variable ', '', d)}"

# source/apps/em/{wifi_em,wifi_em_utils}.c (the actual EasyMesh app code) has dozens
# of pre-existing sign-compare/pointer-sign/incompatible-pointer-types/uninitialized
# warnings -- clearly never built with -Werror before on any target. Confirmed by the
# same bananapi bbappend (meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/ccsp/
# ccsp-one-wifi.bbappend) already doing exactly this for the real hardware target:
# `CFLAGS_append_aarch64 = " -Wno-error "`. Match that precedent for our i686
# container instead of patching each individual site -- still scoped to EasyMesh, so
# it's a no-op for the plain broadband build (which never compiles source/apps/em/*
# at all).
CFLAGS_append = " ${@bb.utils.contains('DISTRO_FEATURES', 'EasyMesh', ' -Wno-error ', '', d)}"

# onewifi_pre_start_em_{ctrl,ext}.sh (meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/ccsp/
# files/) hardcode "phy0" for `iw phy phy0 interface add wifiN type __ap`. On real hardware
# there's exactly one physical radio so it's always phy0; in an LXD container using
# mac80211_hwsim (moved in via `nictype: physical`), the phy keeps its host-side hwsim index
# (e.g. phy40) instead of being renumbered to 0 -- confirmed on both bpi-r25-7 (controller)
# and this build: `ls /sys/class/ieee80211` never returns "phy0". Rewrite both scripts (only
# one of the two actually ships per build, selected by ccsp-one-wifi.bbappend's em_extender
# SRC_URI conditional, but fixing both keeps a future controller rebuild working too) to
# detect the real phy name instead of hardcoding it. Runs in do_install_prepend so it edits
# the WORKDIR copy before meta-cmf-bananapi/meta-rdk-mtk-bpir4/recipes-ccsp/ccsp/
# ccsp-one-wifi.bbappend's do_install_append (higher layer priority, so its function body
# runs after ours within the same accumulated do_install task) copies it into the image as
# /usr/ccsp/wifi/onewifi_pre_start.sh.
do_install_prepend() {
    for fn in onewifi_pre_start_em_ctrl.sh onewifi_pre_start_em_ext.sh; do
        f="${WORKDIR}/$fn"
        [ -f "$f" ] || continue
        grep -q 'phy=\$(ls /sys/class/ieee80211' "$f" && continue
        sed -i \
            -e '0,/^sleep /s//phy=$(ls \/sys\/class\/ieee80211 | head -n1)\n\nsleep /' \
            -e 's/iw phy phy0 /iw phy $phy /g' \
            "$f"
        bbnote "meta-cmf-bananapi-vcpe: rewrote $fn to detect the real phy instead of hardcoding phy0"

        # /nvram/mac_addresses.txt (read a few lines below, "#Obtain the wifi mac
        # address") is a real-hardware artifact -- generated from factory-programmed
        # EEPROM/OTP data during early boot on real BananaPi R4 silicon, long before
        # this script ever runs. This container has no equivalent generator, so the
        # file is simply missing, every "grep -a wifiN | cut ... | head -n1" below
        # returns empty, and every ifconfig-hw-ether call that follows becomes a
        # silent no-op -- leaving every VAP except the first (which happens to get a
        # real address a different way) with the SAME cloned MAC address
        # (02:00:00:00:0c:00) as every other interface on the phy. Confirmed via
        # `ip link show`: sibling interfaces stuck admin-DOWN, and their beacon-start
        # subsequently fails with "-100 Network is down" (nl80211 station-flush on a
        # netdev that could never actually come up) -- the second, non-EOPNOTSUPP
        # failure mode seen after 0007's ACL fix let the *first* VAP per radio
        # through. Generate a stub file with a unique locally-administered MAC per
        # interface if missing, ordered so each bare "wifiN" line precedes its
        # "wifiN.M" sub-interface lines (the script's own grep -a is an unanchored
        # substring match relying on `head -n1` + this ordering, same as real
        # hardware's generated file must do).
        grep -q 'mac_addresses.txt' "$f" || continue
        python3 - "$f" <<'PYEOF'
import re, sys
path = sys.argv[1]
with open(path) as fh:
    content = fh.read()
snippet = (
    "if [ ! -f /nvram/mac_addresses.txt ]; then\n"
    "    for ifn in wifi0 wifi0.1 wifi0.2 wifi1 wifi1.1 wifi1.2 wifi1.3 wifi2 wifi2.1 wifi2.2; do\n"
    "        set -- $(od -An -N3 -tu1 /dev/urandom)\n"
    "        printf '%s 02:00:00:%02x:%02x:%02x\\n' \"$ifn\" \"$1\" \"$2\" \"$3\" >> /nvram/mac_addresses.txt\n"
    "    done\n"
    "fi\n\n"
)
marker = "#Obtain the wifi mac address\n"
assert content.count(marker) == 1, content.count(marker)
content = content.replace(marker, snippet + marker)

# The upstream extender pre-start updates AL_MAC_ADDR by first extracting the
# old value and using it as an unescaped sed pattern.  A genuinely fresh image
# ships an empty value, so that becomes `sed s//$new_mac/`; BusyBox sed rejects
# it with "no previous regular expression".  OneWifi then asks the HAL to
# resolve an empty/undefined AL MAC and remains in its initialization loop.  A
# warm NVRAM happened to hide the defect because it already contained a MAC.
# Replace the complete JSON member instead.  This is idempotent, accepts both
# an empty and a populated first-boot value, and never treats a MAC as a sed
# regular expression.
old_al_update = (
    "al_mac_addr=`cat /nvram/EasymeshCfg.json | grep AL_MAC_ADDR  | cut -d '\"' -f4`\n"
    "al_mac=`iw dev wifi1.3 info | grep addr | cut -d ' ' -f2`\n"
    "sed -i \"s/$al_mac_addr/$al_mac/g\" /nvram/EasymeshCfg.json\n"
)
new_al_update = (
    "al_mac=$(iw dev wifi1.3 info | awk '/addr/ { print $2; exit }')\n"
    "if [ -n \"$al_mac\" ]; then\n"
    "    sed -i \"s@\\\"AL_MAC_ADDR\\\"[[:space:]]*:[[:space:]]*\\\"[^\\\"]*\\\"@\\\"AL_MAC_ADDR\\\": \\\"$al_mac\\\"@\" /nvram/EasymeshCfg.json\n"
    "fi\n"
)
old_al_count = content.count(old_al_update)
if path.endswith("onewifi_pre_start_em_ext.sh"):
    # Keep this assertion on the one script whose fresh-image failure is being
    # repaired.  The controller script legitimately has no extender AL update.
    assert old_al_count == 1, old_al_count
    content = content.replace(old_al_update, new_al_update)
else:
    assert old_al_count == 0, old_al_count
with open(path, "w") as fh:
    fh.write(content)
PYEOF
        bbnote "meta-cmf-bananapi-vcpe: added persistent VAP MAC generation and the applicable first-boot-safe EasyMesh AL-MAC update to $fn"
    done
}
