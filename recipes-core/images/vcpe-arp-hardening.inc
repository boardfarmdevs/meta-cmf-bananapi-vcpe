# ARP is answered only on the interface that holds the address asked for. The veth peers the
# 1905 stacks use (eth0_virt_peer, eth1_virt_peer: no IPv4 address, their partners brlan0
# ports) receive every LAN broadcast; they stayed silent only because rp_filter (2, systemd's
# default) fails the input route of an address-less interface, and the addressed bridges no LAN
# broadcast reaches (brpodbh, br106, br403, brebhaul) answered for 10.0.0.1 with arp_ignore 0
# (rdk-1004, 9 October: no flux, by that side effect alone). The kernel takes the larger of
# all and the interface for both, so brlan0's own arp_ignore 2 stays; default covers the veths
# made after boot. Both images: the gateway (rdk-generic-broadband-image) and the extenders
# (rdk-generic-ap-extender-image) run the same 1905 veths.
vcpe_arp_hardening() {
    mkdir -p ${IMAGE_ROOTFS}${sysconfdir}/sysctl.d
    cat > ${IMAGE_ROOTFS}${sysconfdir}/sysctl.d/60-vcpe-arp.conf <<'EOF'
net.ipv4.conf.all.arp_ignore = 1
net.ipv4.conf.default.arp_ignore = 1
net.ipv4.conf.all.arp_announce = 2
net.ipv4.conf.default.arp_announce = 2
EOF
}

ROOTFS_POSTPROCESS_COMMAND_append = " vcpe_arp_hardening;"
