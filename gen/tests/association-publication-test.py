from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(sys.argv[1]) / 'source/core'
source = (root / 'wifi_ctrl_webconfig.c').read_text()
start = source.index('int webconfig_publish_pending_associations(')
helper = source[start:source.index('\nint webconfig_send_full_associate_status(', start)]
header = (root / 'wifi_ctrl.h').read_text()
assert 'int webconfig_publish_pending_associations(wifi_ctrl_t *ctrl);' in header
loop = (root / 'wifi_ctrl.c').read_text()
start = loop.index('void ctrl_queue_loop(')
loop = loop[start:loop.index('clock_gettime(CLOCK_MONOTONIC, &ctrl->last_signalled_time)', start)]
assert loop.index('apps_mgr_event(') < loop.index('destroy_wifi_event(') < loop.index('webconfig_publish_pending_associations(ctrl);')
analyzer = source[source.index('int webconfig_analyze_pending_states('):]
assert 'case ctrl_webconfig_state_associated_clients_cfg_rsp_pending:\n            return webconfig_publish_pending_associations(ctrl);' in analyzer
program = r'''
#include <assert.h>
typedef int webconfig_subdoc_type_t;
typedef struct { unsigned int webconfig_state; int apps_mgr; } wifi_ctrl_t;
enum { RETURN_OK, RETURN_ERR, webconfig_subdoc_type_associated_clients,
       wifi_event_type_webconfig, wifi_event_webconfig_set_status };
enum { ctrl_webconfig_state_associated_clients_cfg_rsp_pending = 2, other_pending = 4 };
static int publishes, analytics, fail;
static int webconfig_send_associate_status(wifi_ctrl_t *ctrl) {
    publishes++;
    if (fail) return RETURN_ERR;
    ctrl->webconfig_state &= ~ctrl_webconfig_state_associated_clients_cfg_rsp_pending;
    return RETURN_OK;
}
static void apps_mgr_analytics_event(int *manager, int event, int status, int *type) {
    assert(manager && event == wifi_event_type_webconfig && status == wifi_event_webconfig_set_status);
    assert(*type == webconfig_subdoc_type_associated_clients);
    analytics++;
}
''' + helper + r'''
int main(void) {
    wifi_ctrl_t ctrl = {other_pending, 0};
    assert(webconfig_publish_pending_associations(&ctrl) == RETURN_OK);
    assert(publishes == 0 && analytics == 0 && ctrl.webconfig_state == other_pending);
    ctrl.webconfig_state |= ctrl_webconfig_state_associated_clients_cfg_rsp_pending;
    fail = 1;
    assert(webconfig_publish_pending_associations(&ctrl) == RETURN_ERR);
    assert(publishes == 1 && analytics == 0 && ctrl.webconfig_state == (other_pending | 2));
    fail = 0;
    assert(webconfig_publish_pending_associations(&ctrl) == RETURN_OK);
    assert(publishes == 2 && analytics == 1 && ctrl.webconfig_state == other_pending);
    assert(webconfig_publish_pending_associations(&ctrl) == RETURN_OK);
    assert(publishes == 2 && analytics == 1);
}
'''
with tempfile.TemporaryDirectory(prefix='association-publication-') as directory:
    executable = Path(directory) / 'test'
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-x', 'c', '-', '-o', str(executable)],
                   input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True)
print('PASS: association events publish immediately, preserve other pending work and retry failed publication')
