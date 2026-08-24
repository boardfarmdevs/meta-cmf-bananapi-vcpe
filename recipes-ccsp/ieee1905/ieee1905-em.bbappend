FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# rbus-sys's build.rs uses cargo's HOST env var (build-machine triple) instead of
# TARGET (the triple actually being compiled for) when telling bindgen what
# architecture to parse the rbus C headers for. On our i686 container target this
# makes bindgen's compile-time struct-layout assertions overflow (see patch header
# for the exact error). ieee1905-em is only installed by the AP-extender machine
# (qemux86bpiap), so this recipe -- and this fix -- never applies to the plain
# broadband container build.
SRC_URI += "file://0001-rbus-sys-use-TARGET-not-HOST-for-bindgen-clang-arg.patch"
SRC_URI += "file://0002-topology-gc-notify-expired-neighbors.patch"
SRC_URI += "file://0003-topology-forward-local-change-to-al-sap.patch"
SRC_URI += "file://0004-topology-age-only-on-received-evidence.patch"
SRC_URI += "file://0005-topology-publish-neighbor-added-events.patch"
SRC_URI += "file://0006-topology-forward-changed-responses-to-al-sap.patch"

# ieee1905_em_ctrl.service must wait for the interface it actually uses, not the
# nominal WAN. In the LXD/hwsim controller syscfg reports wan_physical_ifname=erouter0,
# but no erouter0 netdev exists; ieee1905 instead binds eth0_virt_peer, which the next
# pre-start command connects to brlan0. Waiting for erouter0 therefore adds 120 seconds
# to every attempt even though the required LAN bridge is ready.
#
# The stock setup-veth line also wraps setup_veth_for_em.sh in backticks. Its stdout is
# command substitution, so output such as "Cleaning existing interfaces..." is executed
# by /bin/sh and makes the first controller start fail with status 127. Rebuild both
# pre-start commands explicitly: wait (bounded) for brlan0, then invoke the setup script
# normally. If brlan0 genuinely never appears, fail the pre-start and let systemd retry
# after a short delay instead of starting ieee1905 on an invalid transport.
do_install_append() {
    u="${D}${systemd_unitdir}/system/ieee1905_em_ctrl.service"
    if [ -f "$u" ]; then
        sed -i '/^ExecStartPre=/d' "$u"
        sed -i "\@^ExecStart=@i ExecStartPre=/bin/sh -c 'i=0; while [ ! -e /sys/class/net/brlan0/address ] \&\& [ \$i -lt 60 ]; do i=\$((i+1)); sleep 1; done; [ -e /sys/class/net/brlan0/address ]'\nExecStartPre=/bin/sh -c 'if [ ! -e \"/sys/class/net/eth0_virt_peer/address\" ]; then /usr/ccsp/EasyMesh/setup_veth_for_em.sh brlan0 eth0 true; fi'" "$u"

        # The upstream unit backgrounds ieee1905 from a shell under
        # Type=forking.  That makes systemd guess the main PID and permits the
        # unit to become active before the AL-SAP sockets exist.  It also leaves
        # process ownership ambiguous across an em_ctrl restart, which was
        # observed as a live ieee1905 PID with no useful controller delivery.
        # ieee1905 already sends READY=1 after binding both AL-SAP listeners, so
        # run it in the foreground as a notify service and let systemd track the
        # real process.  Keep its output in the bounded journal, not an
        # append-only file in /tmp.
        sed -i 's/^Type=forking$/Type=notify/' "$u"
        sed -i 's|^ExecStart=.*$|ExecStart=/usr/bin/ieee1905 -f off -i eth0_virt_peer --sap-data-path /tmp/al_em_ctrl_data_socket --sap-control-path /tmp/al_em_ctrl_control_socket|' "$u"
        sed -i '/^StandardOutput=/d; /^StandardError=/d; /^SyslogIdentifier=/d' "$u"
        sed -i '/^ExecStart=\/usr\/bin\/ieee1905 /a StandardOutput=journal\
StandardError=journal\
SyslogIdentifier=ieee1905_em_ctrl' "$u"

        grep -q '^RestartSec=' "$u" || sed -i '/^Restart=always/a RestartSec=3' "$u"
        grep -q '^Type=notify$' "$u" || bbfatal "meta-cmf-bananapi-vcpe: failed to make ieee1905 controller a notify service"
        ! grep -q '/tmp/ieee1905_ctrl_log\.txt' "$u" || bbfatal "meta-cmf-bananapi-vcpe: unbounded ieee1905 controller log remains"
        bbnote "meta-cmf-bananapi-vcpe: ieee1905 controller is foregrounded, readiness-tracked, and waits for brlan0"
    fi
}


# ieee1905_em_ext_agent.service (installed as ieee1905_em_agent.service) has its two
# ExecStartPre lines in the wrong order, and the first one can block forever:
#
#   1. setup_ext_pre.sh  -- unbounded `while [ ! -e /tmp/wifi_initialized ] ...` plus a
#      second unbounded wait for a VAP matching AL_MAC_ADDR to report both channel and
#      ssid, and finally `udhcpc -i brlan0`.
#   2. setup_veth_for_em.sh -- creates the eth1_virt_peer veth that ieee1905 binds to.
#
# So the unit waits (potentially forever) on wifi/DHCP state *before* creating the
# interface, and on a cold leaf the VAP wait never completes: the fronthaul VAPs only
# get created once the controller answers AP-Autoconfiguration and pushes WSC M2 --
# which can't happen while ieee1905 (the 1905 transport carrying that exchange) hasn't
# started. The unit sits in "activating (start-pre)" indefinitely and the leaf never
# joins the mesh.
#
# Reorder so the veth is created first, and bound setup_ext_pre.sh with `timeout ... ||
# true` so it becomes best-effort: everything it waits for is also converged into by the
# agent itself once it is running, so letting it start late is strictly better than not
# starting at all. Also drops the backticks around the setup_veth_for_em.sh call -- the
# stock line command-substitutes the script and then tries to execute its *output* as a
# command, which is only harmless because the script happens to print nothing.
do_install_append() {
    f="${D}${systemd_unitdir}/system/ieee1905_em_agent.service"
    if [ -f "$f" ]; then
        sed -i '/^ExecStartPre=/d' "$f"
        sed -i "\@^ExecStart=@i ExecStartPre=/bin/sh -c 'if [ ! -e \"/sys/class/net/eth1_virt_peer/address\" ]; then /usr/ccsp/EasyMesh/setup_veth_for_em.sh brlan0 eth1 false; fi'\nExecStartPre=/bin/sh -c 'timeout 60 /usr/ccsp/EasyMesh/setup_ext_pre.sh || true'" "$f"

        # The remote-agent unit has the same process-ownership and tmpfs-log
        # defects as the controller unit corrected above.  ieee1905's default
        # AL-SAP paths are used by the agent invocation and it sends READY=1
        # after both listeners are bound, so systemd can track real readiness.
        sed -i 's/^Type=forking$/Type=notify/' "$f"
        sed -i 's|^ExecStart=.*$|ExecStart=/usr/bin/ieee1905 -f off -i eth1_virt_peer|' "$f"
        sed -i '/^StandardOutput=/d; /^StandardError=/d; /^SyslogIdentifier=/d' "$f"
        sed -i '/^ExecStart=\/usr\/bin\/ieee1905 /a StandardOutput=journal\
StandardError=journal\
SyslogIdentifier=ieee1905_em_agent' "$f"
        grep -q '^RestartSec=' "$f" || sed -i '/^Restart=always/a RestartSec=3' "$f"

        grep -q '^Type=notify$' "$f" || bbfatal "meta-cmf-bananapi-vcpe: failed to make ieee1905 agent a notify service"
        ! grep -q '/tmp/ieee1905_agent_log\.txt' "$f" || bbfatal "meta-cmf-bananapi-vcpe: unbounded ieee1905 agent log remains"
        bbnote "meta-cmf-bananapi-vcpe: ieee1905 agent is foregrounded, readiness-tracked, and uses bounded journald"
    fi
}
