FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# The EasyMesh translator (source/webconfig/wifi_easymesh_translator.c, built into
# libwifi_webconfig.so by THIS recipe) only reported associated clients from
# OneWifi's association DIFF map. On a FULL associated-clients refresh (empty diff)
# -- which the controller's co-located agent hits routinely -- no Client Association
# Event was emitted, so the controller never learned the client and it never
# appeared in STAList / the CLI clients list / the network topology. Fall back to
# the full associated_devices_map when the diff is empty. See patch header.
# NOTE: use a deferred _append (not +=). meta-rdk-mtk-bpir4's libwebconfig bbappend
# does a hard `SRC_URI = "..."` that is parsed after this layer and would wipe a
# plain += ; _append is applied during finalization, after that assignment.
SRC_URI_append = " file://0001-easymesh-translator-report-clients-from-full-list.patch file://0002-easymesh-translator-coherent-cipher-pmf-from-m2.patch file://0004-easymesh-full-list-seeds-only-unknown-clients.patch file://0005-assoc-full-list-report-only-live-clients.patch file://0006-nasta-label-response-subdoc.patch file://0007-ap-metrics-seed-missed-associated-stations.patch file://0008-easymesh-decode-use-call-local-data.patch file://0009-easymesh-translate-mesh-sta-subdoc.patch file://0010-easymesh-apply-m2-to-unseeded-vaps.patch file://0011-rbus-bound-set-provider-timeout.patch file://0012-ap-metrics-release-decoded-json.patch"
