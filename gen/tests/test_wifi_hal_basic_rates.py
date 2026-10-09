"""rdk-wifi-hal 0046: the Banana Pi platform programs its BSS's basic rates into the kernel
(NL80211_CMD_SET_BSS), so mac80211 sends beacons and broadcasts at the lowest basic rate and
not at 1 Mbit/s; the SET_BSS link ID only for an MLD AP, which nl80211 requires.

The patch's own lines (the platform's flags, the link ID) are compiled into a model of
wifi_drv_set_ap's SET_BSS step against a model of nl80211's link ID rule."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "recipes-ccsp/hal/rdk-wifi-hal/0046-banana-pi-program-the-bss-basic-rates.patch"
BBAPPEND = (ROOT / "recipes-ccsp/hal/rdk-wifi-hal.bbappend").read_text()


def added(text):
    return "\n".join(line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++"))


def code(text):    # without its comment lines
    return "\n".join(line for line in text.splitlines() if not re.match(r"\s*(/\*|\*(\s|/|$))", line))


def hunk(path):
    return re.search(rf"^\+\+\+ b/{re.escape(path)}\n(.*?)(?=^--- |^-- \n|\Z)", PATCH.read_text(),
                     re.MULTILINE | re.DOTALL).group(1)


def test_the_patch_is_well_formed_and_applied_from_the_git_directory_after_the_platform_patches():
    subprocess.run(["git", "apply", "--numstat", str(PATCH)], check=True, capture_output=True)
    assert 'PLATFORM_BASIC_RATES_PATCH := "${THISDIR}/${BPN}/0046-banana-pi-program-the-bss-basic-rates.patch"' \
        in BBAPPEND
    # above S (git/src): from the git directory, as the other platform patches, and after them
    block = BBAPPEND[BBAPPEND.index("PLATFORM_BASIC_RATES_PATCH :="):]
    assert "os.path.dirname(d.getVar('S'))" in block and "'patch', '-p1', '-N', '-d'" in block
    assert BBAPPEND.index("PLATFORM_HWSIM_CURRENT_SIGNAL_PATCH'), 'rb')") < BBAPPEND.index(
        "PLATFORM_BASIC_RATES_PATCH'), 'rb')")
    assert 'do_patch[file-checksums] += "${PLATFORM_BASIC_RATES_PATCH}:True"' in BBAPPEND


def model(flags_line, link_line):
    return r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define NL80211_DRV_LINK_ID_NA (-1)
enum { PLATFORM_FLAGS_SET_BSS = 0x1, PLATFORM_FLAGS_CONTROL_PORT_FRAME = 0x1 << 1,
       PLATFORM_FLAGS_STA_INACTIVITY_TIMER = 0x1 << 4 };
struct wpa_driver_ap_params { const int *basic_rates; bool mld_ap; unsigned char mld_link_id; int isolate; };
/* the kernel: nl80211 refuses a link ID on a non-MLD interface; mac80211 keeps the basic rates */
struct kernel { bool mld; int basic_rates_len; unsigned char basic_rates[8]; int isolate; };
static int nl80211_set_bss(struct kernel *k, const int *basic_rates, int isolate, int link_id)
{
    if (!k->mld && link_id != NL80211_DRV_LINK_ID_NA)
        return -22;
    k->isolate = isolate;
    for (k->basic_rates_len = 0; basic_rates && basic_rates[k->basic_rates_len] >= 0; k->basic_rates_len++)
        k->basic_rates[k->basic_rates_len] = basic_rates[k->basic_rates_len] / 5;
    return 0;
}
static int set_bss_param(struct kernel *k, int isolate) { k->isolate = isolate; return 0; }
static int platform_flags_init(int *flags)
{
@FLAGS@
    return 0;
}
static int set_ap(struct kernel *k, struct wpa_driver_ap_params *params)
{
    int flags, link_id = -1;
    platform_flags_init(&flags);
@LINK@
    if (flags & PLATFORM_FLAGS_SET_BSS) {
        if (nl80211_set_bss(k, params->basic_rates, params->isolate, link_id) != 0)
            return -1;
    } else {
        set_bss_param(k, params->isolate);
    }
    return 0;
}
int main(void)
{
    static const int basic_g[] = {60, 120, 240, -1};
    struct wpa_driver_ap_params bss = {basic_g, false, 0, 1}, mld = {basic_g, true, 1, 0};
    struct kernel plain = {0}, multi = {.mld = true};
    /* a BSS that is not an MLD: started, its basic rates (500 kbit/s units) in the kernel */
    assert(set_ap(&plain, &bss) == 0);
    assert(plain.basic_rates_len == 3 && plain.basic_rates[0] == 12 && plain.basic_rates[2] == 48);
    assert(plain.isolate == 1);
    /* an MLD AP's link */
    assert(set_ap(&multi, &mld) == 0 && multi.basic_rates_len == 3);
    return 0;
}
'''.replace("@FLAGS@", flags_line).replace("@LINK@", link_line)


def run(tmp_path, program):
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("C compiler required for the SET_BSS model")
    source = tmp_path / "set_bss.c"
    source.write_text(program)
    subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", "-o", str(tmp_path / "set_bss"), str(source)],
                   check=True, capture_output=True)
    return subprocess.run([str(tmp_path / "set_bss")], capture_output=True).returncode


def test_banana_pi_programs_the_basic_rates_and_the_link_id_is_an_mld_aps_only(tmp_path):
    flags = code(added(hunk("platform/banana-pi/platform.c")))
    link = "\n".join(line for line in added(hunk("src/wifi_hal_nl80211.c")).splitlines()
                     if line.strip().startswith("link_id"))
    assert "PLATFORM_FLAGS_SET_BSS" in flags and link.strip()
    assert run(tmp_path, model(flags, link)) == 0


def test_the_old_code_left_the_kernel_without_basic_rates_or_failed_the_ap(tmp_path):
    old_flags = "    *flags = PLATFORM_FLAGS_STA_INACTIVITY_TIMER | PLATFORM_FLAGS_CONTROL_PORT_FRAME;"
    new_link = [line for line in added(hunk("src/wifi_hal_nl80211.c")).splitlines()
                if line.strip().startswith("link_id")][0]
    # without the flag: no basic rates in the kernel (mac80211 at 1 Mbit/s)
    assert run(tmp_path, model(old_flags, new_link)) != 0
    # with the flag but the link ID of every BSS: a non-MLD AP's start refused (EINVAL)
    new_flags = code(added(hunk("platform/banana-pi/platform.c")))
    assert run(tmp_path, model(new_flags, "    link_id = params->mld_link_id;")) != 0
