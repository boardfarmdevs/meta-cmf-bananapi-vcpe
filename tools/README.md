# tools

## em_cmd.c — a driver for `em_ctrl`

The image ships `libemcli.so` and the narrow `steer_drv`/`steer.sh` steering
adapter, but no general interactive RDKB-CLI executable. This is a small
developer driver that talks to `em_ctrl` over its TLS socket through that
library. Normal steering tests should use `steer.sh`; use this tool for native
command diagnosis.

`src/cli/main.c` upstream is an interactive `readline` REPL and, more
importantly, calls an `init()` that the **shipped** library — built from
`src/rdkb-cli`, not `src/cli` — does not export. This uses the API that is
actually exported: `set_remote_addr()` then `exec()`.

### Build

Cross-compile against the recipe's sysroot on the build host:

```sh
W=<build-dir>/tmp/work/core2-32-rdk-linux/unified-wifi-mesh/1.0-r0
CC=$W/recipe-sysroot-native/usr/bin/i686-rdk-linux/i686-rdk-linux-gcc
S=$W/recipe-sysroot

$CC --sysroot=$S -O2 \
  -I$W/git/inc -I$W/git/src/util -I$W/git/src/utils -I$W/git/src/util_crypto \
  -I$S/usr/include -I$S/usr/include/ccsp -I$S/usr/include/breakpad \
  -I$S/usr/include/rbus -I$S/usr/include/dbus-1.0 -I$S/usr/lib/dbus-1.0/include \
  -o em_cmd em_cmd.c -L$W/image/usr/lib -lemcli

lxc file push em_cmd bpibroadband/usr/bin/em_cmd
lxc exec bpibroadband -- chmod 755 /usr/bin/em_cmd
```

Proper integration would add `bin_PROGRAMS` to a `Makefile.am` so bitbake builds
it in-tree; this is the quick path.

### Use

```sh
em_cmd list                       # enumerate what em_ctrl accepts
em_cmd "get_bss OneWifiMesh"      # network/BSS tree
em_cmd "get_ssid OneWifiMesh"     # the NetworkSSIDList the controller holds
em_cmd "<command>" <json-file>    # a command with a payload
```

Commands take the network ID (`OneWifiMesh`) as an argument -- without it they
return `Error_Invalid_Input`. The vocabulary:

```text
none reset ap_cap dev_test cfg_renew vap_config get_network get_device
remove_device get_radio set_radio get_ssid set_ssid get_channel set_channel
scan_channel scan_result get_bss get_sta steer_sta disassoc_sta btm_sta
start_dpp client_cap get_policy
```

`steer_sta`, `btm_sta` and `disassoc_sta` are the roaming levers.

### Known broken: `cfg_renew`

`cfg_renew` blocks and never returns. `em_ctrl` logs the radio MAC it parsed as

```text
analyze_config_renew:2186: Radio: 43:66:67:52:65:6e
```

`43 66 67 52 65 6e` is ASCII `"CfgRen"` -- the first six bytes of the filename
`CfgRenew.json`, which the command loads by convention. The renew path is
reading a filename as a radio MAC. Supplying a corrected payload with real
device and radio MACs and the 5 GHz operating class (115 rather than the
sample's 2.4 GHz 81) does not help -- it produces no new log entry at all.

Note also that the shipped `/usr/ccsp/EasyMesh/*.json` are upstream **samples**
with foreign identities (`ControllerID: da:3a:dd:09:ea:c0`, network `"Private"`),
not templates for this deployment.
