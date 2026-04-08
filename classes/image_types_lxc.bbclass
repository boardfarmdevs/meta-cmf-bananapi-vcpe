inherit image_types
TYPES_EXTRA:append = " lxc"

# Function to create the lxc image
IMAGE_CMD:lxc() {
    # Create temporary directory structure
    mkdir -p ${WORKDIR}/lxc-image/rootfs

    # Create metadata.yaml with creation_date as Unix timestamp
    cat > ${WORKDIR}/lxc-image/metadata.yaml << EOF
architecture: "i686"
creation_date: $(date +%s)
properties:
  architecture: "i686"
  description: "${@d.getVar("IMAGE_NAME", True)}"
  os: "linux"
  release: "2.1"
EOF

    # Copy rootfs contents
    cp -a ${IMAGE_ROOTFS}/. ${WORKDIR}/lxc-image/rootfs/

    # Create unified tarball with xz compression
    # Use fixed timestamp to avoid warnings (Dec 21, 2023)
    tar --sort=name --owner=root:0 --group=root:0 \
         \
        --numeric-owner -C ${WORKDIR}/lxc-image \
        -cjf ${IMGDEPLOYDIR}/${IMAGE_NAME}${IMAGE_NAME_SUFFIX}.lxc.tar.bz2 .

    # Create symlink without timestamp
    cd ${IMGDEPLOYDIR}
    ln -sf ${IMAGE_NAME}${IMAGE_NAME_SUFFIX}.lxc.tar.bz2 \
        ${IMAGE_LINK_NAME}.lxc.tar.bz2

    # Cleanup
    rm -rf ${WORKDIR}/lxc-image
}

# Define dependencies
do_image_lxc[depends] += "${@bb.utils.contains('IMAGE_FSTYPES', 'tar', '${PN}:do_image_tar', '', d)}"
