"""build.sh gives the VM's root its size when it creates the instance: LXD sizes the new volume
then, from the pool's default when none is given, and a base image published from a 96 GiB VM
does not fit a smaller default (the K8, 9 October: "Source image size exceeds specified volume
size", a 10 GiB default). Set after the init, the size came too late. (LXD 6.9 on rev150:
`lxc init --storage labs --device root,size=...` gives root its pool and size at creation.)"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
BUILD = (ROOT / "gen/vm/lxd/build.sh").read_text()


def test_the_root_size_is_an_argument_of_the_init():
    create = BUILD[BUILD.index("    phase create\n"):]
    create = create[:create.index('"${init_args[@]}" </dev/null')]
    assert 'init_args+=(--device "root,size=$disk")' in create
    # both creations take it: from the base image and from the plain image
    assert re.search(r'init_args=\(lxc init "\$base_alias" "\$name" --vm\)', create)
    assert re.search(r'init_args=\(lxc init "\$image" "\$name" --vm\)', create)
    assert create.index('init_args+=(--storage "$storage")') < create.index('init_args+=(--device "root,size=$disk")')


def test_disk_is_set_before_the_create_step():
    assert BUILD.index('disk=${EASYMESH_LXD_DISK:-') < BUILD.index("    phase create\n")
