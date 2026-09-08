from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'steer.sh'


class SteeringWaitTests(unittest.TestCase):
    def test_association_wait_returns_without_sleep_when_already_connected(self):
        source = SCRIPT.read_text()
        function = source.split('wait_target_association() {', 1)[1].split('\n}\n', 1)[0]
        program = '''
target_bssid=02:00:00:00:01:01
client=wlan-client-001
iw() { printf 'Connected to 02:00:00:00:01:01 (on wlan0)\n'; }
sleep() { return 97; }
export -f iw sleep
lxc_exec_bounded() { shift 3; bash "${@:2}"; }
wait_target_association() {''' + function + '''
}
wait_target_association 4
'''
        result = subprocess.run(['bash', '-c', program], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
