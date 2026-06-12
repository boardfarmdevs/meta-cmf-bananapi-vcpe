SUMMARY = "Tic-Tac-Toe DAC container image (OCI bundle)"
DESCRIPTION = "Builds a Yocto image of lighttpd + tic-tac-toe content and \
packages it as a DAC-deployable bundle (rootfs/ + config.json).  Deploy \
the resulting <name>.bundle.tar via dsmcli du.install."

inherit dac-bundle-image

# Use the OCI config.json next to this recipe.
DAC_CONFIG_JSON = "${THISDIR}/files/config.json"

# IMAGE_INSTALL:append (set in the class) seeds glibc; we add the rest:
# - lighttpd: pulls in mod_indexfile, mod_dirlisting, mod_staticfile via RDEPENDS
# - tictactoe-content: HTML/JS/CSS + /etc/lighttpd.conf
IMAGE_INSTALL:append = " \
    lighttpd \
    tictactoe-content \
"
