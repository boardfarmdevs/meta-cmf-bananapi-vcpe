# Build vcpe (bpi) container image

# create repo mirror (once)

```text

mkdir -p $HOME/yocto/mirror/rdkb-bpi-nosrc
cd $HOME/yocto/mirror/rdkb-bpi-nosrc

repo init --mirror \
  -u https://code.rdkcentral.com/r/manifests \
  -b kirkstone \
  -m rdkb-bpi-nosrc.xml \
  --no-clone-bundle

repo sync -j$(nproc) \
  --no-clone-bundle \
  --no-tags \
  --optimized-fetch \
  --fail-fast

```

# update repo mirror

```text
cd $HOME/yocto/mirror/rdkb-bpi-nosrc
repo sync -j$(nproc) --no-clone-bundle --no-tags

```

# create new repo from repo mirror

```text

mkdir -p $HOME/yocto/rdkb-bpi-nosrc-vcpe-0408
cd $HOME/yocto/rdkb-bpi-nosrc-vcpe-0408


repo init \
  -u https://code.rdkcentral.com/r/manifests \
  -b kirkstone \
  -m rdkb-bpi-nosrc.xml \
  --reference=$HOME/yocto/mirror/rdkb-bpi-nosrc


repo sync -j$(nproc) \
  --no-clone-bundle \
  --no-tags \
  --optimized-fetch

```

# build

```text

git clone git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git

cp meta-cmf-bananapi-vcpe/conf/machine/qemux86bpibroadband.conf.sample meta-cmf-bananapi/conf/machine/qemux86bpibroadband.conf

MACHINE=qemux86bpibroadband source meta-cmf-bananapi/setup-environment-refboard-rdkb

bitbake-layers add-layer ../meta-cmf-bananapi-vcpe

bitbake rdk-generic-broadband-image -k
```

# build with dac-lcm

To include the prpl Lifecycle Manager (cthulhu + AMX stack, OCI bundles via crun)
in the image, add the meta-lcm layer and switch the apps toolkit runtime from its
default ("DAC") to LCM. Can use a separate build directory (e.g.
`build-qemux86bpibroadband-lcm`) sharing the same `DL_DIR`/`SSTATE_DIR`, as the
`DISTRO_FEATURES` change invalidates sstate broadly and toggling it in-place
forces large rebuilds.

```text

bitbake-layers add-layer ../meta-lcm
```

Add to conf/local.conf:

```text

# Switch the apps toolkit from its default ("DAC") to LCM
RDK_BB_APPS_TOOLKIT_CRUNTIME = "LCM"

# meta-lcm ships cmake 3.18.4 pinned to dunfell; mask it so OE's 3.22.3 wins
BBMASK_append = "|meta-lcm/recipes-devtools/cmake/"

# OCI bundles + crun instead of LXC-in-LXC
DISTRO_FEATURES_remove = "lcm-images lxc-backend"
DISTRO_FEATURES_append = " lcm-bundles crun-backend "
```

Then build as usual. A deployable demo app bundle can be built with
`bitbake dac-image-tictactoe` (see classes/dac-bundle-image.bbclass and
examples/).

# Summary

This layer takes the **Banana Pi R4 (MediaTek Filogic880 / MT7988) RDK-B broadband build** and retargets it to **x86 userspace packaged as an LXC
container** for running inside LXD on a host machine. The output is a `*.lxc.tar.bz2` rootfs tarball that runs the same RDK-B userspace stack
the physical bananapi runs (utopia, ccsp-*, RdkWanManager, ccsp-dhcp-mgr, hal-generic, rbus, sysevent, syscfg, telemetry, ...) on
x86 with no kernel modules and no real wifi radio.
