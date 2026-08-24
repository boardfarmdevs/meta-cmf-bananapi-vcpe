# Quickstart for an installed lab

Audience: an operator using the prepared rev130 lab or an equivalent installed
VM.

Purpose: reach a known-good state, open both UIs, perform one manual steer, and
run one reversible RF scenario. This is not an installation guide. For a fresh
deployment or reboot recovery, use [operations](operations.md).

## 1. Enter the current checkout

On rev130:

```sh
ssh rev130
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
```

Inside a packaged VM, the repository is normally:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
```

Confirm that the checkout and expected topology match
[the current baseline](../current-state.md):

```sh
git branch --show-current
lxc list -c ns4t
gen/wmediumd/wmediumd-up.sh status
```

Expected mesh instances are `bpibroadband`, `bpiap`, and `bpiap-001` through
`bpiap-003`. The small client profile contains `wlan-client` and
`wlan-client-001` through `wlan-client-019`.

## 2. Run the health gate

```sh
mkdir -p tmp/test-results/quickstart
gen/tests/health-audit.sh | tee tmp/test-results/quickstart/health.txt
```

Do not proceed if the audit reports an incomplete model, missing client,
traffic loss, stale service, or unexpected restart. The accepted result is:

```text
5 devices / 15 radios / 50 BSSs / 24 associated STAs
20 clients: 10 private + 10 IoT
20/20 gateway traffic
zero monitored service restarts
```

## 3. Open the live views

For rev130:

```text
EasyMesh WebUI       http://192.168.2.130:8888
wmediumd Console     http://192.168.2.130:8890
```

In the EasyMesh WebUI, select **Network Topology**. In the Console, verify that
health is `ok`, 25 station identities are resolved, and the pair table contains
600 directed pairs.

## 4. Perform one named steer

First resolve the proposed action without sending it:

```sh
gen/steer.sh --dry-run sta-03 extender-2
```

If `STA-03` is already on Extender-2, select another extender. Then send the
bounded command:

```sh
gen/steer.sh sta-03 extender-2
```

Pass only when all three observations agree:

1. the command exits successfully;
2. the station's `iw dev wlan0 link` reports the resolved target BSSID; and
3. the WebUI moves the client to the target node without a page reload.

The command is a real EasyMesh steering request and 802.11v BTM exchange. It is
not an autonomous optimizer decision.

## 5. Run a reversible RF demonstration

With the Network Topology page visible, rotate the private cohort twice:

```sh
gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 2
```

Use `--ssid iot_ssid` for the IoT cohort. The script captures the initial
medium and client placement, performs the scenario, and restores all touched
SNR pairs and placements on a clean exit.

During the run:

- the EasyMesh WebUI shows disconnects and new AP ownership;
- the wmediumd Console shows the affected RF links and packet outcomes; and
- the terminal prints the expected client group and destination.

Do not run two scenario writers at the same time.

## 6. Confirm restoration

```sh
gen/tests/health-audit.sh | tee tmp/test-results/quickstart/final-health.txt
gen/wmediumd/wmediumd-up.sh status
```

The final health gate must match the initial one. A scenario that produces an
interesting steer but fails to restore the medium is a failed experiment.

Next steps:

- [Demonstration runbook](demonstrations.md)
- [Experiment catalog](../experiments/README.md)
- [RF simulation concepts](../concepts/rf-simulation.md)
- [Optimizer research workflow](../concepts/optimizer.md)
