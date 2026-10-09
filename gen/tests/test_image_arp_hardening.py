"""The RDK images answer ARP only on the interface that holds the address asked for
(recipes-core/images/vcpe-arp-hardening.inc, required by the gateway's and the extenders' image
bbappends): no ARP flux from the 1905 stacks' address-less veth peers or the addressed bridges,
whatever rp_filter is set to."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "recipes-core/images"
INC = (IMAGES / "vcpe-arp-hardening.inc").read_text()


def test_the_include_writes_arp_ignore_1_and_arp_announce_2_for_all_and_default():
    body = re.search(r"^vcpe_arp_hardening\(\) \{.*?^\}", INC, re.MULTILINE | re.DOTALL).group()
    assert "${IMAGE_ROOTFS}${sysconfdir}/sysctl.d/60-vcpe-arp.conf" in body
    settings = dict(re.findall(r"^(net\.ipv4\.conf\.\w+\.\w+) = (\d+)$", body, re.MULTILINE))
    assert settings == {
        "net.ipv4.conf.all.arp_ignore": "1", "net.ipv4.conf.default.arp_ignore": "1",
        "net.ipv4.conf.all.arp_announce": "2", "net.ipv4.conf.default.arp_announce": "2",
    }


def test_it_runs_at_rootfs_time():
    assert re.search(r'^ROOTFS_POSTPROCESS_COMMAND_append = " vcpe_arp_hardening;"$', INC, re.MULTILINE)


def test_both_images_take_it():
    for image in ("rdk-generic-broadband-image", "rdk-generic-ap-extender-image"):
        text = (IMAGES / f"{image}.bbappend").read_text()
        assert "require recipes-core/images/vcpe-arp-hardening.inc" in text.splitlines(), image
