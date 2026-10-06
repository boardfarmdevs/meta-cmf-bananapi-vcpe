vcpe_patch_system_defaults() {
    sd="${D}${sysconfdir}/utopia/system_defaults"
    if [ -f "$sd" ]; then
        sed -i \
            -e 's|^\$\$lan_ethernet_physical_ifnames=.*|$$lan_ethernet_physical_ifnames=eth1|' \
            "$sd"
    fi
}
do_install[postfuncs] += "vcpe_patch_system_defaults"

# The gateway's dnsmasq binds per interface (bind-dynamic): the EMOSA pods' GRE termination
# point runs a DHCP server of its own on their underlay bridge (see the patch). Deferred
# _append, as the libwebconfig bbappend explains for this layer stack.
FILESEXTRAPATHS_prepend := "${THISDIR}/utopia:"
SRC_URI_append = " file://0001-dhcp-server-dnsmasq-binds-per-interface.patch"
