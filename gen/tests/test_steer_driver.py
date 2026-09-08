from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest


STUB = r'''
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <stddef.h>
int set_remote_addr(unsigned int address, unsigned int port, bool valid) { return 0; }
void *get_network_tree_by_file(const char *file) { return (void *)1; }
void *exec(char *command, size_t size, void *node) {
    return strcmp(getenv("TEST_STATUS"), "null") == 0 ? NULL : (void *)2;
}
void *get_network_tree_by_key(void *node, const char *key) { return node; }
char *get_node_scalar_value(void *node) { return strdup(getenv("TEST_STATUS")); }
void free_node_value(char *value) { free(value); }
void free_network_tree(void *node) {}
'''


@unittest.skipUnless(shutil.which("cc"), "C compiler unavailable")
class SteeringDriverTests(unittest.TestCase):
    def test_native_status_controls_exit_code_and_is_machine_readable(self):
        root = Path(__file__).resolve().parents[2]
        source = root / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh/steer_drv.c"
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "steer_drv"
            subprocess.run(["cc", str(source), "-x", "c", "-", "-o", str(binary)], input=STUB,
                           text=True, capture_output=True, check=True)
            for status in ("Success", "Error_Prev_Cmd_In_Progress", "Error_Not_Ready", "null"):
                with self.subTest(status=status):
                    result = subprocess.run([str(binary), "steer_sta OneWifiMesh", "payload.json"],
                                            env={**os.environ, "TEST_STATUS": status},
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0 if status == "Success" else 1)
                    if status != "null":
                        self.assertEqual(result.stdout.strip(), "steer_drv_status=" + status)


if __name__ == "__main__":
    unittest.main()
