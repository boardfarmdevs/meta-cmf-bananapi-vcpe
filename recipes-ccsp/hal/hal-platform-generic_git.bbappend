FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://platform_hal.c"

do_compile_prepend() {
    if [ -f ${WORKDIR}/platform_hal.c ] && [ -f ${S}/platform_hal.c ]; then
        install -m 0644 ${WORKDIR}/platform_hal.c ${S}/platform_hal.c
        echo "vCPE: overlaid platform_hal.c (gerrit-patched arm source) onto ${S}/"
    fi
}
