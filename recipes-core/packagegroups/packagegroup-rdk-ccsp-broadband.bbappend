# The BPI layer deliberately ships its patched/prebuilt onewifi_em_cli and
# WebUI assets from unified-wifi-mesh.  Current RDK Central also adds the stock
# unified-wifi-mesh-cli recipe to this package group, but both recipes claim
# /usr/bin/onewifi_em_cli and /usr/ccsp/EasyMesh/static.  Installing both IPKs
# therefore fails do_rootfs with deterministic file-owner conflicts.
#
# Keep the BPI-owned CLI that matches this layer's libemcli and WebUI patches;
# do not install the redundant stock CLI package in BPI broadband images.  The
# recipe remains available to other images and layers.
RDEPENDS_packagegroup-rdk-ccsp-broadband_remove = "unified-wifi-mesh-cli"
