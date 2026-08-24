# WNM/BTM-capable WLAN-client supplicant

Every accepted `wlan-client[-NNN]` uses the committed
`wpa_supplicant-wnm` binary. It is wpa_supplicant 2.10 built with
`CONFIG_WNM=y`, so all ten client instances can receive an 802.11v BSS
Transition Management Request, return a BTM Response and reassociate to the
requested BSS.

The former manual flow—building into one client's `/tmp` and swapping the
stock Alpine daemon—is obsolete. `gen/wlan-client.sh` now builds a reusable
`wlan-client-base` LXD image containing:

- `iw` and the stock runtime libraries;
- `/usr/local/sbin/wpa_supplicant-wnm`;
- an OpenRC hook that reconnects from `/etc/wpa.conf`; and
- the packages needed to run the committed binary.

`wlan-client.sh up` creates every station from that image. If the image alias
does not exist it is built once. `--wnm` remains an ignored compatibility
option because WNM is no longer optional.

## Verify the accepted runtime

```sh
lxc exec wlan-client -- readlink /proc/$(
  lxc exec wlan-client -- pgrep -o wpa_supplicant
)/exe
lxc exec wlan-client -- /usr/local/sbin/wpa_supplicant-wnm -v
lxc exec wlan-client -- iw dev wlan0 link
```

The executable path must be `/usr/local/sbin/wpa_supplicant-wnm`. Repeat the
check for `wlan-client-001` through `wlan-client-009` when validating a newly
built base image.

An end-to-end proof is a commanded steering test, not just the presence of the
binary:

```sh
gen/tests/steering-matrix.sh 1
```

A pass requires the Client Steering Request, source-VAP BTM transmission,
client reassociation, controller database/API convergence and traffic. See
[steering policy](../../doc/easymesh/concepts/steering-policy.md).

## Rebuild the binary

The committed binary is the reproducible runtime input:

```text
file     gen/wpa_supplicant/wpa_supplicant-wnm
SHA-256 23af2fbf6ef96731b9fda55142775e6d49430d92b09ccba6349de21e14651c46
config   gen/wpa_supplicant/wpa_supplicant-wnm.config
```

Rebuild it only when changing wpa_supplicant or its configuration:

```sh
gen/wpa_supplicant/build-wnm-supplicant.sh wlan-client
```

The build helper temporarily raises the selected client's memory limit,
downloads and verifies wpa_supplicant 2.10, compiles it with the recorded
configuration, and copies the result back to the host-side committed path.
After reviewing the binary and hash change, rebuild the reusable client image:

```sh
gen/wlan-client.sh --build-image build-image
```

Client containers have a 128 MiB runtime limit. Compilation uses more memory
and is therefore a maintainer action; normal deployment never compiles inside
a client.
