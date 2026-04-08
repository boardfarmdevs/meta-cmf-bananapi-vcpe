do_install:append() {
    sed -i 's/,CAP_SYS_RAWIO//g; s/CAP_SYS_RAWIO,//g; s/CAP_SYS_RAWIO//g' \
        ${D}${sysconfdir}/security/caps/process-capabilities.json
    sed -i 's/,CAP_SYS_MODULE//g; s/CAP_SYS_MODULE,//g; s/CAP_SYS_MODULE//g' \
        ${D}${sysconfdir}/security/caps/process-capabilities.json
}
