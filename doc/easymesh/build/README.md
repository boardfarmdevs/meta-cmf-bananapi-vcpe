# Build the EasyMesh lab

This is the single entry point for building the RDK EasyMesh lab on a new
Ubuntu 22.04 x86-64 machine. Build the two BPI container images first, then
build a separate LXD VM from those images, then choose an appropriate test tier.
The VM build does not invoke Yocto and the image build does not create a VM.

## What is built

| Stage | Output | Start here |
| --- | --- | --- |
| BPI images | controller and extender `*.rootfs.lxc.tar.bz2` | [BPI images](#bpi-images) |
| Lab VM | one named LXD VM, matching LXD pool and named ports | [VM build](vm.md) |
| Build-time tests | static, image and VM baseline tiers | [Test tiers](tests.md) |
| Ready-VM qualification | full static, browser, live, room and soak suite | [Test guide](../test/README.md) |

The permanent lab capacity is 100 clients and five physical mesh containers
(six displayed roles). Rooms select the active client subset; they do not resize
the appliance.

## Host prerequisites

Use a supported Ubuntu 22.04 x86-64 host with hardware virtualization enabled,
at least 32 GiB RAM and at least 300 GiB available disk for the Yocto tree,
downloads, sstate and images. Source acquisition needs Internet access and the
credentials required by RDK Central. LXD VM creation additionally needs `/dev/kvm`.

```sh
sudo apt update
sudo apt install -y gawk wget curl git diffstat unzip texinfo gcc build-essential \
  chrpath socat cpio python3 python3-pip python3-pexpect xz-utils debianutils \
  iputils-ping python3-git python3-jinja2 libegl1-mesa libsdl1.2-dev python3-subunit \
  mesa-common-dev zstd liblz4-tool python-is-python3 gnupg locales strace qemu-kvm snapd
mkdir -p "$HOME/bin" "$HOME/hosttools/bin" "$HOME/oe/downloads" "$HOME/oe/sstate-cache"
curl -o "$HOME/bin/repo" https://storage.googleapis.com/git-repo-downloads/repo
chmod +x "$HOME/bin/repo"
export PATH="$HOME/hosttools/bin:$HOME/bin:$PATH"
```

The Kirkstone-era build requires GNU tar without the newer `openat2` behavior.
Build and place GNU tar 1.34 ahead of `/usr/bin` before creating a build directory:

```sh
mkdir -p "$HOME/hosttools/src" && cd "$HOME/hosttools/src"
wget https://ftp.gnu.org/gnu/tar/tar-1.34.tar.gz
tar -xzf tar-1.34.tar.gz && cd tar-1.34
./configure --prefix="$HOME/hosttools/tar134" --without-selinux
make -j"$(nproc)" && make install
ln -sf ../tar134/bin/tar "$HOME/hosttools/bin/tar"
command -v tar
```

Verify that the selected tar does not use `openat2` before the first BitBake
directory is created:

```sh
strace -f -e trace=openat2 -o /tmp/easymesh-tar.strace \
  tar -xf "$HOME/hosttools/src/tar-1.34.tar.gz" -C /tmp
test "$(grep -c openat2 /tmp/easymesh-tar.strace)" = 0
```

If the host package cannot provide `lz4c`, stage it without changing the system
installation:

```sh
mkdir -p "$HOME/hosttools/debs" && cd "$HOME/hosttools/debs"
apt-get download lz4
dpkg-deb -x lz4_*.deb "$HOME/hosttools/root"
ln -sf ../root/usr/bin/lz4c "$HOME/hosttools/bin/lz4c"
command -v lz4c
```
Do not put build-specific exports in a shell profile: each script below derives
working defaults from its checkout and accepts only optional overrides.

## BPI images

Create a workspace and clone the layer. The current branch in that clone is the
layer source; the single checked-in [manifest.xml](manifest.xml) pins every
upstream project used by the image build.

```sh
mkdir -p "$HOME/yocto/easymesh-bpi"
git clone https://github.com/boardfarmdevs/meta-cmf-bananapi-vcpe.git \
  "$HOME/yocto/easymesh-bpi/meta-cmf-bananapi-vcpe"
cd "$HOME/yocto/easymesh-bpi/meta-cmf-bananapi-vcpe"
export PATH="$HOME/hosttools/bin:$HOME/bin:$PATH"
bash doc/easymesh/build/scripts/bootstrap-sources.sh
bash doc/easymesh/build/scripts/build-images.sh both
```

The image helper defaults to the checkout's parent as its workspace,
`$HOME/oe/downloads`, `$HOME/oe/sstate-cache`, and `$(nproc)`. Override only
when needed, for example `TREE=/work/bpi BUILD_THREADS=16 build-images.sh both`.
It verifies the pinned manifest before it builds, keeps separate build
directories for the two machines, and writes checksums/logs under
`$TREE/build-evidence/`.

Verify both role records before proceeding:

```sh
cd "$HOME/yocto/easymesh-bpi"
for role in controller extender; do
  record=$(cat "build-evidence/latest-$role")
  cat "$record/exit-code" "$record/images.sha256"
done
```

## Rebuild from a Yocto shell

Use a fresh terminal for one role at a time. These commands source the same RDK
environment as the helper and retain the shared downloads, sstate, and thread
settings in `clean-build.conf`.

Controller image:

```sh
cd "$HOME/yocto/easymesh-bpi"
workspace=$PWD
export PATH="$HOME/hosttools/bin:$HOME/bin:$PATH"
MACHINE=qemux86bpibroadband BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpibroadband
bitbake -R "$workspace/clean-build.conf" rdk-generic-broadband-image
```

Extender image:

```sh
cd "$HOME/yocto/easymesh-bpi"
workspace=$PWD
export PATH="$HOME/hosttools/bin:$HOME/bin:$PATH"
MACHINE=qemux86bpiap BPI_IMG_TYPE=nand \
  source meta-cmf-bananapi/setup-environment-refboard-rdkb build-qemux86bpiap
bitbake -R "$workspace/clean-build.conf" rdk-generic-ap-extender-image
```

The `em-cli.tar.gz` artifact is not a third user-facing build target. It is a
checked-in recipe input used only when an intentional em-cli source change has
been made; its rebuild helper lives under `gen/`, and its ownership contract is
in the platform reference.

## Next steps

Build a named VM from the two verified images: [VM build](vm.md).
Then select the smallest appropriate validation level: [test tiers](tests.md).
After the VM baseline passes, use the [ready-VM test suite](../test/README.md).
For installed-lab operation rather than construction, use the
[operations guide](../guide/operations.md).
