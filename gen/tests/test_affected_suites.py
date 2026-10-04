"""affected-suites.py: what a change needs (the lab VM's step, the suite sections)."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "affected_suites", Path(__file__).resolve().parent / "affected-suites.py")
affected = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(affected)


def test_documents_need_nothing():
    result = affected.plan(["docs/guides/build.md", "README.md", "gen/medium/docs/x.md"])
    assert result["step"] == "none"
    assert result["sections"] == []


def test_the_optimizer_is_an_update_and_its_rooms():
    result = affected.plan(["gen/optimizer/optimizer/policy.py"])
    assert result["step"] == "update"
    assert {"static", "rooms", "rf-actions"} <= set(result["sections"])
    assert "browser" not in result["sections"]


def test_the_medium_daemon_is_an_update_and_the_rf_sections():
    result = affected.plan(["gen/medium/wmediumd/patches/0040-x.patch"])
    assert result["step"] == "update"
    assert {"live", "rooms", "rf", "rf-actions"} <= set(result["sections"])


def test_the_vm_stages_need_a_build():
    assert affected.plan(["gen/vm/scripts/40-deploy-easymesh.sh"])["step"] == "build"
    assert affected.plan(["gen/vm/lxd/build.sh"])["step"] == "build"


def test_the_topology_page_comes_with_the_controller_image():
    result = affected.plan(["gen/medium/topology-ui/index.html"])
    assert result["step"] == "images"
    assert {"webui", "browser"} <= set(result["sections"])


def test_recipes_rebuild_the_images_and_run_everything():
    result = affected.plan(["recipes-ccsp/onewifi/onewifi.bbappend"])
    assert result["step"] == "images"
    assert result["sections"] == affected.SECTIONS


def test_guest_services_are_an_update():
    result = affected.plan(["gen/vm/scripts/guest/easymesh-lab-runtime"])
    assert result["step"] == "update"
    assert "live" in result["sections"]


def test_an_unknown_path_runs_everything_and_the_highest_step_wins():
    result = affected.plan(["docs/a.md", "something/new.bin", "gen/tests/x.sh"])
    assert result["step"] == "build"
    assert result["sections"] == affected.SECTIONS


def test_static_runs_for_any_code_change():
    assert "static" in affected.plan(["gen/rooms/rooms.py"])["sections"]


def test_the_soak_is_never_chosen():
    every = [p for p, _, _ in affected.RULES] + ["unknown/path"]
    assert "soak" not in affected.plan(every)["sections"]
