from pathlib import Path
import re
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "recipes-ccsp/hal/rdk-wifi-hal/0039-hwsim-preserve-management-receive-context.patch"


@pytest.mark.parametrize("hwsim", [False, True])
@pytest.mark.parametrize("mutation", [None, "normal", "forwarded", "metadata"])
def test_per_bss_receive_contract(tmp_path, hwsim, mutation):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for management routing regression")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    additions = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
    blocks = re.findall(r"#ifdef HWSIM_RADIO\n.*?#endif", additions, re.DOTALL)
    assert len(blocks) == 3
    metadata, normal, forwarded = blocks
    if mutation == "normal":
        normal = ""
    elif mutation == "forwarded":
        forwarded = ""
    elif mutation == "metadata":
        metadata = ""
    program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
struct Bss { void *drv_priv; unsigned int responses; };
struct Interface { struct { struct { struct Bss hapd; } ap; } u; };
struct Event { struct { void *drv_priv; int freq; int ssi_signal; } rx_mgmt; };
static struct Event receive(struct Interface *interface, bool forwarded, int recv_freq, int sig_dbm)
{
    struct Event event = {0};
    (void)interface;
    (void)recv_freq;
    (void)sig_dbm;
    if (forwarded) {
FORWARDED
    } else {
METADATA
NORMAL
    }
    return event;
}
static void hostap_dispatch(struct Interface *interfaces, struct Event event, int directed)
{
    if (event.rx_mgmt.freq && event.rx_mgmt.freq != 2437)
        return;
    if (directed >= 0) {
        interfaces[directed].u.ap.hapd.responses++;
        return;
    }
    for (size_t index = 0; index < 3; index++) {
        struct Bss *bss = &interfaces[index].u.ap.hapd;
        if (event.rx_mgmt.drv_priv && bss->drv_priv != event.rx_mgmt.drv_priv)
            continue;
        bss->responses++;
    }
}
int main(void)
{
    struct Interface interfaces[3] = {0};
#ifdef HWSIM_RADIO
    unsigned int expected = 1;
#else
    unsigned int expected = 3;
#endif
    for (size_t index = 0; index < 3; index++)
        interfaces[index].u.ap.hapd.drv_priv = &interfaces[index];
    for (size_t forwarded = 0; forwarded < 2; forwarded++) {
        for (size_t index = 0; index < 3; index++)
            interfaces[index].u.ap.hapd.responses = 0;
        for (size_t index = 0; index < 3; index++) {
            struct Event event = receive(&interfaces[index], forwarded, 2437, -42);
            hostap_dispatch(interfaces, event, -1);
#ifdef HWSIM_RADIO
            assert(event.rx_mgmt.drv_priv == &interfaces[index]);
            if (!forwarded) {
                assert(event.rx_mgmt.freq == 2437);
                assert(event.rx_mgmt.ssi_signal == -42);
            }
#endif
        }
        for (size_t index = 0; index < 3; index++)
            assert(interfaces[index].u.ap.hapd.responses == expected);
    }
    for (size_t index = 0; index < 3; index++)
        interfaces[index].u.ap.hapd.responses = 0;
    struct Event event = receive(&interfaces[1], false, 2437, -67);
    hostap_dispatch(interfaces, event, 1);
    assert(interfaces[0].u.ap.hapd.responses == 0);
    assert(interfaces[1].u.ap.hapd.responses == 1);
    assert(interfaces[2].u.ap.hapd.responses == 0);
#ifdef HWSIM_RADIO
    event = receive(&interfaces[1], false, 5180, -53);
    hostap_dispatch(interfaces, event, -1);
    assert(interfaces[1].u.ap.hapd.responses == 1);
#endif
    return 0;
}
'''.replace("METADATA", metadata).replace("NORMAL", normal).replace("FORWARDED", forwarded)
    source_file = tmp_path / "management.c"
    binary = tmp_path / "management"
    source_file.write_text(program)
    command = [compiler, "-Wall", "-Wextra", "-Werror", str(source_file), "-o", str(binary)]
    if hwsim:
        command.append("-DHWSIM_RADIO")
    subprocess.run(command, check=True, capture_output=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert (result.returncode != 0) == (hwsim and mutation is not None)


def test_patch_preserves_sta_dispatch_and_is_enabled():
    source = PATCH.read_text()
    assert source.count("supplicant_event(&interface->wpa_s, EVENT_RX_MGMT, &event);") == 2
    assert source.count("+            event.rx_mgmt.drv_priv = interface->u.ap.hapd.drv_priv;") == 1
    assert source.count("+        event.rx_mgmt.drv_priv = interface->u.ap.hapd.drv_priv;") == 1
    recipe = ROOT / "recipes-ccsp/hal/rdk-wifi-hal.bbappend"
    assert f'file://{PATCH.name}' in recipe.read_text()
