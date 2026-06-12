# libtr181's setXOpsReverseSshTrigger calls /lib/rdk/startTunnel.sh
# but sysint-broadband installs it to /rdklogger/. The RPi image-exclude
# list removes it entirely. Symlink it to where libtr181 expects it.
# Same for exec_curl_mtls.sh (used by uploadDumps.sh).

do_install_append() {
    install -d ${D}${base_libdir}/rdk
    for script in startTunnel.sh startStunnel.sh exec_curl_mtls.sh; do
        if [ -f ${D}/rdklogger/$script ] && [ ! -e ${D}${base_libdir}/rdk/$script ]; then
            ln -sf /rdklogger/$script ${D}${base_libdir}/rdk/$script
        fi
    done
}

FILES_${PN} += "${base_libdir}/rdk/startTunnel.sh"
FILES_${PN} += "${base_libdir}/rdk/startStunnel.sh"
FILES_${PN} += "${base_libdir}/rdk/exec_curl_mtls.sh"
