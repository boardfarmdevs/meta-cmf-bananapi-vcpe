vcpe_patch_system_defaults() {
    sd="${D}${sysconfdir}/utopia/system_defaults"
    if [ -f "$sd" ]; then
        sed -i \
            -e 's|^\$\$lan_ethernet_physical_ifnames=.*|$$lan_ethernet_physical_ifnames=eth1|' \
            "$sd"
    fi
}
do_install[postfuncs] += "vcpe_patch_system_defaults"
