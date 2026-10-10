"""A band's VAP subdoc from the co-located EasyMesh agent leaves out the VAPs the agent does not
manage (libwebconfig 0015), and OneWifi keeps the VAPs a band's subdoc leaves out as they are
(OneWifi 0042): after a OneWifi restart the agent's subdoc could carry its stale copy of an lnf
onboarding VAP, which OneWifi applied over the VAP as configured in the meantime.

Each patch's own added lines are compiled into a model: 0042's case in OneWifi's set-data
handler fills the decoded data from the current configuration of every VAP of the band's radio
before the subdoc is decoded; 0015's per-thread exclusion set, filled by the translator, and the
lines it adds to encode_multivap_subdoc's loop, in a model of that loop that keeps its final
branch: a VAP no branch encodes, a nameless one included, fails the whole encode. An earlier
0015 left a VAP out by blanking its name, which that branch rejects: the gateway's 5 GHz band
subdoc failed to encode on every M2 (rdk-1010, image 23, 10 October)."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ONEWIFI = ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi/0042-band-vap-subdoc-keeps-the-vaps-it-leaves-out.patch"
WEBCONFIG = ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig/0015-easymesh-band-subdoc-leaves-out-unmanaged-vaps.patch"
compiler = pytest.mark.skipif(shutil.which("cc") is None, reason="C compiler required")


def added(patch):
    return "\n".join(line[1:] for line in patch.read_text().splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


def by_file(patch):
    """{path: [hunks' added lines, one list per hunk]} of a patch."""
    files, current, hunk = {}, None, None
    for line in patch.read_text().splitlines():
        if line.startswith("+++ b/"):
            current = files.setdefault(line[6:], [])
        elif line.startswith("@@") and current is not None:
            hunk = []
            current.append(hunk)
        elif hunk is not None and line.startswith("+") and not line.startswith("+++"):
            hunk.append(line[1:])
    return files


def run(tmp_path, program, *flags):
    source = tmp_path / "model.c"
    source.write_text(program)
    built = subprocess.run(["cc", "-std=gnu11", "-Wall", "-Werror", *flags, "-o", str(tmp_path / "model"),
                            str(source)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    return subprocess.run([str(tmp_path / "model")], capture_output=True, text=True)


def test_both_patches_are_well_formed_and_in_their_series():
    for patch in (ONEWIFI, WEBCONFIG):
        subprocess.run(["git", "apply", "--numstat", str(patch)], check=True, capture_output=True)
    onewifi = (ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi.bbappend").read_text()
    assert 'WIFI_BAND_SUBDOC_PATCH := "${THISDIR}/${BPN}/0042-band-vap-subdoc-keeps-the-vaps-it-leaves-out.patch"' in onewifi
    assert onewifi.index("d.getVar('WIFI_BACKHAUL_RECONNECT_PATCH')") < onewifi.index("d.getVar('WIFI_BAND_SUBDOC_PATCH')")
    assert 'do_patch[file-checksums] += "${WIFI_BAND_SUBDOC_PATCH}:True"' in onewifi
    webconfig = (ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig.bbappend").read_text()
    # after 0030 and 0040: written against the source with them
    assert re.search(r"file://0040-[^ \"]+ file://0015-easymesh-band-subdoc-leaves-out-unmanaged-vaps.patch[ \"]",
                     webconfig)


def test_no_structure_changes_its_layout_and_no_name_is_blanked():
    for path, hunks in by_file(WEBCONFIG).items():
        lines = [line for hunk in hunks for line in hunk]
        if path.endswith(".h"):
            assert not any(re.search(r"\b(struct|typedef|union|enum)\b", line) for line in lines), path
        assert not any("vap_name[0] = " in line for line in lines), path


@compiler
def test_a_bands_subdoc_decodes_every_vap_of_its_radio_from_the_current_configuration(tmp_path):
    case = added(ONEWIFI)
    case = case[case.index("case webconfig_subdoc_type_vap_24G:"):case.rindex("break;\n        }") + len("break;\n        }")]
    program = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_NUM_RADIOS 3
#define MAX_NUM_VAP_PER_RADIO 8
typedef char wifi_vap_name_t[64];
typedef enum { webconfig_subdoc_type_private, webconfig_subdoc_type_vap_24G, webconfig_subdoc_type_vap_5G,
               webconfig_subdoc_type_vap_6G } webconfig_subdoc_type_t;
typedef struct { wifi_vap_name_t vap_name; } rdk_wifi_vap_info_t;
typedef struct { unsigned int num_vaps; rdk_wifi_vap_info_t rdk_vap_array[MAX_NUM_VAP_PER_RADIO]; } rdk_wifi_vap_map_t;
typedef struct { rdk_wifi_vap_map_t vaps; } rdk_wifi_radio_t;
typedef struct { rdk_wifi_radio_t radio_config[MAX_NUM_RADIOS]; } wifi_mgr_t;
static wifi_mgr_t manager;
static unsigned int getNumberRadios(void) { return 3; }
static unsigned int names_for(webconfig_subdoc_type_t subdoc_type, wifi_vap_name_t *out)
{
    wifi_mgr_t *mgr = &manager;
    /* as handle_webconfig_event declares them */
    wifi_vap_name_t vap_names[MAX_NUM_RADIOS * MAX_NUM_VAP_PER_RADIO];
    unsigned int num_ssid = 0;
    switch (subdoc_type) {
    @CASE@
    default:
        break;
    }
    memcpy(out, vap_names, sizeof(vap_names));
    return num_ssid;
}
int main(void)
{
    const char *band5[] = {"private_ssid_5g", "iot_ssid_5g", "", "lnf_radius_5g", "mesh_backhaul_5g"};
    manager.radio_config[1].vaps.num_vaps = 5;
    for (int i = 0; i < 5; i++)
        snprintf(manager.radio_config[1].vaps.rdk_vap_array[i].vap_name, 64, "%s", band5[i]);
    wifi_vap_name_t names[MAX_NUM_RADIOS * MAX_NUM_VAP_PER_RADIO];
    unsigned int n = names_for(webconfig_subdoc_type_vap_5G, names);
    /* every named VAP of radio 1, the lnf onboarding VAP among them */
    assert(n == 4 && !strcmp(names[3], "mesh_backhaul_5g") && !strcmp(names[2], "lnf_radius_5g"));
    assert(names_for(webconfig_subdoc_type_vap_24G, names) == 0);
    puts("ok");
    return 0;
}
'''.replace("@CASE@", case)
    result = run(tmp_path, program)
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr


@compiler
def test_the_encoder_leaves_out_only_the_excluded_vaps_on_their_thread(tmp_path):
    multivap = by_file(WEBCONFIG)["source/webconfig/wifi_webconfig_multivap.c"]
    exclusions = "\n".join(multivap[0])          # the set and its functions
    loop_check = "\n".join(multivap[1])          # the lines at the top of the encoder's loop
    assert "webconfig_encode_vap_excluded(vap->vap_index)" in loop_check and "continue;" in loop_check
    program = r'''
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define MAX_NUM_RADIOS 3
#define MAX_NUM_VAP_PER_RADIO 8
#define WIFI_WEBCONFIG 0
typedef struct { char vap_name[64]; unsigned int vap_index; } wifi_vap_info_t;
static char logged[512];
#define wifi_util_info_print(module, fmt, ...) \
    snprintf(logged + strlen(logged), sizeof(logged) - strlen(logged), fmt, __VA_ARGS__)
@EXCLUSIONS@
/* encode_multivap_subdoc's loop: 0015's lines first; then a branch per VAP type, each for a
 * named VAP only; the final branch fails the whole encode ("Unknown vap") */
static int encode(wifi_vap_info_t *vaps, unsigned int num_vaps, char *out, size_t size)
{
    wifi_vap_info_t *vap;
    out[0] = 0;
    for (unsigned int j = 0; j < num_vaps; j++) {
        vap = &vaps[j];
@LOOP_CHECK@
        if (strlen(vap->vap_name) != 0) {
            strncat(out, vap->vap_name, size - strlen(out) - 2);
            strcat(out, ",");
        } else {
            return -1;
        }
    }
    return 0;
}
static wifi_vap_info_t band5[] = {{"private_ssid_5g", 1}, {"iot_ssid_5g", 3}, {"lnf_radius_5g", 11},
                                  {"mesh_backhaul_5g", 13}};
static void *other_thread(void *arg)
{
    char out[256];
    (void)arg;
    /* the main thread's exclusion does not reach this thread's encode */
    assert(encode(band5, 4, out, sizeof(out)) == 0 && strstr(out, "lnf_radius_5g") != NULL);
    return NULL;
}
int main(void)
{
    char out[256];
    webconfig_encode_clear_exclusions();
    assert(webconfig_encode_exclude_vap(11));                /* the translator: no row, no M2 */
    assert(encode(band5, 4, out, sizeof(out)) == 0);
    assert(!strcmp(out, "private_ssid_5g,iot_ssid_5g,mesh_backhaul_5g,"));
    assert(strstr(logged, "left out of the subdoc: lnf_radius_5g") != NULL);
    pthread_t thread;
    assert(pthread_create(&thread, NULL, other_thread, NULL) == 0 && pthread_join(thread, NULL) == 0);
    /* the agent's copy is untouched, and after the clear the next encode has it again */
    assert(!strcmp(band5[2].vap_name, "lnf_radius_5g"));
    webconfig_encode_clear_exclusions();
    assert(encode(band5, 4, out, sizeof(out)) == 0 && strstr(out, "lnf_radius_5g") != NULL);
    /* a nameless VAP no one excluded still fails the encode, as before */
    wifi_vap_info_t broken[] = {{"private_ssid_5g", 1}, {"", 12}};
    assert(encode(broken, 2, out, sizeof(out)) == -1);
    /* an index outside the set: refused, so the translator can say so */
    assert(!webconfig_encode_exclude_vap(MAX_NUM_RADIOS * MAX_NUM_VAP_PER_RADIO));
    assert(!webconfig_encode_vap_excluded(MAX_NUM_RADIOS * MAX_NUM_VAP_PER_RADIO));
    puts("ok");
    return 0;
}
'''.replace("@EXCLUSIONS@", exclusions).replace("@LOOP_CHECK@", loop_check)
    result = run(tmp_path, program, "-pthread")
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr


def test_the_translator_excludes_and_every_easymesh_encode_clears_before_and_after():
    patch = WEBCONFIG.read_text()
    translator = "\n".join(line for hunk in by_file(WEBCONFIG)["source/webconfig/wifi_easymesh_translator.c"]
                           for line in hunk)
    assert re.search(r"webconfig_encode_clear_exclusions\(\);\n\s+webconfig_error_t encoded = "
                     r"webconfig_encode\(config, &webconfig_easymesh_data, type\);\n"
                     r"\s+webconfig_encode_clear_exclusions\(\);\n\s+if \(encoded != webconfig_error_none\)",
                     translator)
    # in the no-row, no-M2 branch, then on to the next VAP (the context line after it)
    assert re.search(r"^\+\s+if \(!webconfig_encode_exclude_vap\(vap->vap_index\)\) \{", patch, re.M)
    assert re.search(r"^\+\s+\}\n \s+continue;", patch, re.M)
