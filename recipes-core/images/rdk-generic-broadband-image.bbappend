mask_onewifi_units() {
    for unit in onewifi.service filogicwifiinitialized.path \
                checkfilogicwifisupport.path checkfilogicwifisupport.service; do
        ln -sf /dev/null ${IMAGE_ROOTFS}${systemd_unitdir}/system/$unit
    done
}

fix_ccspwebui() {
    sed -i 's/gwprovethwan\.service/gwprovapp.service/g' \
        ${IMAGE_ROOTFS}${systemd_unitdir}/system/CcspWebUI.service
    sed -i '/^sleep 10/d' \
        ${IMAGE_ROOTFS}${base_libdir}/rdk/CcspWebUI.sh
}

IMAGE_INSTALL_append = " ccsp-tr069-pa ccsp-tr069-pa-ccsp"
IMAGE_INSTALL_append = " systemd-analyze"

fix_cr_deviceprofile() {
    for f in ${IMAGE_ROOTFS}/usr/ccsp/cr-deviceprofile.xml \
             ${IMAGE_ROOTFS}/usr/ccsp/cr-ethwan-deviceprofile.xml; do
        [ -f "$f" ] || continue
        python3 -c "
import re, sys
p = sys.argv[1]
with open(p) as fh: s = fh.read()
pattern = re.compile(r'(\s*)<component>\s*<name>com\.cisco\.spvtg\.ccsp\.wifi</name>\s*<version>\d+</version>\s*</component>', re.DOTALL)
s2 = pattern.sub(r'\1<!-- vcpe: wifi component removed (no wifi hw in LXC) -->', s)
if s2 != s:
    with open(p, 'w') as fh: fh.write(s2)
" "$f"
    done
}

# Drop hardcoded ExecStartPre sleeps: 30s on CcspAdvSecuritySsp, 12s on rfc.
# Neither service is on the WAN/LAN path; both block multi-user.target.
vcpe_drop_boot_sleeps() {
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/CcspAdvSecuritySsp.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/CcspAdvSecuritySsp.service.d/00-vcpe.conf <<'EOF'
[Service]
ExecStartPre=
EOF
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/rfc.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/rfc.service.d/00-vcpe.conf <<'EOF'
[Service]
ExecStartPre=
ExecStartPre=-/bin/cp /etc/rfc.properties /nvram/
EOF
}

# dnsmasq serves LAN DHCP/DNS on brlan0; must not be gated on WAN.
# Drop Requires=network-online.target, order after CcspPandMSsp (brlan0 up).
vcpe_fix_dnsmasq_lan_deps() {
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/dnsmasq.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/dnsmasq.service.d/00-vcpe.conf <<'EOF'
[Unit]
Requires=
After=
After=CcspPandMSsp.service securemount.service
EOF
}

# PsmSsp, RdkWanManager: drop redundant utopiaInitCheck.sh (kept on CcspPandMSsp).
# RdkWanManager: dedupe duplicated After=PsmSsp.service.
# CcspPandMSsp: order After=RdkWanManager so GwProvCheck.sh sees OS_WANMANAGER_ENABLED.
# parodus: cap the unbounded parodusStartCheck.sh poll at 60s.
vcpe_fix_sync_ordering() {
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/PsmSsp.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/PsmSsp.service.d/00-vcpe.conf <<'EOF'
[Service]
ExecStartPre=
ExecStartPre=-/bin/sh -c '(/usr/ccsp/log_psm.db.sh)'
ExecStartPre=-/bin/sh -c '(/usr/ccsp/migration_for_psm.sh)'
EOF
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/RdkWanManager.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/RdkWanManager.service.d/00-vcpe.conf <<'EOF'
[Unit]
After=
After=CcspCrSsp.service PsmSsp.service ApplySystemDefaults.service

[Service]
ExecStartPre=
ExecStartPre=/bin/sh /lib/rdk/run_rm_key.sh
ExecStartPre=/bin/touch /tmp/OS_WANMANAGER_ENABLED
ExecStartPre=-/bin/sh -c '[ -x /usr/ccsp/dhcpmgr/DHCPMgrPSMValueCheck.sh ] && (/usr/ccsp/dhcpmgr/DHCPMgrPSMValueCheck.sh)'
EOF
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/CcspPandMSsp.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/CcspPandMSsp.service.d/00-vcpe.conf <<'EOF'
[Unit]
After=RdkWanManager.service
EOF
    mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/parodus.service.d
    cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/parodus.service.d/00-vcpe.conf <<'EOF'
[Service]
TimeoutStartSec=60s
EOF
}

ROOTFS_POSTPROCESS_COMMAND_append = " mask_onewifi_units; fix_ccspwebui; fix_cr_deviceprofile; vcpe_drop_boot_sleeps; vcpe_fix_dnsmasq_lan_deps; vcpe_fix_sync_ordering;"
