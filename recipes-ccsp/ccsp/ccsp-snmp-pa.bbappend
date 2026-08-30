FILESEXTRAPATHS_prepend := "${THISDIR}/${PN}:"

SRC_URI_append = " \
    file://0001-run-subagent-find-existing-processes-across-users.patch \
"
