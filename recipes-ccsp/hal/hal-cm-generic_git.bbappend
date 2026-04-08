FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://cm_hal.c"

do_compile_prepend() {
    if [ -f ${WORKDIR}/cm_hal.c ] && [ -f ${S}/cm_hal.c ]; then
        install -m 0644 ${WORKDIR}/cm_hal.c ${S}/cm_hal.c
    fi
}
