import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / "vm" / "virtualbox"
RUBY = os.environ.get("VAGRANT_RUBY") or shutil.which("ruby")
RUBY_HARNESS = '''
require "json"
class Configuration
  attr_reader :calls
  def initialize
    @calls = []
  end
  def method_missing(name, *arguments, **keywords, &block)
    @calls << [name.to_s, arguments, keywords]
    block.call(self) if block
    self
  end
end
module Vagrant
  def self.configure(version)
    configuration = Configuration.new
    yield configuration
    puts JSON.generate(configuration.calls)
  end
end
load ARGV.fetch(0)
'''


@unittest.skipUnless(RUBY, "Ruby is needed for Vagrantfile contract tests")
class VagrantConfigurationTest(unittest.TestCase):
    def evaluate(self, environment=None, release=None, checksum="a" * 64):
        with tempfile.TemporaryDirectory(prefix="rdk vagrant test ") as directory:
            folder = Path(directory)
            shutil.copy(ROOT / "Vagrantfile", folder)
            manifest = release or {"stack": "rdkeasymesh", "provider": "virtualbox",
                                   "release_id": "0908", "box": "rdk.box"}
            (folder / "release.json").write_text(json.dumps(manifest))
            (folder / "rdk.box").touch()
            (folder / "rdk.box.sha256").write_text(checksum + "  rdk.box\n")
            selected = {key: value for key, value in os.environ.items()
                        if not key.startswith(("EASYMESH_", "WMEDIUMD_"))}
            selected.update(environment or {})
            return subprocess.run([RUBY, "-e", RUBY_HARNESS, str(folder / "Vagrantfile")],
                                  env=selected, capture_output=True, text=True, timeout=15)

    def test_local_box_ports_and_resources(self):
        result = self.evaluate()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = json.loads(result.stdout)
        forwards = [arguments for method, positional, arguments in calls if method == "network"]
        self.assertEqual({entry["host"] for entry in forwards}, {18889, 18890, 18891, 18892, 18893})
        self.assertTrue(all(entry["host_ip"] == "127.0.0.1" and entry["auto_correct"] is False for entry in forwards))
        self.assertIn(["cpus=", [6], {}], calls)
        self.assertIn(["memory=", [8192], {}], calls)
        self.assertIn(["insert_key=", [True], {}], calls)
        self.assertIn(["check_guest_additions=", [False], {}], calls)
        urls = [arguments[0] for method, arguments, keywords in calls if method == "box_url="]
        self.assertEqual(len(urls), 1)
        self.assertTrue(urls[0].endswith("/rdk.box"))
        self.assertIn("rdk vagrant test ", urls[0])
        self.assertIn(["box_download_checksum=", ["a" * 64], {}], calls)
        self.assertIn(["box=", ["rdkeasymesh/0908-virtualbox-aaaaaaaaaaaa"], {}], calls)

    def test_override_port(self):
        result = self.evaluate({"EASYMESH_ROOM_DEMO_PORT": "28891"})
        self.assertEqual(result.returncode, 0, result.stderr)
        forwards = [keywords for method, arguments, keywords in json.loads(result.stdout) if method == "network"]
        self.assertIn(28891, [entry["host"] for entry in forwards])

    def test_0909_box_identity_comes_from_release_manifest(self):
        result = self.evaluate(release={"stack": "rdkeasymesh", "provider": "virtualbox",
                                        "release_id": "0909", "box": "rdk.box"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(["box=", ["rdkeasymesh/0909-virtualbox-aaaaaaaaaaaa"], {}],
                      json.loads(result.stdout))

    def test_invalid_configuration_is_rejected(self):
        for environment in ({"EASYMESH_CPUS": "2"}, {"EASYMESH_MEMORY_MB": "4096"},
                            {"EASYMESH_ROOM_DEMO_PORT": "18889"}, {"EASYMESH_WEBUI_PORT": "65536"}):
            with self.subTest(environment=environment):
                self.assertNotEqual(self.evaluate(environment).returncode, 0)
        self.assertNotEqual(self.evaluate(checksum="invalid").returncode, 0)
        self.assertNotEqual(self.evaluate(release={"stack": "prplmesh", "provider": "virtualbox"}).returncode, 0)


class VirtualBoxSourceTest(unittest.TestCase):
    def test_guest_unmount_retries_transient_busy_without_forcing(self):
        builder = (ROOT / "build.sh").read_text()
        function = "unmount_guest() {" + builder.split("unmount_guest() {", 1)[1].split("\ncleanup() {", 1)[0]
        harness = '''
set -euo pipefail
root=/copied
declare -A mounted=([/copied/boot/efi]=1 [/copied/boot]=1 [/copied]=1)
root_attempts=0
mountpoint() { test "${mounted[$2]:-0}" = 1; }
sudo() {
    test "$1" = umount
    if [ "$2" = "$root" ]; then
        root_attempts=$((root_attempts + 1))
        [ "$root_attempts" -ne 1 ] || return 1
    fi
    mounted[$2]=0
}
sleep() { :; }
'''
        result = subprocess.run(["bash", "-c", harness + function + '\nunmount_guest\ntest "$root_attempts" = 2\n'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("umount -l", function)
        self.assertNotIn("umount -f", function)

    def test_builder_is_not_excluded_by_gitignore(self):
        result = subprocess.run(["git", "check-ignore", "--no-index", "build.sh"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_bounded_room_selection_does_not_start_a_lab(self):
        script = ROOT.parents[1] / "tests/room-world-switch-smoke.py"
        help_result = subprocess.run([sys.executable, str(script), "--help"],
                                     capture_output=True, text=True, check=True, timeout=10)
        self.assertIn("--skip-presence", help_result.stdout)
        self.assertIn("--world WORLD", help_result.stdout)
        invalid = subprocess.run([sys.executable, str(script), "--yes-act", "--world", "default",
                                  "--all-worlds", "--output", "/unused.json"],
                                 capture_output=True, text=True, timeout=10)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("choose --all-worlds or --world", invalid.stderr)

    def test_shell_syntax(self):
        for script in [ROOT / "build.sh", ROOT / "prepare-guest.sh", ROOT / "package-release.sh", ROOT / "guest/easymesh-vagrant-up"]:
            with self.subTest(script=script.name):
                subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True)

    def test_guest_reuses_offline_profile_and_no_downloads(self):
        script = (ROOT / "guest/easymesh-vagrant-up").read_text()
        self.assertIn("easymesh-select-thin-profile 20", script)
        self.assertIn(".final_instances == 25", script)
        self.assertIn("systemctl is-failed --quiet easymesh-thin-firstboot.service", script)
        self.assertNotIn("apt-get", script)
        self.assertNotIn("git clone", script)
        self.assertNotIn("curl -k", script)

    def test_transport_and_key_isolation(self):
        ssh = (ROOT / "guest/sshd.conf").read_text()
        self.assertIn("PasswordAuthentication no", ssh)
        self.assertIn("PermitRootLogin no", ssh)
        self.assertNotIn("PRIVATE KEY", (ROOT / "guest/vagrant.pub").read_text())
        script = (ROOT / "prepare-guest.sh").read_text()
        self.assertIn('mountpoint -q "$root"', script)
        self.assertIn('thin-profile-selection.required', script)
        self.assertIn('cloud-init.disabled', script)
        self.assertIn('mask lxd-agent.service', script)
        self.assertNotIn('mask snap.lxd', script)
        self.assertIn('server.crt', script)
        self.assertIn('ssh_host_*', script)

    def test_host_keys_do_not_order_a_regular_service_before_sockets(self):
        unit = (ROOT / "guest/easymesh-vbox-identity.service").read_text()
        self.assertIn("Before=ssh.service", unit)
        self.assertNotIn("ssh.socket", unit)
        self.assertNotIn("sockets.target", unit)

    def test_windows_wrapper_excludes_vm_state(self):
        script = (ROOT / "package-release.sh").read_text()
        self.assertIn('"${files[@]}" SHA256SUMS', script)
        self.assertNotIn('tar -cf "$destination/$name.tar" .', script)
        self.assertIn("adapter-source.tar.gz", script)

    @unittest.skipUnless(shutil.which("jq"), "jq is needed for release packaging")
    def test_release_wrapper_round_trip(self):
        with tempfile.TemporaryDirectory(prefix="rdk package test ") as directory:
            parent = Path(directory)
            release = parent / "input with spaces"
            release.mkdir()
            box_name = "rdkeasymesh-0908-virtualbox.box"
            (release / box_name).write_bytes(b"test provider artifact")
            (release / (box_name + ".sha256")).write_text(
                hashlib.sha256((release / box_name).read_bytes()).hexdigest() + "  " + box_name + "\n")
            (release / "release.json").write_text(json.dumps({
                "stack": "rdkeasymesh", "provider": "virtualbox", "release_id": "0908", "box": box_name}))
            for filename in ("Vagrantfile", "README.md", "source-release.json", "adapter-files.sha256",
                             "adapter-source.tar.gz", "package-release.sh"):
                (release / filename).write_text("fixture\n")
            files = sorted(release.iterdir())
            (release / "SHA256SUMS").write_text("".join(
                hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in files))
            (release / ".vagrant").mkdir()
            (release / ".vagrant/private_key").write_text("must not ship")
            (release / "build.secret").write_text("must not ship")
            arguments = ["bash", str(ROOT / "package-release.sh"), str(release), str(parent)]
            subprocess.run(arguments, check=True, capture_output=True, timeout=30)
            archive = parent / "rdkeasymesh-0908-virtualbox.tar"
            with tarfile.open(archive) as packaged:
                names = packaged.getnames()
                self.assertTrue(all(name.startswith("rdkeasymesh-0908-virtualbox/") for name in names))
                self.assertFalse(any(".vagrant" in name or "build.secret" in name for name in names))
                self.assertEqual(packaged.extractfile("rdkeasymesh-0908-virtualbox/" + box_name).read(),
                                 b"test provider artifact")
            self.assertEqual((parent / (archive.name + ".sha256")).read_text().split()[0],
                             hashlib.sha256(archive.read_bytes()).hexdigest())
            repeated = subprocess.run(arguments, capture_output=True, timeout=30)
            self.assertNotEqual(repeated.returncode, 0)


if __name__ == "__main__":
    unittest.main()
