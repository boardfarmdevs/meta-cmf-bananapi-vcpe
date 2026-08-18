# wmediumd configurator

This directory contains the scenario-language implementation described in
`doc/easymesh/configurator.md`.

Python 3.8 or newer is supported so the offline compiler and tests can also run
on the rev140 build host; live inventory and execution still run inside the lab
VM that owns the LXD/hwsim topology.

The current `0.1` increment implements parsing, validation, live LXD/hwsim
inventory, frozen role binding, deterministic event-plan compilation, and live
execution through wmediumd's dedicated atomic control socket. Every generation
is read back, the captured baseline is restored on normal exit or a handled
interrupt, and ramps never restart wmediumd.

Run directly from the source tree:

```sh
cd gen/wmediumd/configurator
python3 -m unittest discover -s tests -v
python3 -m wmdcfg.cli inventory -o /tmp/inventory.json
python3 -m wmdcfg.cli compile scenarios/two-ap-crossover.wmd \
    --inventory /tmp/inventory.json \
    --bind client=wlan-client \
    --bind ap_a=bpibroadband \
    --bind ap_b=bpiap \
    -o /tmp/two-ap-crossover.plan.json
python3 -m wmdcfg.cli status
python3 -m wmdcfg.cli run /tmp/two-ap-crossover.plan.json \
    --output-root /tmp/wmdcfg-runs
```

Every station/AP pair declared by the scenario must be initialized in its first
phase. Bindings are frozen to hwsim transmitter identities (`permanent | 0x40`)
and never follow the client's association.

For a two-minute visual check of live RCPI reporting, the wrapper discovers the
selected client's current serving AP, oscillates only that RF link, samples
`/api/v1/clients`, and restores the captured medium state:

```sh
./run-rcpi-monitor.sh wlan-client
```

Keep the WebUI **Connected Clients** tab open during the run. Its Signal column
refreshes every two seconds and shows both dBm and raw RCPI. The wrapper keeps
traffic flowing to `10.0.0.1` so hwsim reports each current phase; set
`WMD_TRAFFIC_TARGET` to use a different reachable address.

The runner requires a complete EasyMesh topology and all expected WLAN clients
to be active at preflight and postflight. Run artifacts contain the frozen plan,
every applied generation and observation, health snapshots, verified restore,
and a machine-readable summary.
