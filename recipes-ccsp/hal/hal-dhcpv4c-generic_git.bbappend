FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI += "file://vcpe_dhcp4c_shim.c"
SRC_URI += "file://dhcpv4c_api.c"

DEPENDS_append = " rdkb-halif-dhcp"

do_configure_prepend() {
    if [ -f ${WORKDIR}/dhcpv4c_api.c ] && [ -f ${S}/dhcpv4c_api.c ]; then
        install -m 0644 ${WORKDIR}/dhcpv4c_api.c ${S}/dhcpv4c_api.c
    fi

    if [ -f ${WORKDIR}/vcpe_dhcp4c_shim.c ] && [ ! -f ${S}/vcpe_dhcp4c_shim.c ]; then
        install -m 0644 ${WORKDIR}/vcpe_dhcp4c_shim.c ${S}/vcpe_dhcp4c_shim.c
        if [ -f ${S}/Makefile.am ]; then
            sed -i 's/\(libapi_dhcpv4c_la_SOURCES\s*=.*\)/\1 vcpe_dhcp4c_shim.c/' ${S}/Makefile.am
        fi
    fi
}

# meta-cmf-bananapi adds MediaTek's rdkb_hal as a second Git source but does
# not pin that source. BitBake refuses to fetch an unpinned SCM URL. Keep the
# known-good main revision reproducible and include both SCM names in PV's
# aggregate revision.
SRCREV_default = "e0fded2dff10d7c7b9be00e7c6479ce4c666c59a"
SRCREV_FORMAT = "dhcpv4hal_default"
