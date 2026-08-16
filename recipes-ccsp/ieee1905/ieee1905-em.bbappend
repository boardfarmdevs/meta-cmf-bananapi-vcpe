FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

# rbus-sys's build.rs uses cargo's HOST env var (build-machine triple) instead of
# TARGET (the triple actually being compiled for) when telling bindgen what
# architecture to parse the rbus C headers for. On our i686 container target this
# makes bindgen's compile-time struct-layout assertions overflow (see patch header
# for the exact error). ieee1905-em is only installed by the AP-extender machine
# (qemux86bpiap), so this recipe -- and this fix -- never applies to the plain
# broadband container build.
SRC_URI += "file://0001-rbus-sys-use-TARGET-not-HOST-for-bindgen-clang-arg.patch"

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
        grep -q '^RestartSec=' "$u" || sed -i '/^Restart=always/a RestartSec=3' "$u"
        bbnote "meta-cmf-bananapi-vcpe: ieee1905 controller waits for brlan0 and invokes veth setup directly"
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
        bbnote "meta-cmf-bananapi-vcpe: reordered/bounded ExecStartPre in ieee1905_em_agent.service"
    fi
}
