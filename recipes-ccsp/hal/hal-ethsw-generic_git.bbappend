FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://ccsp_hal_ethsw.c"

CFLAGS_append = " -DFEATURE_RDKB_WAN_MANAGER"

do_compile_prepend() {
    if [ -f ${WORKDIR}/ccsp_hal_ethsw.c ] && [ -f ${S}/ccsp_hal_ethsw.c ]; then
        install -m 0644 ${WORKDIR}/ccsp_hal_ethsw.c ${S}/ccsp_hal_ethsw.c
        echo "vCPE: overlaid ccsp_hal_ethsw.c (gerrit-patched arm source) onto ${S}/"
    fi
}
