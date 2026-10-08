vcpe_patch_system_defaults() {
    sd="${D}${sysconfdir}/utopia/system_defaults"
    if [ -f "$sd" ]; then
        sed -i \
            -e 's|^\$\$lan_ethernet_physical_ifnames=.*|$$lan_ethernet_physical_ifnames=eth1|' \
            "$sd"
    fi
}
do_install[postfuncs] += "vcpe_patch_system_defaults"

# The gateway keeps its DHCP leases across a start. meta-cmf-filogic's bbappend has
# utopia_init.sh remove /nvram/dnsmasq.leases at every boot, while the lab's clients keep
# their addresses (week-long leases, requested once on association) and do not ask again:
# dnsmasq then hands an address a client still holds, off the air at that moment, to
# whatever asks first (rdk-1004, 7 October 2026: a pod took a client's address after a
# redeploy, and the client's traffic went to the pod). A factory reset still removes them
# (its own, indented line).
vcpe_keep_dhcp_leases() {
    init="${D}${sysconfdir}/utopia/utopia_init.sh"
    if [ -f "$init" ]; then
        sed -i -e '/^rm -f \/nvram\/dnsmasq\.leases *$/d' "$init"
    fi
}
do_install[postfuncs] += "vcpe_keep_dhcp_leases"

# The gateway's dnsmasq binds per interface (bind-dynamic): the EMOSA pods' GRE termination
# point runs a DHCP server of its own on their underlay bridge (see the patch). Deferred
# _append, as the libwebconfig bbappend explains for this layer stack.
FILESEXTRAPATHS_prepend := "${THISDIR}/utopia:"
SRC_URI_append = " file://0001-dhcp-server-dnsmasq-binds-per-interface.patch"
