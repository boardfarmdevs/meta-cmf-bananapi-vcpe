FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Fix obuspa pegging a core at 100% as soon as timingila publishes any
# Device.SoftwareModules.* table-change event.  Missing iterator-advance in
# the rbus event-property scanning loop in the RDK vendor plugin.
SRC_URI += "file://0001-fix-LCM_Handle_Table_Changes-infinite-loop.patch"
