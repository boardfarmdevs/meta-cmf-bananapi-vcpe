# Build with DAC / LCM

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
