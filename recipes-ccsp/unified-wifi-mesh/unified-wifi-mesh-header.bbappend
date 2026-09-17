FILESEXTRAPATHS_prepend := "${THISDIR}/${BPN}:"

SRC_URI_append = " file://0001-align-public-header-abi.patch file://0002-align-ap-report-snapshot-abi.patch"
