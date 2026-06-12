FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Make cthulhu's sandbox-cgroup config tolerant of cgroup v2 unified
# hierarchy on the host.  Without this, the sandbox can't reach Up state
# and timingila refuses every InstallDU with "EE not enabled".
# Also bake AllocatedDiskSpace=-1 into the default sandbox so the
# loop-mount step is skipped (loop mounts aren't permitted in unprivileged
# LXC containers).
SRC_URI += "file://0001-cgroup-v2-tolerance.patch"

# Patch the shipped defaults.d file at do_install time
do_install:append() {
    if [ -f ${D}${sysconfdir}/amx/cthulhu/defaults.d/cthulhu_defaults.odl ]; then
        sed -i "s/parameter 'AllocatedDiskSpace' = 5120/parameter 'AllocatedDiskSpace' = -1/" \
            ${D}${sysconfdir}/amx/cthulhu/defaults.d/cthulhu_defaults.odl
    fi
}
