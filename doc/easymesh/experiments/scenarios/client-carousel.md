# Live client-carousel topology test

## Purpose

The client carousel is a visual association-churn test. It continuously moves
small, named groups of WLAN clients around the five fronthaul APs while the
Network Topology page remains open. Each move contains a real disconnect
interval followed by deterministic RF placement at the next AP.

This is the easiest scenario to correlate by eye because the test prints the
same stable labels that the WebUI displays: `STA-03` for private clients and
`IOT-03` for IoT clients.

It is not an optimizer or steering-policy test. The script never calls
`steer.sh`. It uses atomic wmediumd SNR generations to make one destination the
only reachable AP. During the visible pause it also gates the selected station
interfaces down and back up, preventing immediate fallback association before
the destination generation is ready. The resulting disconnection,
reassociation, agent notifications and controller topology updates are real.

## Scenario

For either ten-client cohort in the accepted five-AP/20-client lab, the script
creates five groups of two clients and forms this visible ring:

```text
 [Agent-1] -> [Extender-1] -> [Extender-2] -> [Extender-3] -> [Extender-4]
   Group 1      Group 2         Group 3         Group 4         Group 5
      ^                                                            |
      +------------------------------------------------------------+
```

The exact group membership and AP/container mapping are discovered at runtime
and printed before the first move. For every group, one carousel step is:

```text
stable on source AP
  -> BLACKOUT: every client/AP link for that group becomes -20 dB
  -> set the selected wlan0 interfaces down
  -> require iw link = Not connected
  -> hold the disconnected state for four seconds
  -> ARRIVAL: next AP becomes 45 dB; every other AP remains -20 dB
  -> set the selected wlan0 interfaces up
  -> require the real client BSSID to belong to the next AP
  -> require the WebUI/API parent to be the same next AP
  -> hold the new position for four seconds
  -> start the next group
```

This deliberate break-before-make pattern is important. A smooth RF crossover
does not guarantee a roam: the client can remain associated, and this BPI lab
does not yet contain an autonomous optimizer that orders a steer. At the
control protocol's minimum `-20 dB`, a scanning supplicant can also immediately
attempt another weak candidate. The station link gate makes the demonstration
repeatable without coupling wmediumd to an EasyMesh steering command.

Initial formation and final placement restoration also run one two-client
group at a time. Moving all ten clients in one generation is a useful event-path
stress test, but it is not a stable setup/cleanup mechanism and is now kept
separate from the visual scenario.

## Run it

Open the WebUI Network Topology tab first and optionally click **Optimize
Layout** once. Then run on the lab host/VM:

```sh
cd /home/rev/easymesh-lab/0824-clean/meta-cmf-bananapi-vcpe
gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 2
```

Inside a distributable VM the repository is normally under `/home/vagrant`:

```sh
cd /home/vagrant/git/meta-cmf-bananapi-vcpe
gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 2
```

Two rounds move every client twice and then return all clients to their
preflight APs. For a continuous demonstration, use:

```sh
gen/tests/wmediumd-client-carousel.py --ssid private_ssid --rounds 0
```

Press `Ctrl-C` once to stop. The signal is handled at a phase boundary, the
original client placement is reconstructed, and every touched SNR pair is
restored to its captured value before the script exits.

Useful controls:

```text
--rounds 2                 full rotations; 0 means run until Ctrl-C
--ssid private_ssid        select private clients (use iot_ssid for IoT)
--blackout-hold 4          seconds to leave clients visibly absent
--arrival-hold 4           seconds to leave clients visibly at the new AP
--disconnect-timeout 30    deadline for real and controller disassociation
--connect-timeout 60       deadline for real and controller reassociation
--strong-snr 45            reachable destination value
--outage-snr -20           unreachable link value
--output-root PATH         evidence directory
```

## What should be visible

The console announces the visual event before changing the medium:

```text
BLACKOUT round=1 group=1 STA-03,STA-04 Agent-1 -> DISCONNECTED
ARRIVAL  round=1 group=1 STA-03,STA-04 DISCONNECTED -> Extender-1
```

Within the following two-second WebUI refreshes:

1. the named phones remain at their last-known source during the disconnect hold;
2. they jump to the announced destination after ARRIVAL; and
3. the next group begins the same sequence.

The first point is a controller limitation, not simulated truth: the current
RDK EasyMesh model retains a disconnected STA under its last-known parent until
the next association notification. The WebUI therefore cannot truthfully show
an absent phone using controller data alone. The observable acceptance signal
is the predictable clockwise parent change after every ARRIVAL. The event log
and client `iw` state prove that a real disconnect occurred between parents.

The script does not infer success from elapsed time. It advances only after
both the client's `iw` association and the controller topology agree. A stale
or zero-node API response cannot satisfy an arrival transition.

## Evidence and cleanup

Each run writes under `/tmp/wmediumd-client-carousel/<timestamp>-client-carousel/`:

```text
inventory.json       frozen hwsim/container identities
scenario.json        AP ring, groups and SNR/timing parameters
events.jsonl         every blackout, disconnect, arrival and convergence
topology-before.json controller state before formation
topology-after.json  controller state after cleanup
summary.json         result and restoration status
```

A pass requires every group to disconnect, reconnect to the announced AP, and
converge in the topology. It also requires verified medium restoration and
preflight client placement restoration. Backhaul pairs are never touched,
wmediumd is never restarted, and cleanup leaves every client interface up.

Any disagreement between the physical association, controller model and API is
a hard failure. Preserve the complete run directory for diagnosis.
