# Build a DAC bundle (rootfs/ + config.json) from a normal Yocto image
# recipe.  Output is dropped in DEPLOY_DIR_IMAGE as <basename>.bundle.tar in
# the flat layout DSM's local-tarball packager expects (./rootfs/ +
# ./config.json at the top of the archive).
#
# Per-app recipes set:
#   DAC_CONFIG_JSON   absolute path to the OCI config.json for this image
#                     (default: ${THISDIR}/files/config.json)
#   IMAGE_INSTALL     usual Yocto image packages (lighttpd, busybox, your app, ...)
#
# A regular tar.gz of the rootfs is also produced (useful for debug).

inherit image

# No kernel needed - container shares the host's kernel
PREFERRED_PROVIDER_virtual/kernel ?= "linux-dummy"

# We want at minimum a rootfs tar.gz; the bundle is layered on top.
IMAGE_FSTYPES ?= "tar.gz"

# Strip cruft we don't want in a containerized rootfs.
IMAGE_FEATURES = ""
IMAGE_LINGUAS = ""
NO_RECOMMENDATIONS = "1"
LICENSE ?= "MIT"

# The vCPE machine.conf appends RDK-B platform packages to every image's
# IMAGE_INSTALL.  We don't want them in a containerized rootfs.
IMAGE_INSTALL:remove = "vcpe-init ccsp-gwprovapp"

# Anything dynamically linked needs the loader + libc, so seed those in.
# Apps can append their own (lighttpd, busybox, etc.).
IMAGE_INSTALL:append = " glibc"

# Default location of the bundle config.json relative to the image recipe.
DAC_CONFIG_JSON ??= "${THISDIR}/files/config.json"

# Run after the rootfs is finalized but before checksumming.
IMAGE_POSTPROCESS_COMMAND += "dac_bundle_assemble;"

dac_bundle_assemble() {
    set -e
    if [ ! -f "${DAC_CONFIG_JSON}" ]; then
        bbfatal "DAC_CONFIG_JSON does not exist: ${DAC_CONFIG_JSON}"
    fi

    bundle_work="${WORKDIR}/dac-bundle"
    rm -rf "${bundle_work}"
    mkdir -p "${bundle_work}"

    # cp -a preserves symlinks, perms, ownership
    cp -a "${IMAGE_ROOTFS}" "${bundle_work}/rootfs"

    cp "${DAC_CONFIG_JSON}" "${bundle_work}/config.json"

    # Flat-layout bundle archive for DSM
    out="${DEPLOY_DIR_IMAGE}/${IMAGE_BASENAME}.bundle.tar"
    tar -C "${bundle_work}" -cf "${out}" rootfs config.json

    # Convenience symlink: <basename>.tar -> <fully-stamped>.bundle.tar
    ln -sfn "${IMAGE_BASENAME}.bundle.tar" "${DEPLOY_DIR_IMAGE}/${IMAGE_BASENAME}.tar"

    bbnote "DAC bundle written to ${out}"

    rm -rf "${bundle_work}"
}
