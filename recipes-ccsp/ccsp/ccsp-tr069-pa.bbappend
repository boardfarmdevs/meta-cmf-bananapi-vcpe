FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://0001-fixup-prompt-system-ready-event-retrieval.patch"
SRC_URI += "file://0002-sercomm-fx-tr069-ipv6.patch"
SRC_URI += "file://0003-fix-erouter0-ipv6-first-ipv4-fallback.patch"

CFLAGS_remove = " -U_ANSC_IPV6_COMPATIBLE_"
CFLAGS_append = " -D_SUPPORT_HTTP -D_ANSC_IPV6_COMPATIBLE_ -DSERCOMM_FIX_ANSC_IPV6_COMPATIBLE_"
