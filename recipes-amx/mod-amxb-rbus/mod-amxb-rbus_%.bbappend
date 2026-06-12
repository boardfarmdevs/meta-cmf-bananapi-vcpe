FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Add a weak rbusConfig_Get fallback so this module loads against the
# rdkcentral rbus fork (which doesn't export the symbol).  See the patch
# header for full reasoning; tl;dr: setting timeouts becomes a no-op.
SRC_URI += "file://0001-stub-rbusConfig_Get-for-rdkcentral-rbus.patch"
