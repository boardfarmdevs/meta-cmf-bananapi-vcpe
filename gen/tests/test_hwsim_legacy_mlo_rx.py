from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "recipes-ccsp/hal/rdk-wifi-hal/0040-hwsim-preserve-legacy-rx-interface-before-mlo-routing.patch"


@pytest.mark.parametrize("hwsim", [False, True])
@pytest.mark.parametrize("remove_guard", [False, True])
def test_legacy_multi_band_receive_keeps_registered_interface(tmp_path, hwsim, remove_guard):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for receive routing regression")
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    additions = "\n".join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
    condition = additions.replace("        } else if", "    if")
    if remove_guard:
        condition = "    if (freq != 0) {"
    program = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#define NL80211_DRV_LINK_ID_NA (-1)
struct Interface { unsigned int freq; unsigned int configured_link; bool mld_enabled; unsigned int responses; };
static struct Interface radios[] = {{2437, 255, true, 0}, {5180, 255, true, 0}, {6135, 255, true, 0}};
static int wifi_hal_get_mld_link_id(struct Interface *interface)
{
    return interface->mld_enabled && interface->configured_link <= 14
        ? (int)interface->configured_link : NL80211_DRV_LINK_ID_NA;
}
static struct Interface *dispatch(struct Interface *interface, int link_id, uint32_t freq)
{
    if (link_id != -1)
        return &radios[link_id];
CONDITION
        if (interface->mld_enabled)
            interface = &radios[0];
    }
    return interface;
}
static void receive(struct Interface *registered, unsigned int freq)
{
    struct Interface *interface = dispatch(registered, -1, freq);
    if (interface->freq == freq)
        interface->responses++;
}
int main(void)
{
    (void)wifi_hal_get_mld_link_id;
    for (unsigned int scan = 0; scan < 2; scan++)
        for (unsigned int index = 0; index < 3; index++)
            receive(&radios[index], 2437);
#ifdef HWSIM_RADIO
    assert(radios[0].responses == 2);
#else
    assert(radios[0].responses == 6);
#endif
    assert(radios[1].responses == 0 && radios[2].responses == 0);
    assert(dispatch(&radios[2], 1, 2437) == &radios[1]);
    radios[2].configured_link = 2;
    assert(dispatch(&radios[2], -1, 2437) == &radios[0]);
    assert(dispatch(&radios[2], -1, 0) == &radios[2]);
    radios[2].mld_enabled = false;
    assert(dispatch(&radios[2], -1, 2437) == &radios[2]);
    return 0;
}
'''.replace("CONDITION", condition)
    source = tmp_path / "legacy_rx.c"
    binary = tmp_path / "legacy_rx"
    source.write_text(program)
    command = [compiler, "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)]
    if hwsim:
        command.append("-DHWSIM_RADIO")
    subprocess.run(command, check=True, capture_output=True)
    result = subprocess.run([str(binary)], capture_output=True)
    assert (result.returncode != 0) == (hwsim and remove_guard)


def test_legacy_receive_guard_is_packaged_after_receive_context():
    recipe = (ROOT / "recipes-ccsp/hal/rdk-wifi-hal.bbappend").read_text()
    assert recipe.index("0039-hwsim-preserve-management-receive-context.patch") < recipe.index(PATCH.name)
