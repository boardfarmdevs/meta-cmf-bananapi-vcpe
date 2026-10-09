"""rdk-wifi-hal.bbappend's platform patches (platform/banana-pi/platform.c, above S): applied to
the file as fetched, every time the same. A do_patch run again on a tree it patched before (a
build host without rm_work: the K8, 9 October, stopped at 0036 "previously applied") ends
with the same file; a later patch rewriting an earlier one's line is no obstacle; a platform
patch reaching outside platform/ stops the build.

bananapi_platform_patches, the bbappend's own function, runs here on a git checkout."""
from pathlib import Path
import re
import shutil
import subprocess
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
BBAPPEND = (ROOT / "recipes-ccsp/hal/rdk-wifi-hal.bbappend").read_text()
needs_tools = pytest.mark.skipif(not (shutil.which("git") and shutil.which("patch")),
                                 reason="git and patch required")

ORIGINAL = "int platform_flags_init(int *flags)\n{\n    *flags = A;\n    return 0;\n}\n"
FIRST = """--- a/platform/banana-pi/platform.c
+++ b/platform/banana-pi/platform.c
@@ -1,5 +1,5 @@
 int platform_flags_init(int *flags)
 {
-    *flags = A;
+    *flags = A | B;
     return 0;
 }
"""
SECOND = """--- a/platform/banana-pi/platform.c
+++ b/platform/banana-pi/platform.c
@@ -1,5 +1,5 @@
 int platform_flags_init(int *flags)
 {
-    *flags = A | B;
+    *flags = A | B | C;
     return 0;
 }
"""
OUTSIDE = """--- a/src/wifi_hal.c
+++ b/src/wifi_hal.c
@@ -1 +1 @@
-x
+y
"""


class Fatal(Exception):
    pass


def helper():
    text = re.search(r"^def bananapi_platform_patches\(.*?(?=^\S)", BBAPPEND, re.S | re.M).group()

    def fatal(message):
        raise Fatal(message)

    notes = []
    namespace = {"bb": types.SimpleNamespace(note=notes.append, fatal=fatal)}
    exec(text, namespace)
    return namespace["bananapi_platform_patches"], notes


def checkout(tmp_path):
    git = tmp_path / "git"
    (git / "platform/banana-pi").mkdir(parents=True)
    (git / "src").mkdir()
    (git / "platform/banana-pi/platform.c").write_text(ORIGINAL)
    (git / "src/wifi_hal.c").write_text("x\n")
    for command in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "f"]):
        subprocess.run(["git", "-C", str(git), *command], check=True)
    return git


def datastore(git, patches):
    class D:
        def getVar(self, name):
            return str(git / "src") if name == "S" else str(patches[name])
    return D()


@needs_tools
def test_a_second_run_on_a_patched_tree_ends_with_the_same_file(tmp_path):
    git = checkout(tmp_path)
    (tmp_path / "first.patch").write_text(FIRST)
    (tmp_path / "second.patch").write_text(SECOND)
    apply, notes = helper()
    d = datastore(git, {"FIRST": tmp_path / "first.patch", "SECOND": tmp_path / "second.patch"})
    apply(d, [("FIRST", "first"), ("SECOND", None)])
    once = (git / "platform/banana-pi/platform.c").read_text()
    assert "A | B | C" in once
    # do_patch again on that tree, its leftovers there too (the K8's .orig and .rej)
    (git / "platform/banana-pi/platform.c.rej").write_text("old")
    apply(d, [("FIRST", "first"), ("SECOND", None)])
    assert (git / "platform/banana-pi/platform.c").read_text() == once
    assert not (git / "platform/banana-pi/platform.c.rej").exists()
    assert not (git / "platform/banana-pi/platform.c.orig").exists()
    assert notes == ["meta-cmf-bananapi-vcpe: first"] * 2


@needs_tools
def test_a_platform_patch_outside_platform_stops_the_build(tmp_path):
    git = checkout(tmp_path)
    (tmp_path / "outside.patch").write_text(OUTSIDE)
    apply, _ = helper()
    with pytest.raises(Fatal, match="src/wifi_hal.c, outside platform/"):
        apply(datastore(git, {"OUTSIDE": tmp_path / "outside.patch"}), [("OUTSIDE", None)])
    assert (git / "src/wifi_hal.c").read_text() == "x\n"


def test_every_platform_patch_goes_through_it_in_the_series_order():
    calls = BBAPPEND[BBAPPEND.index("python do_patch_append() {\n    bananapi_platform_patches(d, ["):]
    calls = calls[:calls.index("\n}\n")]
    names = re.findall(r"\('(PLATFORM_\w+_PATCH)'", calls)
    assert names == ["PLATFORM_HWSIM_SURVEY_PATCH", "PLATFORM_CREATE_VAP_NULL_PATCH",
                     "PLATFORM_CREATE_VAP_MLD_NULL_PATCH", "PLATFORM_BACKHAUL_SSID_PATCH",
                     "PLATFORM_WDS_STA_METRICS_PATCH", "PLATFORM_HWSIM_STA_LIVENESS_PATCH",
                     "PLATFORM_HWSIM_ASSOC_OWNERSHIP_PATCH", "PLATFORM_HWSIM_CURRENT_SIGNAL_PATCH",
                     "PLATFORM_BASIC_RATES_PATCH"]
    # nothing else patches outside S on its own
    assert BBAPPEND.count("python do_patch_append()") == 1
    assert BBAPPEND.count("'patch', '-p1'") == 1
    for name in names:
        assert f'do_patch[file-checksums] += "${{{name}}}:True"' in BBAPPEND
