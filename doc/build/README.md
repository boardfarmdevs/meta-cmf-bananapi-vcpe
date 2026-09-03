# Build

| role | MACHINE | image |
|---|---|---|
| controller (standard bpi) | `qemux86bpibroadband` | `rdk-generic-broadband-image` |
| AP extender (bpi-ap) | `qemux86bpiap` | `rdk-generic-ap-extender-image` |

One tree serves both machines, with a build directory per MACHINE. The 0902
release is based on RDK Central's `kirkstone` manifest family and its
`rdkb-bpi-nosrc.xml` manifest as captured on 2026-09-02. The RDK OE projects
were on `rdk-next`, but the build uses the accompanying
[`rdkb-bpi-nosrc-0902.xml`](rdkb-bpi-nosrc-0902.xml) lock file with immutable
commit IDs. Do not build a release directly from the moving branches.

```text
mkdir -p $HOME/yocto/rdkb-bpi-nosrc-vcpe-0902-clean
cd $HOME/yocto/rdkb-bpi-nosrc-vcpe-0902-clean

# must precede setup-environment: MACHINE is resolved from conf/machine here
git clone --branch codex/0902-clean \
  git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git

# Bootstrap from the exact manifest-repository revision used by 0902, then
# select the release lock carried by this repository.
repo init -u https://code.rdkcentral.com/r/manifests \
  -b a4637a8cadb68e34dedba6e8a5afd9432cdc3a05 \
  -m rdkb-bpi-nosrc.xml
cp meta-cmf-bananapi-vcpe/doc/build/rdkb-bpi-nosrc-0902.xml \
  .repo/manifests/rdkb-bpi-nosrc-0902.xml
repo init -m rdkb-bpi-nosrc-0902.xml
repo sync -j$(nproc) --no-clone-bundle

MACHINE=qemux86bpibroadband BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpibroadband
bitbake rdk-generic-broadband-image

cd ..

MACHINE=qemux86bpiap BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpiap
bitbake rdk-generic-ap-extender-image
```

Verify the source lock before building:

```sh
repo manifest -r -o /tmp/actual.xml
diff -u meta-cmf-bananapi-vcpe/doc/build/rdkb-bpi-nosrc-0902.xml \
  /tmp/actual.xml
```

Only comments and insignificant whitespace should differ. To create a future
release lock, deliberately initialize and synchronize the chosen upstream
manifest branch, run `repo manifest -r`, review every changed project revision,
and add the reviewed output under a new release name. Never overwrite the 0902
lock.

The controller WebUI Go server is intentionally carried in
`unified-wifi-mesh/em-cli.tar.gz` because the stock CLI recipe cannot fetch its
modules in this build. When an EasyMesh patch changes `src/rdkb-cli/main.go`,
first compile `unified-wifi-mesh`, rebuild the checked-in helper from that
workdir, and then build the image again:

```sh
bitbake unified-wifi-mesh -c compile
../meta-cmf-bananapi-vcpe/gen/rebuild-em-cli-artifact.sh \
  "$PWD/tmp/work/core2-32-rdk-linux/unified-wifi-mesh/1.0-r0"
bitbake rdk-generic-broadband-image
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
