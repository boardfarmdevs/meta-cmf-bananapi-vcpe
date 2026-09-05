from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "gen/vm/lxd/observability"
GUIDE = ROOT / "doc/easymesh/reference/lxd-ui-and-monitoring.md"


@pytest.fixture(scope="module")
def dashboard():
    return json.loads((BUNDLE / "grafana/dashboards/lxd-containers.json").read_text())


@pytest.fixture(scope="module")
def compose():
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is required for configuration validation")
    version = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, timeout=20
    )
    if version.returncode:
        pytest.skip("Docker Compose v2 is not installed")
    environment = os.environ.copy()
    for variable in ("PROMETHEUS_IMAGE", "GRAFANA_IMAGE", "GRAFANA_PUBLIC_URL"):
        environment.pop(variable, None)
    result = subprocess.run(
        ["docker", "compose", "-f", str(BUNDLE / "compose.yaml"), "config", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("script", ("setup.sh", "disable.sh"))
def test_shell_syntax(script):
    subprocess.run(["bash", "-n", str(BUNDLE / script)], check=True)


def test_monitoring_is_unprivileged_and_loopback_only(compose):
    assert compose["name"] == "easymesh-observability"
    assert set(compose["services"]) == {"prometheus", "grafana"}
    for name, service in compose["services"].items():
        assert service["network_mode"] == "host"
        assert not service.get("ports")
        assert not service.get("privileged", False)
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["user"] == ("65534:65534" if name == "prometheus" else "472:472")
        assert int(service["mem_limit"]) == 512 * 1024 * 1024
        assert service["cpus"] == 0.5
        assert ":latest" not in service["image"]
        for volume in service["volumes"]:
            assert not volume["source"].endswith(".sock")
            if volume["type"] == "bind":
                assert volume["read_only"] is True
    assert "--web.listen-address=127.0.0.1:9090" in compose["services"]["prometheus"]["command"]
    environment = compose["services"]["grafana"]["environment"]
    assert environment["GF_SERVER_HTTP_ADDR"] == "127.0.0.1"
    assert environment["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert environment["GF_USERS_ALLOW_SIGN_UP"] == "false"
    assert "GF_SECURITY_ADMIN_PASSWORD" not in environment
    assert environment["GF_SECURITY_ADMIN_PASSWORD__FILE"] == "/run/secrets/grafana-admin-password"


def test_dashboard_filters_and_datasource_are_consistent(dashboard):
    assert dashboard["uid"] == "easymesh-lxd"
    assert dashboard["editable"] is False
    assert dashboard["refresh"] == "30s"
    variables = dashboard["templating"]["list"]
    assert [variable["name"] for variable in variables] == ["lab", "project", "name"]
    for variable in variables:
        assert variable["includeAll"] and variable["multi"]
        assert variable["allValue"] == ".*"
        assert variable["datasource"]["uid"] == "lxd-prometheus"
        assert 'type="container"' in variable["query"]["query"]
    panels = dashboard["panels"]
    assert len({panel["id"] for panel in panels}) == len(panels)
    for panel in panels:
        assert panel["datasource"]["uid"] == "lxd-prometheus"
        for target in panel["targets"]:
            expression = target["expr"]
            assert 'job="lxd"' in expression
            assert 'lab=~"$lab"' in expression
            if "up{" not in expression:
                for selector in ('type="container"', 'project=~"$project"', 'name=~"$name"'):
                    assert selector in expression
            if "rate(" in expression or "increase(" in expression:
                assert "[$__rate_interval]" in expression
    datasource = (BUNDLE / "grafana/provisioning/datasources/prometheus.yml").read_text()
    assert "uid: lxd-prometheus" in datasource
    assert "timeInterval: 30s" in datasource


def test_scrape_uses_verified_metrics_only_credentials():
    configuration = (BUNDLE / "prometheus.yml").read_text()
    for required in (
        "scrape_interval: 30s", "scheme: https", "metrics_path: /1.0/metrics",
        "targets: [127.0.0.1:8444]", 'lab: "@LAB_LABEL@"',
        "ca_file: /etc/prometheus/tls/server.crt",
        "cert_file: /etc/prometheus/tls/metrics.crt",
        "key_file: /etc/prometheus/tls/metrics.key",
        "server_name: 127.0.0.1", "insecure_skip_verify: false",
    ):
        assert required in configuration
    setup = (BUNDLE / "setup.sh").read_text()
    assert "--type=metrics" in setup
    assert "config set core.metrics_authentication true" in setup
    assert "openssl rand -hex 24" in setup
    assert not list(BUNDLE.rglob("*.key"))
    assert not list(BUNDLE.rglob("*.crt"))
    assert not (BUNDLE / ".env").exists()


def test_memory_panel_uses_available_cgroup_v2_metrics(dashboard):
    panel = next(panel for panel in dashboard["panels"] if panel["id"] == 4)
    expression = panel["targets"][0]["expr"]
    assert expression.startswith("lxd_memory_MemTotal_bytes{")
    assert " - lxd_memory_MemFree_bytes{" in expression
    assert "RSS_bytes" not in expression
    assert "including cache" in panel["title"]


@pytest.mark.parametrize("document", (GUIDE, BUNDLE / "README.md"))
def test_reference_links_resolve(document):
    for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
        if not target.startswith(("https://", "http://", "#")):
            assert (document.parent / target.split("#", 1)[0]).exists(), target
