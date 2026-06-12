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

# LCM: cthulhu's service unit writes to /sys/fs/cgroup/memory/memory.use_hierarchy
# and /sys/fs/cgroup/cpuset/cgroup.clone_children -- cgroup v1 paths.  Hosts
# running cgroup v2 unified (modern Linux) lack these; the ExecStartPre's fail
# and cthulhu never starts.  The directives are advisory performance hints, safe
# to drop on cgroup v2.
vcpe_fix_lcm_cthulhu_cgroup() {
    if [ -f ${IMAGE_ROOTFS}${systemd_unitdir}/system/lcm-cthulhu.service ]; then
        mkdir -p ${IMAGE_ROOTFS}${systemd_unitdir}/system/lcm-cthulhu.service.d
        cat > ${IMAGE_ROOTFS}${systemd_unitdir}/system/lcm-cthulhu.service.d/00-vcpe.conf <<'EOF'
[Service]
# cgroup v1 paths don't exist on cgroup v2 hosts; strip the v1 ExecStartPre's
ExecStartPre=
EOF
    fi
}

# LCM: cthulhu writes per-container syslog-ng configs to
# /lcm/cthulhu/syslogng/configs/<DUID>.conf and runs `syslog-ng-ctl reload`
# to pick them up.  syslog-ng walks them via /etc/amx/cthulhu/syslog-ng-lcm.conf
# (an @include for the configs dir).  But the shipped /etc/syslog-ng/syslog-ng.conf
# has NO @include pointing at that fragment, so syslog-ng never knows about the
# per-container sources.  cthulhu then logs "Syslogng did not create the log
# socket" and silent long-running daemons in containers (like lighttpd) lose
# their stdio plumbing.  Fix: append the @include to the main config.
vcpe_fix_syslog_ng_cthulhu_include() {
    cfg=${IMAGE_ROOTFS}${sysconfdir}/syslog-ng/syslog-ng.conf
    if [ -f "$cfg" ] && ! grep -q "syslog-ng-lcm.conf" "$cfg"; then
        cat >> "$cfg" <<'EOF'

# Pulled in by meta-cmf-bananapi-vcpe so LCM/cthulhu per-container log
# sockets are routable.  See /etc/amx/cthulhu/syslog-ng-lcm.conf.
@include "/etc/amx/cthulhu/syslog-ng-lcm.conf"
EOF
    fi
}

ROOTFS_POSTPROCESS_COMMAND_append = " mask_onewifi_units; fix_ccspwebui; fix_cr_deviceprofile; vcpe_drop_boot_sleeps; vcpe_fix_dnsmasq_lan_deps; vcpe_fix_sync_ordering; vcpe_fix_lcm_cthulhu_cgroup; vcpe_fix_syslog_ng_cthulhu_include;"
