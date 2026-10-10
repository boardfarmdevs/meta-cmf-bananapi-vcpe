"""ccsp-one-wifi.bbappend's hand-applied patches: applied to the files as fetched, every time the
same. A do_patch run again on a tree it patched before (its inputs changed, no rm_work: rev140,
9 October, image 23 stopped at "reconciling hwsim live association snapshots", neither
applicable nor already applied) ends with the same tree, the files a patch creates and old
.orig/.rej included; a later patch rewriting an earlier one's line is no obstacle; a *_PATCH
variable naming another layer's patch restores nothing.

restore_layer_patched_files and the head of do_patch_append (apply_layer_patch, then the
restore), the bbappend's own text, run here on a git checkout."""
from pathlib import Path
import re
import shutil
import subprocess
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
BBAPPEND = (ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi.bbappend").read_text()
BODY = re.search(r"^python do_patch_append\(\) \{\n(.*?)^\}\n", BBAPPEND, re.S | re.M).group(1)
needs_tools = pytest.mark.skipif(not (shutil.which("git") and shutil.which("patch")),
                                 reason="git and patch required")

ORIGINAL = "int em_assoc(void)\n{\n    int live = A;\n    return live;\n}\n"
FIRST = """--- a/source/apps/em/wifi_em.c
+++ b/source/apps/em/wifi_em.c
@@ -1,5 +1,5 @@
 int em_assoc(void)
 {
-    int live = A;
+    int live = A + B;
     return live;
 }
"""
SECOND = """--- a/source/apps/em/wifi_em.c
+++ b/source/apps/em/wifi_em.c
@@ -1,5 +1,5 @@
 int em_assoc(void)
 {
-    int live = A + B;
+    int live = reconcile(A + B);
     return live;
 }
"""
CREATES = """--- /dev/null
+++ b/include/wifi_em_util_threshold.h
@@ -0,0 +1 @@
+#define THRESHOLD 1
"""
# a patch that alone touches its files, dropped from the layer later (0043's webconfig files,
# 10 October: image 26, without it, built on image 25's tree, kept its changes)
DROPPED = """--- a/source/webconfig/wifi_decoder.c
+++ b/source/webconfig/wifi_decoder.c
@@ -1 +1,2 @@
 decode
+decode TransmitPowerdBm
--- /dev/null
+++ b/include/wifi_dropped.h
@@ -0,0 +1 @@
+#define DROPPED 1
"""
FOREIGN = """--- a/source/core/wifi_ctrl.c
+++ b/source/core/wifi_ctrl.c
@@ -1 +1 @@
-x
+y
"""


class Fatal(Exception):
    pass


def checkout(tmp_path):
    git = tmp_path / "git"
    (git / "source/apps/em").mkdir(parents=True)
    (git / "source/core").mkdir(parents=True)
    (git / "include").mkdir()
    (git / "source/apps/em/wifi_em.c").write_text(ORIGINAL)
    (git / "source/core/wifi_ctrl.c").write_text("x\n")
    (git / "source/webconfig").mkdir(parents=True)
    (git / "source/webconfig/wifi_decoder.c").write_text("decode\n")
    for command in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "f"]):
        subprocess.run(["git", "-C", str(git), *command], check=True)
    return git


def layer(tmp_path):
    here = tmp_path / "layer/recipes-ccsp/ccsp/ccsp-one-wifi"
    here.mkdir(parents=True)
    patches = {"FIRST_PATCH": FIRST, "SECOND_PATCH": SECOND, "CREATES_PATCH": CREATES}
    for name, text in patches.items():
        (here / f"{name.lower()}.patch").write_text(text)
    # another layer's, named by a *_PATCH variable the recipe's datastore also holds
    other = tmp_path / "other-layer"
    other.mkdir()
    (other / "foreign.patch").write_text(FOREIGN)
    variables = {name: str(here / f"{name.lower()}.patch") for name in patches}
    variables["OTHER_LAYER_PATCH"] = str(other / "foreign.patch")
    variables["LAYER_ONEWIFI_PATCH_DIR"] = str(here)
    (tmp_path / "work").mkdir(exist_ok=True)
    variables["WORKDIR"] = str(tmp_path / "work")
    return variables


def datastore(git, variables):
    class D:
        def getVar(self, name):
            return str(git) if name == "S" else variables.get(name)

        def keys(self):
            return ["S", *variables]
    return D()


def do_patch_head(d, restore=True):
    """The body up to its first patch, apply_layer_patch returned; without the restore when
    restore is False (the bbappend before it)."""
    helper = re.search(r"^def restore_layer_patched_files\(.*?(?=^\S)", BBAPPEND, re.S | re.M).group()
    head = BODY[:BODY.index("    restore_layer_patched_files(d, s)\n") + len("    restore_layer_patched_files(d, s)\n")]
    if not restore:
        head = head.replace("    restore_layer_patched_files(d, s)\n", "")

    def fatal(message):
        raise Fatal(message)

    notes = []
    namespace = {"bb": types.SimpleNamespace(note=notes.append, fatal=fatal), "d": d}
    exec(helper, namespace)
    exec("def head():\n" + head + "    return apply_layer_patch\n", namespace)
    return namespace["head"](), notes


def run(d, variables, restore=True):
    apply, notes = do_patch_head(d, restore)
    for name in ("FIRST_PATCH", "SECOND_PATCH", "CREATES_PATCH"):
        with open(variables[name], "rb") as stream:
            apply(stream)
    return notes


def tree(git):
    return {str(p.relative_to(git)): p.read_text() for p in sorted(git.rglob("*"))
            if p.is_file() and ".git" not in p.relative_to(git).parts}


@needs_tools
def test_a_second_run_on_a_patched_tree_ends_with_the_same_tree(tmp_path):
    git = checkout(tmp_path)
    variables = layer(tmp_path)
    d = datastore(git, variables)
    notes = run(d, variables)
    once = tree(git)
    assert "reconcile(A + B)" in once["source/apps/em/wifi_em.c"]
    assert once["include/wifi_em_util_threshold.h"] == "#define THRESHOLD 1\n"
    assert notes == ["meta-cmf-bananapi-vcpe: 2 files the layer patches touch restored to the "
                     "fetched revision"]
    # do_patch again on that tree, a leftover of an earlier failed run there too
    (git / "source/apps/em/wifi_em.c.rej").write_text("old")
    run(d, variables)
    assert tree(git) == once


@needs_tools
def test_without_the_restore_the_second_run_stops(tmp_path):
    """The failure the restore removes: FIRST is neither applicable (SECOND rewrote its line)
    nor already applied (its reverse finds A + B gone)."""
    git = checkout(tmp_path)
    variables = layer(tmp_path)
    d = datastore(git, variables)
    run(d, variables, restore=False)
    with pytest.raises(Fatal, match="neither cleanly applicable nor already applied"):
        run(d, variables, restore=False)


@needs_tools
def test_a_dropped_patchs_files_are_restored_at_the_next_run(tmp_path):
    """A build with one more patch, then one without it on the same tree: the files only that
    patch touched are back as fetched, the file it created gone; the others as patched."""
    git = checkout(tmp_path)
    variables = layer(tmp_path)
    dropped = Path(variables["LAYER_ONEWIFI_PATCH_DIR"]) / "dropped_patch.patch"
    dropped.write_text(DROPPED)
    with_it = dict(variables, DROPPED_PATCH=str(dropped))
    apply, _ = do_patch_head(datastore(git, with_it))
    for name in ("FIRST_PATCH", "SECOND_PATCH", "CREATES_PATCH", "DROPPED_PATCH"):
        with open(with_it[name], "rb") as stream:
            apply(stream)
    assert "TransmitPowerdBm" in (git / "source/webconfig/wifi_decoder.c").read_text()
    assert (git / "include/wifi_dropped.h").exists()
    dropped.unlink()    # the next branch's layer has no such patch
    notes = run(datastore(git, variables), variables)
    assert (git / "source/webconfig/wifi_decoder.c").read_text() == "decode\n"
    assert not (git / "include/wifi_dropped.h").exists()
    assert "reconcile(A + B)" in (git / "source/apps/em/wifi_em.c").read_text()
    assert notes[-1] == "meta-cmf-bananapi-vcpe: 2 files only a dropped layer patch had changed restored too"


@needs_tools
def test_another_layers_patch_restores_nothing(tmp_path):
    git = checkout(tmp_path)
    variables = layer(tmp_path)
    (git / "source/core/wifi_ctrl.c").write_text("changed by someone else\n")
    run(datastore(git, variables), variables)
    assert (git / "source/core/wifi_ctrl.c").read_text() == "changed by someone else\n"


def test_the_restore_comes_before_every_patch():
    restore = BODY.index("    restore_layer_patched_files(d, s)\n")
    first_patch = re.search(r"(?<!def )apply_layer_patch\(", BODY).start()
    assert restore < first_patch
    assert BODY.count("restore_layer_patched_files(") == 1
    assert 'LAYER_ONEWIFI_PATCH_DIR := "${THISDIR}/${BPN}"' in BBAPPEND
    # every patch the body applies is one the restore sees: read through a *_PATCH variable
    opened = re.findall(r"open\(d\.getVar\('(\w+)'\)", BODY)
    looped = re.findall(r"'(\w+_PATCH)'", BODY)
    assert opened and looped and all(name.endswith("_PATCH") for name in opened)
    assert BODY.count("open(") == len(opened) + BODY.count("open(d.getVar(variable)") + 2  # + wifi_em.c, wifi_stats_assoc_client.c
    for name in set(opened + looped):
        assert re.search(rf'^{name} := "\$\{{THISDIR\}}/\$\{{BPN\}}/\S+\.patch"', BBAPPEND, re.M), name
