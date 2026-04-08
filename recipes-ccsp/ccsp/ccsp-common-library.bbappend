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
