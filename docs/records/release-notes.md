# Release information

[Documents](../README.md)

A lab VM is built from a clean checkout of this repository at a commit, with the
medium, the optimizer and EMOSA at the commits it pins, and with the controller
and extender images the easymesh-labs `manifest.json` pins, each with the commit
it was built from. The VM's bundle carries this note, and its guest checkout is this
repository at that commit (`build.sh check` compares it with the host's).

[Current state](../project/current-state.md) is the single source for the
last-tested VM, its qualification and its open limitations. A source build, a
built VM and a qualified VM are distinct states: only a passed suite qualifies a
VM. For older releases, use Git history; do not use an old acceptance report as
the current operating manual.
