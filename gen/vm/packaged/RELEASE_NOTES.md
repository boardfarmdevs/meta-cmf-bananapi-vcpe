# EasyMesh lab 0828 release notes

This release replaces `easymesh-lab-0827-c461c59.box` with
`easymesh-lab-0828-cf6b5e8.box`.

## Exact provenance

| Release | Source revision | Size | SHA-256 |
| --- | --- | ---: | --- |
| 0827 | `c461c591afe8afef47d1b215fbcfbb09eb5abcb3` | 3,882,758,736 bytes | `0c3a4edb10c2bce1152116ad39d42fd53a5f55bf91b1f4cf64b533b532ef9821` |
| 0828 | `cf6b5e8923b2d75781759deee8fa7f1ae00e2175` | 4,106,818,874 bytes | `335206682b3d0b7798e5fd5e56fe6ccf7a55090d165a10b0c00bf41bca170ecc` |

The functional source delta is exactly:

```sh
git log --reverse --oneline \
  c461c591afe8afef47d1b215fbcfbb09eb5abcb3..cf6b5e8923b2d75781759deee8fa7f1ae00e2175
```

```text
cefbc4e fix(lab): stabilize client roaming and recovery
cf6b5e8 webui: stage steering cues and shape topology
```

## Changes

### Client roaming and recovery

- Candidate discovery now runs through `wpa_supplicant` with `wpa_cli`
  instead of issuing an external `iw scan`. This keeps scanning and
  reassociation in one station state machine and avoids an hwsim idle-state
  race that could discard an AP authentication response.
- The WLAN-client image exposes the supplicant control socket required by the
  deterministic steering and carousel tools.
- OneWifi no longer exports inactive historical association-cache rows as
  current clients. After an intra-agent band roam, the controller can therefore
  converge on the new BSSID instead of retaining the old BSSID indefinitely.
- The hwsim Wi-Fi HAL refreshes management/EAPOL receive registrations during
  radio-wide and per-interface AP reconfiguration. It also rearms the VAP
  operational state so replacement sockets are actually created. This fixes
  the failure mode where an AP continued beaconing but hostapd did not receive
  authentication frames.
- The wmediumd client-carousel test now tracks the actual frequency of each
  target BSS, primes same-band candidates through the supplicant, and requires
  exact agreement between the physical BSSID and controller topology BSSID.
  The soak tests cover these recovery paths.

### Topology and steering presentation

- The WebUI provides a short-lived presentation-only steering-event endpoint.
  `gen/steer.sh` announces planned, moving, completed, and failed phases around
  the real EasyMesh steering request.
- Before a steer, the selected client is highlighted with its intended target.
  During convergence it is animated between APs; arrival receives a pulse and
  fading trail. These cues do not modify the EasyMesh model or make the steering
  decision.
- Optimize Layout is topology-aware: mostly-star topologies center the
  controller and full chains use a two-row serpentine layout suited to a
  landscape viewport.
- The topology pane is bounded to the current browser viewport and no longer
  grows vertically after repeated refreshes or resizing.
- Wireless backhaul links remain solid when signal telemetry is temporarily
  unavailable; freshness is represented by opacity instead of incorrectly
  making a physical link look absent.

### Appliance handoff

- The Vagrant box name and VM name are generic and can be overridden through
  environment variables, so the same bundle works from any new empty
  directory and on any supported host address.
- The packaged guide uses the adjacent `SHA256SUMS`, imports exactly one box,
  and includes explicit removal, operation, health, and test procedures.

## Acceptance performed for 0828

The new images were deployed from scratch on rev120 and the VM was then
actually rebooted. Automatic reconstruction passed with:

```text
controller model       5 devices / 15 radios / 50 BSSs / 24 associated STAs
fronthaul clients      20 / 20
client RCPI            20 / 20 nonzero
backhaul telemetry     4 / 4 fresh
association ownership  20 / 20 physical BSSID matches controller API BSSID
client connectivity    20 / 20 at 0% packet loss
service restarts       zero for OneWifi and all EasyMesh processes
stability hold         120 seconds
wmediumd Console       healthy
```

The 0828 release is therefore a replacement for 0827. Import it under the same
logical `cmf/easymesh-lab` name only after stopping and removing the old VM as
described in `README.md`.
