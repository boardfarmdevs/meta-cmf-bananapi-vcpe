# Build

| role | MACHINE | image |
|---|---|---|
| controller (standard bpi) | `qemux86bpibroadband` | `rdk-generic-broadband-image` |
| AP extender (bpi-ap) | `qemux86bpiap` | `rdk-generic-ap-extender-image` |

One tree serves both machines, with a build directory per MACHINE.

```text
mkdir -p $HOME/yocto/rdkb-bpi-nosrc-vcpe-$(date +%m%d)
cd $HOME/yocto/rdkb-bpi-nosrc-vcpe-$(date +%m%d)

# must precede setup-environment: MACHINE is resolved from conf/machine here
git clone --branch codex/0824-clean \
  git@github.com:robvogelaar/meta-cmf-bananapi-vcpe.git

repo init -u https://code.rdkcentral.com/r/manifests -b kirkstone -m rdkb-bpi-nosrc.xml
repo sync -j$(nproc) --no-clone-bundle

MACHINE=qemux86bpibroadband BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpibroadband
bitbake rdk-generic-broadband-image

cd ..

MACHINE=qemux86bpiap BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpiap
bitbake rdk-generic-ap-extender-image
```

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
hash recorded in `doc/easymesh/patch-set.md`; a successful image build alone
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
