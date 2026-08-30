# Repo mirror

Optional. A local `repo` mirror makes creating a new build tree much faster and
lets you re-sync without hitting the servers again. It is not required -- the
plain `repo init` / `repo sync` in [../build](../build) works on its own.

## create repo mirror (once)

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

## update repo mirror

```text
cd $HOME/yocto/mirror/rdkb-bpi-nosrc
repo sync -j$(nproc) --no-clone-bundle --no-tags

```

## create new repo from repo mirror

```text

mkdir -p $HOME/yocto/rdkb-bpi-nosrc-vcpe-$(date +%m%d)
cd $HOME/yocto/rdkb-bpi-nosrc-vcpe-$(date +%m%d)


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

Then continue with [../build](../build), skipping its `repo init` / `repo sync`
step -- the tree already exists.
