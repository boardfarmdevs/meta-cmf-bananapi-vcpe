# Build

| role | MACHINE | image |
|---|---|---|
| controller (standard bpi) | `qemux86bpibroadband` | `rdk-generic-broadband-image` |
| AP extender (bpi-ap) | `qemux86bpiap` | `rdk-generic-ap-extender-image` |

One tree serves both machines, with a build directory per MACHINE. The 0905
release is based on RDK Central's `kirkstone` manifest family and its
`rdkb-bpi-nosrc.xml` manifest as captured on 2026-09-02. The RDK OE projects
were on `rdk-next`, but the build uses the accompanying
[`rdkb-bpi-nosrc-0905.xml`](rdkb-bpi-nosrc-0905.xml) lock file with immutable
commit IDs, deliberately retaining the reviewed 0902 upstream revisions.
The lab layer is canonical on `codex/0905-clean`. Do not build a release
directly from moving upstream branches or reuse an older release's images.

```text
mkdir -p $HOME/yocto/rdkb-bpi-nosrc-vcpe-0905-clean
cd $HOME/yocto/rdkb-bpi-nosrc-vcpe-0905-clean

# must precede setup-environment: MACHINE is resolved from conf/machine here
git clone --branch codex/0905-clean \
  git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git

# Bootstrap from the exact manifest-repository revision used by 0902, then
# select the release lock carried by this repository.
repo init -u https://code.rdkcentral.com/r/manifests \
  -b a4637a8cadb68e34dedba6e8a5afd9432cdc3a05 \
  -m rdkb-bpi-nosrc.xml
cp meta-cmf-bananapi-vcpe/doc/build/rdkb-bpi-nosrc-0905.xml \
  .repo/manifests/rdkb-bpi-nosrc-0905.xml
repo init -m rdkb-bpi-nosrc-0905.xml
repo sync -j$(nproc) --no-clone-bundle

cat > clean-build.conf <<EOF
BB_NUMBER_THREADS:forcevariable = "8"
PARALLEL_MAKE:forcevariable = "-j 8"
SSTATE_DIR:forcevariable = "$PWD/sstate-cache"
SSTATE_MIRRORS:forcevariable = ""
EOF

MACHINE=qemux86bpibroadband BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpibroadband
bitbake -R ../clean-build.conf rdk-generic-broadband-image

cd ..

MACHINE=qemux86bpiap BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpiap
bitbake -R ../clean-build.conf rdk-generic-ap-extender-image
```

Verify the source lock before building:

```sh
repo manifest -r -o /tmp/actual.xml
diff -u meta-cmf-bananapi-vcpe/doc/build/rdkb-bpi-nosrc-0905.xml \
  /tmp/actual.xml
```

Only comments and insignificant whitespace should differ. To create a future
release lock, deliberately initialize and synchronize the chosen upstream
manifest branch, run `repo manifest -r`, review every changed project revision,
and add the reviewed output under a new release name. Never overwrite the 0902
lock.

A complete 0905 rebuild starts with new `build-qemux86bpibroadband` and
`build-qemux86bpiap` directories and an empty 0905 `SSTATE_DIR`; disable
external `SSTATE_MIRRORS`. Reusing verified source downloads is permitted,
but reusing older compiled sstate or rootfs archives is not. The second role
may share tasks freshly built for the first role within this same release.
Retain both complete build logs, the resolved manifest, source commit, build
configuration, output filenames, and SHA-256 checksums with the release
evidence. A successful component compile is not a complete image build.
The post-read configuration above overrides the machine defaults, which
otherwise share `$HOME/oe/sstate-cache`. Confirm the effective `SSTATE_DIR`
and empty `SSTATE_MIRRORS` using `bitbake -R ../clean-build.conf -e IMAGE`.

The controller WebUI Go server is intentionally carried in
`unified-wifi-mesh/em-cli.tar.gz` because the stock CLI recipe cannot fetch its
modules in this build. When an EasyMesh patch changes `src/rdkb-cli/main.go`,
first compile `unified-wifi-mesh`, rebuild the checked-in helper from that
workdir, and then build the image again:

```sh
bitbake -R ../clean-build.conf unified-wifi-mesh -c compile
../meta-cmf-bananapi-vcpe/gen/rebuild-em-cli-artifact.sh \
  "$PWD/tmp/work/core2-32-rdk-linux/unified-wifi-mesh/v0.3.1-r0"
bitbake -R ../clean-build.conf rdk-generic-broadband-image
```

Review and commit both the source patch and `em-cli.tar.gz`. Verify the helper
hash recorded in the [patch-set reference](../easymesh/reference/patch-set.md);
a successful image build alone
does not prove that a changed Go handler was included.

Optional: a local [repo mirror](../repo-mirror) makes creating and re-syncing
trees faster.

These are the container equivalents of the BPI-R4 hardware build instructions on
the RDK wiki
([EasyMesh unified-wifi-mesh Porting on Banana Pi R4](https://wiki.rdkcentral.com/spaces/RDK/pages/378377039/EasyMesh+unified-wifi-mesh+Porting+on+Banana+Pi+R4)),
which use `bananapi4-rdk-broadband` / `bananapi4-rdk-broadband-ap-extender` and
the `extsrc` manifests. `FEATURE_TYPE=EasyMesh` is not needed here -- the machine
configs set `EasyMesh`/`with_alsap` themselves, and `qemux86bpiap` adds
`em_extender`.
