"""A radio's transmit power reading in dBm travels beside its TransmitPower, TR-181's percentage
(OneWifi 0043, in libwebconfig's series too, and 0044): OneWifi's EM app stored the HAL's reading
(dBm) in the percentage, so Device.WiFi.Radio.{i}.TransmitPower read 20, 30 or 33 on radios
configured at 100 and the next radio configuration set that as a percentage; the EasyMesh
translator reported the percentage as the operating class's transmit power in dBm.

0043's own added lines are compiled into a model of the two processes: OneWifi, which reads the
HAL and sends the reading in the radio subdoc, and the co-located agent, which receives it and
reports it to EasyMesh. No structure changes its layout: a binary built against the headers
before the patches still agrees with them."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi"
WEBCONFIG = PATCHES / "0043-webconfig-radio-transmit-power-reading-in-dbm.patch"
EM_APP = PATCHES / "0044-em-app-keeps-the-radio-transmit-power-percentage.patch"
compiler = pytest.mark.skipif(shutil.which("cc") is None, reason="C compiler required")


def by_file(patch):
    """{path: (added lines, removed lines)} of a patch."""
    files, current = {}, None
    for line in patch.read_text().splitlines():
        if line.startswith("+++ b/"):
            current = files.setdefault(line[6:], ([], []))
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            current[0].append(line[1:])
        elif current is not None and line.startswith("-") and not line.startswith("---"):
            current[1].append(line[1:])
    return files


def test_both_patches_are_well_formed_and_in_their_series():
    for patch in (WEBCONFIG, EM_APP):
        subprocess.run(["git", "apply", "--numstat", str(patch)], check=True, capture_output=True)
    onewifi = (ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi.bbappend").read_text()
    for name, patch in (("WIFI_TX_POWER_DBM_PATCH", WEBCONFIG), ("WIFI_EM_TX_POWER_PERCENT_PATCH", EM_APP)):
        assert f'{name} := "${{THISDIR}}/${{BPN}}/{patch.name}"' in onewifi
        assert f'do_patch[file-checksums] += "${{{name}}}:True"' in onewifi
    # after 0042, 0043 before the EM app's use of it
    assert (onewifi.index("d.getVar('WIFI_BAND_SUBDOC_PATCH')")
            < onewifi.index("d.getVar('WIFI_TX_POWER_DBM_PATCH')")
            < onewifi.index("d.getVar('WIFI_EM_TX_POWER_PERCENT_PATCH')"))
    # the library OneWifi and the agent load is libwebconfig's: 0043 in its series, last
    webconfig = (ROOT / "recipes-ccsp/ccsp/ccsp-one-wifi-libwebconfig.bbappend").read_text()
    assert re.search(r"file://0015-[^ \"]+ file://0043-webconfig-radio-transmit-power-reading-in-dbm.patch\"",
                     webconfig)
    assert "${THISDIR}/ccsp-one-wifi" in webconfig.splitlines()[0]


def test_no_structure_changes_its_layout():
    for patch in (WEBCONFIG, EM_APP):
        for path, (added, _) in by_file(patch).items():
            if path.endswith(".h"):
                assert not any(re.search(r"\b(struct|typedef|union|enum)\b", line) for line in added), path
    assert set(by_file(WEBCONFIG)) == {"include/wifi_webconfig.h", "source/webconfig/wifi_decoder.c",
                                       "source/webconfig/wifi_easymesh_translator.c",
                                       "source/webconfig/wifi_encoder.c", "source/webconfig/wifi_webconfig.c"}


def test_the_em_app_no_longer_writes_the_reading_into_the_percentage():
    added, removed = by_file(EM_APP)["source/apps/em/wifi_em.c"]
    assert any("oper.transmitPower = (UINT)curr_txpower" in line for line in removed)
    assert any("curr_txpower = 100;" in line for line in removed)
    assert not any("transmitPower" in line and "=" in line for line in added)
    assert any("webconfig_set_radio_tx_power_dbm(i, (int)curr_txpower, true);" in line for line in added)


@compiler
@pytest.mark.parametrize("process", ["onewifi", "agent"])
def test_the_reading_from_onewifi_to_the_agents_easymesh_report(tmp_path, process):
    files = by_file(WEBCONFIG)
    prototypes = "\n".join(files["include/wifi_webconfig.h"][0])
    table = "\n".join(files["source/webconfig/wifi_webconfig.c"][0])
    encode = "\n".join(files["source/webconfig/wifi_encoder.c"][0])
    decode = "\n".join(files["source/webconfig/wifi_decoder.c"][0])
    translated = files["source/webconfig/wifi_easymesh_translator.c"][0]
    half = len(translated) // 2
    assert translated[:half] == translated[half:]    # both translators, the same lines
    translate = "\n".join(translated[:half])
    program = r'''
#include <assert.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define MAX_NUM_RADIOS 3
typedef struct cJSON { double valuedouble; int is_number; } cJSON;
typedef struct { struct { unsigned int radio_index; } vaps; } rdk_wifi_radio_t;
typedef struct { int tx_power; } em_op_class_info_t;
static int emitted_count;
static const char *emitted_name;
static double emitted_value;
static cJSON *incoming;
static void cJSON_AddNumberToObject(cJSON *object, const char *name, double value)
{
    (void)object; emitted_count++; emitted_name = name; emitted_value = value;
}
static cJSON *cJSON_GetObjectItem(const cJSON *object, const char *name)
{
    (void)object; return strcmp(name, "TransmitPowerdBm") == 0 ? incoming : NULL;
}
static int cJSON_IsNumber(const cJSON *item) { return item != NULL && item->is_number; }
''' + prototypes + "\n" + table + r'''
static void encode(const rdk_wifi_radio_t *radio, cJSON *radio_object)
{
''' + encode + r'''
}
static void decode(const cJSON *obj_radio, rdk_wifi_radio_t *radio)
{
    const cJSON *param;
''' + decode + r'''
}
static void translate(unsigned int radio_index, em_op_class_info_t *em_op_class_info)
{
''' + translate + r'''
}
int main(int argc, char **argv)
{
    rdk_wifi_radio_t radio = { { 1 } };
    cJSON object = { 0, 0 };
    (void)argc;
    if (strcmp(argv[1], "onewifi") == 0) {
        encode(&radio, &object);                        /* no reading yet: none sent */
        assert(emitted_count == 0);
        webconfig_set_radio_tx_power_dbm(1, 30, true);  /* the EM app's HAL reading (0044) */
        encode(&radio, &object);
        assert(emitted_count == 1 && strcmp(emitted_name, "TransmitPowerdBm") == 0 && emitted_value == 30);
        cJSON copy = { 33, 1 };                         /* an agent's copy coming back */
        incoming = &copy;
        decode(&object, &radio);
        assert(webconfig_get_radio_tx_power_dbm(1, NULL) == 30);
        incoming = NULL;                                /* a subdoc without one */
        decode(&object, &radio);
        bool measured = false;
        assert(webconfig_get_radio_tx_power_dbm(1, &measured) == 30 && measured);
    } else {
        em_op_class_info_t current = { 17 };
        translate(1, &current);                         /* no reading: the class keeps its power */
        assert(current.tx_power == 17);
        cJSON reading = { 30, 1 };
        incoming = &reading;
        decode(&object, &radio);
        translate(1, &current);
        assert(current.tx_power == 30);
        encode(&radio, &object);                        /* received, never echoed back */
        assert(emitted_count == 0);
        incoming = NULL;                                /* OneWifi restarted, no reading yet */
        decode(&object, &radio);
        translate(1, &current);
        assert(current.tx_power == 30);
        webconfig_set_radio_tx_power_dbm(MAX_NUM_RADIOS, 5, true);
        assert(webconfig_get_radio_tx_power_dbm(MAX_NUM_RADIOS, NULL) == 0);
    }
    puts("ok");
    return 0;
}
'''
    source = tmp_path / "model.c"
    source.write_text(program)
    built = subprocess.run(["cc", "-std=gnu11", "-Wall", "-Werror", "-pthread", "-o", str(tmp_path / "model"),
                            str(source)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(tmp_path / "model"), process], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == "ok\n", result.stderr
