SUMMARY = "Breakpad/minidump demonstration tool"
DESCRIPTION = "A small C utility that links libbreakpadwrapper to \
exercise Google Breakpad crash-dump generation."
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

SRC_URI = "file://breakpad-demo.c \
           file://exec_curl_mtls.sh \
           file://lab-crashupload-setup.sh \
           file://lab-crashupload.service"

DEPENDS += "breakpad breakpad-wrapper"

inherit breakpad-wrapper breakpad-logmapper systemd

# Lab crash-upload setup: a boot-time oneshot that points the stock RDK-B crash
# pipeline (uploadDumps.sh) at the per-desk lab SSR and swaps the Xpki mTLS curl
# for plain curl, so a real crash is delivered to the lab SSR by the normal
# systemd coredump-upload.path trigger. Dev/lab images only.
SYSTEMD_SERVICE_${PN} = "lab-crashupload.service"

BREAKPAD_BIN = "breakpad-demo"
BREAKPAD_LOGMAPPER_PROCLIST = "breakpad-demo"
BREAKPAD_LOGMAPPER_LOGLIST = "breakpad-demo.log"

CFLAGS += "-fno-omit-frame-pointer -fno-optimize-sibling-calls"

S = "${WORKDIR}"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} \
        -I${STAGING_INCDIR} \
        -Wl,--no-as-needed \
        -o breakpad-demo breakpad-demo.c \
        -lbreakpadwrapper \
        -Wl,--as-needed
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${WORKDIR}/breakpad-demo ${D}${bindir}/breakpad-demo

    # Lab crash-upload setup files
    install -d ${D}/usr/share/lab-crashupload
    install -m 0644 ${WORKDIR}/exec_curl_mtls.sh ${D}/usr/share/lab-crashupload/exec_curl_mtls.sh
    install -m 0755 ${WORKDIR}/lab-crashupload-setup.sh ${D}/usr/share/lab-crashupload/lab-crashupload-setup.sh
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${WORKDIR}/lab-crashupload.service ${D}${systemd_system_unitdir}/lab-crashupload.service
}

FILES_${PN} = "${bindir}/breakpad-demo \
               /usr/share/lab-crashupload \
               ${systemd_system_unitdir}/lab-crashupload.service"
