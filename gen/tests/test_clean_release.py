from pathlib import Path
import subprocess
import xml.etree.ElementTree as tree


ROOT = Path(__file__).resolve().parents[2]


def test_0908_retains_reviewed_upstream_revisions():
    def projects(release):
        return {project.get("path", project.get("name")): project.get("revision") for project in tree.parse(ROOT / f"doc/build/rdkb-bpi-nosrc-{release}.xml").findall("project")}

    assert projects("0908") == projects("0905")
    assert all(len(revision) == 40 for revision in projects("0908").values())


def test_clean_build_uses_workspace_local_caches_and_complete_images():
    script = ROOT / "doc/build/build-images.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    source = script.read_text()
    assert 'BUILD_DOWNLOADS:-$workspace/downloads' in source
    assert 'SSTATE_DIR:forcevariable = "$workspace/sstate-cache"' in source
    assert 'SSTATE_MIRRORS:forcevariable = ""' in source
    assert "rdk-generic-broadband-image" in source
    assert "rdk-generic-ap-extender-image" in source
    assert 'git -C "$source_root" status --porcelain' in source
    bootstrap = source.index('MACHINE="$machine" BPI_IMG_TYPE=nand source')
    assert source.index('set +o pipefail') < bootstrap
    assert source.index('set -eo pipefail', bootstrap) > bootstrap
    assert '"$record/incomplete-conf"' in source
    assert 'grep -Fq \'meta-cmf-bananapi-vcpe\' conf/bblayers.conf' in source


def test_hostap_fetch_uses_current_upstream_without_changing_revision():
    source = (ROOT / "recipes-ccsp/rdk-wifi-libhostap/rdk-wifi-libhostap_2.11.bbappend").read_text()
    assert 'SRC_URI:remove = "git://w1.fi/hostap.git;' in source
    assert 'SRC_URI:prepend = "git://git.w1.fi/hostap.git;protocol=https;branch=main;destsuffix=${S}/source/hostap-${PV};name=${PV} "' in source
    assert "git://chromium.googlesource.com/external/w1.fi/cgit/hostap;protocol=https" in source
    assert "SRCREV" not in source


def test_ieee1905_crates_use_the_registry_download_cdn():
    source = (ROOT / "recipes-ccsp/ieee1905/ieee1905-em.bbappend").read_text()
    assert 'PREMIRRORS:prepend = "https://crates.io/api/v1/crates/([^/]+)/.* ' in source
    assert r"https://static.crates.io/crates/\1/" in source
    assert "BB_STRICT_CHECKSUM" not in source


def test_virglrenderer_uses_upstream_https_without_changing_revision():
    source = (ROOT / "recipes-graphics/virglrenderer/virglrenderer_0.9.1.bbappend").read_text()
    assert 'SRC_URI:remove = "git://anongit.freedesktop.org/git/virglrenderer;branch=branch-0.9.1"' in source
    assert "git://gitlab.freedesktop.org/virgl/virglrenderer.git;protocol=https;branch=branch-0.9.1" in source
    assert "SRCREV" not in source


def test_virgin_agent_remembers_the_controller_before_first_wsc():
    patch_name = "0172-agent-remember-controller-before-first-wsc.patch"
    recipe = (ROOT / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh.bbappend").read_text()
    patch = (ROOT / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh" / patch_name).read_text()
    assert "file://" + patch_name in recipe
    remember = patch.index("+    get_data_model()->set_ctrl_al_interface_mac(hdr->src);")
    assert patch.index('printf("Received resp and validated...creating M1 msg') < remember
    assert remember < patch.index("int msg_len = create_autoconfig_wsc_m1_msg(msg, hdr->src);")


def test_room_is_installed_from_source_with_current_profiling_defaults():
    unit = (ROOT / "gen/vm/scripts/guest/easymesh-room-demo.service").read_text()
    assert "Requires=easymesh-lab.service" in unit
    assert "After=easymesh-lab.service" in unit
    assert "ConditionPathExists=!/var/lib/easymesh-lab/thin-profile-selection.required" in unit
    assert "ExecCondition=/usr/bin/grep -qx HEALTH_EXPECT_CLIENTS=20" in unit
    assert "--mode act --yes-act --profiling" in unit
    assert "--adaptive-backhaul" not in unit
    assert "WantedBy=multi-user.target easymesh-lab.service" in unit
    builder = (ROOT / "gen/vm/lxd/build.sh").read_text()
    installer = (ROOT / "gen/vm/scripts/50-runtime-service.sh").read_text()
    assert "[easymesh-room-demo.service]=gen/vm/scripts/guest/easymesh-room-demo.service" in builder
    assert '"http://$proxy_check_address:$room_port/healthz"' in builder
    assert "/home/easymesh/easymesh-assets/easymesh-room-demo.service" in installer
    assert "systemctl enable easymesh-room-demo.service" in installer


def test_thin_export_stops_room_before_native_lab():
    for name in ("easymesh-prepare-thin-package", "easymesh-package-cleanup"):
        script = (ROOT / "gen/vm/scripts/guest" / name).read_text()
        assert script.index("systemctl stop easymesh-room-demo.service") < script.index("systemctl stop easymesh-lab.service")
