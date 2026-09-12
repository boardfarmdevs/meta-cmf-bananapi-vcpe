from pathlib import Path
import re
import subprocess
import sys
import tempfile


root = Path(sys.argv[1]) / 'source/core'
header = (root / 'wifi_ctrl.h').read_text()
source = (root / 'wifi_ctrl.c').read_text()
names = ('check_wifi_radio_sched_timeout_active_status_of_radio_index',
         'check_wifi_csa_sched_timeout_active_status_of_radio_index')
declarations = '\n'.join(re.findall(r'bool check_wifi_\w+sched\w*\([^;]+;', header))
definitions = '\n'.join(source[source.index('bool ' + name):source.index('\n}', source.index('bool ' + name)) + 2]
                        for name in names)
shared = r'''
#include <stdbool.h>
#include <assert.h>
typedef unsigned int UINT;
typedef int BOOL;
typedef struct {
    int wifi_radio_sched_handler_id[3];
    int wifi_csa_sched_handler_id[3];
} wifi_scheduler_id_t;
typedef struct { wifi_scheduler_id_t wifi_sched_id; } wifi_ctrl_t;
unsigned int getNumberRadios(void);
''' + declarations
caller = shared + r'''
int main(void) {
    wifi_ctrl_t controller = {0};
    for (int radio_index = 0; radio_index < 3; radio_index++) {
        assert(!check_wifi_radio_sched_timeout_active_status_of_radio_index(&controller, radio_index));
        assert(!check_wifi_csa_sched_timeout_active_status_of_radio_index(&controller, radio_index));
        controller.wifi_sched_id.wifi_radio_sched_handler_id[radio_index] = 7;
        controller.wifi_sched_id.wifi_csa_sched_handler_id[radio_index] = 9;
        assert(check_wifi_radio_sched_timeout_active_status_of_radio_index(&controller, radio_index));
        assert(check_wifi_csa_sched_timeout_active_status_of_radio_index(&controller, radio_index));
        controller.wifi_sched_id.wifi_radio_sched_handler_id[radio_index] = 0;
        controller.wifi_sched_id.wifi_csa_sched_handler_id[radio_index] = 0;
    }
    assert(!check_wifi_radio_sched_timeout_active_status_of_radio_index(&controller, -1));
    assert(!check_wifi_csa_sched_timeout_active_status_of_radio_index(&controller, 3));
}
'''
with tempfile.TemporaryDirectory(prefix='onewifi-radio-scheduler-') as directory:
    output = Path(directory)
    (output / 'caller.c').write_text(caller)
    (output / 'provider.c').write_text(shared + '\nunsigned int getNumberRadios(void) { return 3; }\n' + definitions)
    subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(output / 'caller.c'),
                    str(output / 'provider.c'), '-o', str(output / 'test')], check=True)
    subprocess.run([str(output / 'test')], check=True)
print('PASS: cross-translation-unit radio timer checks preserve their boolean return type')
