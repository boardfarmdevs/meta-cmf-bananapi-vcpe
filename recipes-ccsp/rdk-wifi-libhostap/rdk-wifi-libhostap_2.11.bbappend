FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# See the patch header: ccsp-one-wifi's EasyMesh/em_extender build (the only consumer
# that defines IEEE80211_HDRLEN itself, in source/apps/em/wifi_em.h) can include this
# header either before or after wifi_em.h depending on the translation unit, so both
# sides need the #ifndef guard for the collision to be resolved order-independently.
# Purely additive (a no-op unless something else already defined the macro), so inert
# for every other rdk-wifi-libhostap consumer (hostapd/wpa_supplicant in both the
# EasyMesh and plain broadband builds).
SRC_URI += "file://0001-ieee802_11_defs-guard-IEEE80211_HDRLEN-against-em-redef.patch"

# THE reason the EasyMesh leaf never brought up its fronthaul VAPs, despite the 1905
# transport, AP-Autoconfiguration Search/Response and WSC M1/M2 all completing cleanly:
# OneWifi SIGSEGV'd the instant it applied the M2 config, systemd restarted it, and the
# fresh process came up without that configuration -- which autoconfiguration never
# re-sends. Root-caused from the breakpad minidump the crash left in /minidumps: a NULL
# `struct wpa_sm *` reaching wpa_sm_notify_disassoc(), which (unlike its sibling
# wpa_sm_notify_assoc and every other wpa_sm_* entry point in that file) has no NULL
# guard. Not hwsim-specific and not a wifi_hal bug -- a genuinely missing check on a
# path that legitimately sees NULL -- so applied unconditionally. See patch header for
# the full stack, faulting instruction and register state.
SRC_URI += "file://0002-wpa_sm_notify_disassoc-guard-against-NULL-sm.patch"

# Defer 4-address WDS-STA setup until the station is authorized (see patch): creating the
# WDS netdev at association -- before the 4-way -- diverts the STA's pre-auth EAPOL (M4) to
# the WDS netdev on mac80211_hwsim, so the backhaul 4-way times out (reason 15).
SRC_URI += "file://0003-defer-wds-sta-setup-until-station-authorized.patch"

# Companion to 0003: the WDS-STA netdev is also created from ieee802_11_rx_from_unknown()
# on the first 4-addr frame (M2) before the 4-way -- defer that to authorization too.
SRC_URI += "file://0004-defer-wds-on-rx-from-unknown-until-authorized.patch"
