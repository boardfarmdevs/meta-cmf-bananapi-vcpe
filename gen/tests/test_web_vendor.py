import hashlib
from pathlib import Path
import re
import tarfile


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/web-vendor.tar.gz"


def test_offline_browser_bundle_has_verified_assets_and_licenses():
    assert hashlib.sha256(BUNDLE.read_bytes()).hexdigest() == "699a85cca2578c7d1563ab7e0544f934ca3b2292fef42b85022a1fca89139e08"
    with tarfile.open(BUNDLE) as archive:
        names = archive.getnames()
        assert all(name.startswith("vendor") and ".." not in Path(name).parts for name in names)
        for line in archive.extractfile("vendor/SHA256SUMS").read().decode().splitlines():
            digest, name = line.split(None, 1)
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest() == digest
        for name in ("d3-LICENSE", "chart-LICENSE.md", "animate-LICENSE", "fontawesome/LICENSE.txt"):
            assert archive.extractfile("vendor/" + name).read()
        stylesheet = archive.extractfile("vendor/fontawesome/css/all.min.css").read().decode()
        for font in re.findall(r"url\((?:['\"])?\.\./webfonts/([^)'\"]+)", stylesheet):
            assert "vendor/fontawesome/webfonts/" + font in names
        for asset in ("d3-7.9.0.min.js", "chart-3.9.1.min.js", "animate-4.1.1.min.css"):
            assert archive.extractfile("vendor/" + asset).read()
