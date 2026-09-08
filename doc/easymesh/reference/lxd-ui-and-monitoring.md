# LXD web UI, container and outer-VM monitoring

Audience: operators who want to inspect the containers **inside** an EasyMesh
LXD VM, then graph their CPU, memory, interface traffic, disk I/O and processes.
An optional second scrape adds the appliance VM's guest resource metrics from
the physical host's LXD to the same Prometheus/Grafana installation.

This is an opt-in management-plane addition. Import with `--monitoring` to enable
it; otherwise it stays disabled. It does not change RF conditions, install agents in the
Yocto/Alpine containers, or change the immutable client profile. Consult
[current state](../current-state.md) for release acceptance; enabling monitoring
does not turn a failed lab audit into a pass.

## Browser-ready setup (RDK and prplMesh, current rev140: 0907)

For an existing running RDK VM, execute on its physical LXD host:

```sh
SOURCE=/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/meta-cmf-bananapi-vcpe
LAB_LXD_UI_PORT=48892 LAB_GRAFANA_PORT=48893 LAB_MONITORING_ALLOW_RESTART=1 \
  bash "$SOURCE/gen/vm/lxd/observability/enable.sh" \
  rdkeasymesh-20-0907 192.168.2.140 rev140-rdk-0907
```

The equivalent prplMesh source command is
`bash deploy/lxd-vm/observability/enable.sh VM HOST_IPV4 LABEL`. Both importers
accept `bash import.sh --profile 20 --monitoring` in newly packaged releases.
Older immutable 0906 archives remain unchanged; use the source helper for them.
The historical runtime acceptance below is RDK/rev140 only. The Windows-access
corrections and optional outer-metrics integration are source additions; they
do not by themselves enable a host listener or update existing immutable tars.

| Browser service on rev140 | URL | Authentication |
| --- | --- | --- |
| Inner LXD full bundled UI | `https://192.168.2.140:48892/` | Browser certificate and identity enrollment |
| Grafana container dashboard | `https://192.168.2.140:48893/` | Generated per-VM admin password |

From a trusted shell on rev140, obtain first-login credentials privately:

```sh
lxc exec local:rdkeasymesh-20-0907 -- lxc auth group show local:admins
lxc exec local:rdkeasymesh-20-0907 --mode=interactive -- lxc auth identity create local:tls/lab-browser --group admins
lxc exec local:rdkeasymesh-20-0907 -- cat /opt/easymesh-observability/secrets/grafana-admin-password
```

Follow LXD UI's certificate creation/import flow, then supply the enrollment
token. It grants inner-LXD administrative access: do not share it with observers.
Grafana username is `admin`; create Viewer-role accounts for read-only users.
The provisioned container dashboard opens as Grafana's home dashboard and has
lab/project/container selectors, CPU, memory, network, disk, process and OOM views.

Both browser endpoints use generated self-signed TLS certificates. Verify their
SHA-256 fingerprints through the host shell before accepting the browser warning:

```sh
lxc exec rdkeasymesh-20-0907 -- openssl x509 -in /var/snap/lxd/common/lxd/server.crt -noout -fingerprint -sha256
lxc exec rdkeasymesh-20-0907 -- openssl x509 -in /opt/easymesh-observability/secrets/grafana.crt -noout -fingerprint -sha256
```

The helper binds UI/API 8443 and Grafana 3000 to the VM management IPv4 and
adds only `lab-lxd-ui` / `lab-grafana` outer NAT proxies. Prometheus 9090 and
authenticated metrics 8444 remain loopback-only. Override browser ports with
`LAB_LXD_UI_PORT` / `LAB_GRAFANA_PORT` if several VMs share one physical host.
VM `boot.autostart` is not changed. Restrict management access to a trusted LAN
or VPN; do not forward these ports indiscriminately onto the Internet.

Older RDK Boardfarm checks assumed that the VM contained exactly two Docker
containers. Setup's `prepare-rdk.py` narrowly changes those checks to count only
the two Boardfarm names, backing up their previous scripts under the managed
state directory. Without this fix, monitoring could incorrectly trigger WAN
teardown/rebuild on a later lab restart. The source build/rebuild/audit scripts
include the same correction. prplMesh does not use this RDK compatibility step.

First network-enabled setup replaces an unexposed cloned LXD server identity
with a unique per-VM certificate. Its `reload-lxd.sh` maintenance helper first
stops active room/lab units while LXD is available, restarts LXD, then restores
those units. Set `LAB_MONITORING_ALLOW_RESTART=1` explicitly for that first
maintenance operation on an active lab; allow several minutes for recovery.
It refuses a transitioning lab. Repeated setup preserves identity and does not
restart the lab. Fresh thin imports enable monitoring before starting the lab.
Do not use an ordinary `systemctl reload snap.lxd.daemon` on a live lab: the
snap restarts its daemon and `Requires=` dependencies can stop the room/lab.
The first rev140 installation exposed this coupling and required lab recovery;
`RestartMode=direct` also failed to prevent it, so the final helper does not
rely on that setting. Existing exposed LXD identities are
preserved. All generated certificates expire after one year; schedule renewal.

The following numbered sections retain the detailed **local-only / SSH-tunnel
alternative**. Do not run that alternative over a browser-ready installation:
its loopback addresses differ. Use the same `enable.sh` command for repeat setup.

### rev140 acceptance record (2026-09-07)

- RDK `rdkeasymesh-20-0906` only; no deployment to rev150 or prplMesh/rev120.
- Authenticated LXD browser shows all 25 running containers; Grafana login
  opens the provisioned dashboard with 25-container CPU/memory/network data.
- Prometheus targets are UP; all ten dashboard panel expressions return data.
  Anonymous metrics/LXD inventory requests are forbidden, Grafana user API
  requires login, and the metrics certificate cannot manage LXD instances.
- Room health reports 20 active clients, six topology nodes and a converged
  optimizer. The native lab health audit passes; grey cursors and floor-level
  dashed mesh links also pass the browser regression.
- Repeat enablement preserves credentials, native container/service identities,
  the LXD daemon, room process and existing Docker container identities.
- With the Go-runtime target configured, six reload rounds using home and
  single-client dashboard tabs pass with no Grafana restarts or JavaScript
  errors; sampled memory is 307.4–316.9 MiB under the unchanged 512 MiB cap.
- Corrected Boardfarm fast-path verification completes in one second with
  monitoring running, preserving both WAN/DHCP container identities.
- Both source bundles pass 19 configuration/helper tests; mocked imports prove
  optional monitoring runs before initial lab startup. prplMesh is source-tested
  only. Existing immutable thin archives are not rebuilt by this change.

Evidence and browser screenshots: `/home/rev/work/lab-monitoring-0906/` on rev140
and the editing workstation. Test browser credentials are revoked after use;
users must enroll their own browser identity. Outer VM autostart remains false.

## 1. Choose the correct LXD server

There are two independent LXD daemons:

```text
Operator workstation
  | SSH jump through rev140 or rev150
  v
Ubuntu appliance VM: rdkeasymesh-20-0905
  |-- nested LXD HTTPS UI/API  127.0.0.1:8443
  |     `-- bpibroadband, bpiap[-NNN], wlan-client[-NNN]
  |-- nested LXD metrics      127.0.0.1:8444/1.0/metrics
  |                | authenticated TLS scrape every 30 seconds
  |-- Prometheus (Docker)     127.0.0.1:9090
  `-- Grafana (Docker)        127.0.0.1:3000

Physical host's outer LXD: manages the appliance VM, not its nested containers
```

The outer host UI shows the VM as one instance. Open the **guest's** LXD UI
to see the controller, four extenders and 20 WLAN client containers. Agent-1
and Controller share `bpibroadband`; they are not two LXD containers. The
20-client lab therefore has 25 nested LXD instances, while its EasyMesh WebUI
shows six mesh nodes.

The bundled monitoring services are Docker containers in the Ubuntu VM. They
do not add LXD instances or consume hwsim radios. Existing Boardfarm Docker
containers are not included in LXD metrics; neither are physical-host resource
metrics. Do not confuse this dashboard with [EasyMesh STA/AP metrics](metrics.md),
the [wmediumd Console](wmediumd-console.md), or an end-to-end traffic test.

## 2. What is provided

The source files live at `gen/vm/lxd/observability/`:

| File | Purpose |
| --- | --- |
| `enable.sh` | Host-side browser-ready setup, start monitoring, add authenticated browser ports |
| `setup.sh` | VM-side configuration and credentials; loopback by default |
| `enable-outer-metrics.sh` | Opt-in host-side VM scrape using existing Prometheus/Grafana |
| `enable-rev140-outer-lxd-metrics.sh` | Current rev140 RDK 0907 preset, not the stopped 0906 VM |
| `disable-outer-metrics.sh` | Remove the outer job/dashboard and revoke its host-side trust |
| `outer-metrics.py` | Verified installation, rollback, persistent job rendering and removal |
| `reload-lxd.sh` | Explicit first-identity maintenance: ordered lab stop, daemon restart, lab restore |
| `prepare-rdk.py` | Backed-up compatibility repair for older RDK Boardfarm inventory checks |
| `disable.sh` | Stop this Compose project, revoke its metrics certificate, restore owned LXD settings |
| `compose.yaml` | Version-pinned Prometheus and Grafana services with persistent volumes |
| `.env.example` | Image references and browser-facing Grafana URL |
| `prometheus.yml` | Authenticated nested-LXD scrape and Prometheus self-monitoring |
| `grafana/provisioning/datasources/prometheus.yml` | Provisioned data source, UID `lxd-prometheus` |
| `grafana/provisioning/dashboards/lxd.yml` | File-backed dashboard provisioning |
| `grafana/dashboards/lxd-containers.json` | Container dashboard, UID `easymesh-lxd` |
| `grafana/dashboards/lxd-outer-vms.json` | Optional outer VM dashboard, UID `easymesh-lxd-outer` |

Installation copies these files to `/opt/easymesh-observability`. Runtime
credentials are generated there, not committed into Git. The dashboard is
provided locally; no dashboard download, plugin installation or Loki deployment
is required to see container metrics.

The supplied image tags are Prometheus `v3.14.0` and Grafana `13.2.1`. They are
explicit versions, not `latest`. For immutable/offline deployment, record the
pulled repository digests and replace the image references in the installed
`.env` with those digests. Review upstream release/security updates before
changing versions; validate the configuration and retain the previous images.

## 3. Prerequisites and resource boundary

Run outer-host commands on `rev140` or `rev150`. Run VM commands inside the
Ubuntu appliance, never inside `bpibroadband` or a WLAN client.

On the outer host:

Replace `VM` with the actual appliance name from `lxc list` if it differs;
the name below is the intended 0905 release name, not an assertion that a
particular candidate has already been deployed or accepted.

```sh
VM=rdkeasymesh-20-0905
lxc list "$VM" -c ns4
lxc exec "$VM" -- lxc --force-local list
lxc exec "$VM" -- lxc version
lxc exec "$VM" -- docker compose version
lxc exec "$VM" -- /usr/local/sbin/easymesh-labctl check
```

Use an initialized LXD snap with its web UI and metrics API, Docker Engine,
the Compose v2 plugin, OpenSSL, `jq`, and `curl`. The setup helper deliberately
does not run `lxd init`, reinstall Docker, modify host firewall rules, or
replace an existing non-loopback LXD listener. The appliance already provides
Docker for Boardfarm; do not install a second Docker daemon.

Reserve approximately 1 GiB of additional memory headroom: each monitoring
container is capped at 512 MiB and half a CPU. These caps are limits, not
measured consumption. Grafana's `GOMEMLIMIT=256MiB` soft Go-runtime target
reserves headroom beneath its container cap; the initial untuned configuration
hit that cap during repeated dashboard loads on rev140. Prometheus keeps up to seven days or 1 GB of TSDB blocks,
whichever retention policy removes old blocks first. WAL/head data, Grafana
state, image layers and logs need additional disk space; the retention flag
is not a hard quota on the entire Docker volume. Budget several GiB and check
`df -h` and `docker system df` before enabling it on a busy 8 GiB appliance.

The scrape interval is 30 seconds, including the Grafana data-source interval.
Increase both together for larger rosters. LXD metrics collection has a cost;
capture performance/soak baselines with monitoring consistently enabled or
consistently disabled, not a mixture.

## 4. Install inside the VM

Enter the VM from its outer host:

```sh
lxc exec "$VM" -- bash
cd /home/easymesh/git/meta-cmf-bananapi-vcpe/gen/vm/lxd/observability
bash setup.sh rev140-0905
```

On rev150 use the distinct label `rev150-0905`. Do not copy generated private
keys or passwords between appliances. The label becomes the `lab` label on
scraped series, useful when comparing hosts later.

If an older deployed VM does not yet contain these source files, copy only
the optional bundle instead of upgrading its running lab checkout. On an
outer host with the updated source checkout:

```sh
SOURCE=/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/meta-cmf-bananapi-vcpe
tar -C "$SOURCE/gen/vm/lxd" -czf /tmp/easymesh-observability-source.tgz observability
lxc file push /tmp/easymesh-observability-source.tgz "$VM/tmp/easymesh-observability-source.tgz"
lxc exec "$VM" -- mkdir -p /root/easymesh-observability-source
lxc exec "$VM" -- tar -xzf /tmp/easymesh-observability-source.tgz \
  -C /root/easymesh-observability-source
lxc exec "$VM" -- bash /root/easymesh-observability-source/observability/setup.sh rev140-0905
```

Adjust `SOURCE` to that host's checkout, or transfer the source-only archive
from rev140 to rev150 before its `lxc file push`. Keep this source directory
for deliberate reinstallation; do not copy another VM's installed `/opt`
directory because it contains that VM's credentials.

Setup checks that it is running as root in a configured RDK or prplMesh appliance.
It selects the local Unix-socket LXD server explicitly
with `--force-local`, rather than following a user's default remote.

It then:

1. Saves the previous values of `core.https_address`, `core.metrics_address`
   and `core.metrics_authentication` under `state/previous-lxd.json`.
2. Copies the supplied configuration and dashboard.
3. Generates a one-year metrics client certificate and trusts it with
   `--type=metrics`, not as an administrative client certificate.
4. Copies the local LXD server certificate as Prometheus's trust anchor and
   verifies that its SAN covers `127.0.0.1`.
5. Generates a random Grafana initial administrator password in a file.
6. Enables authenticated LXD metrics on `127.0.0.1:8444` and the LXD UI/API on
   `127.0.0.1:8443`. It does **not** start Prometheus or Grafana yet.

The script is repeatable: it retains the password and matching, unexpired
metrics key/certificate, preserves the original rollback settings and checks
that any already-trusted certificate still has metrics-only type. Rerunning
it refreshes managed configuration from source; back up local edits first.
It refuses an unmanaged installation directory or conflicting LXD listeners.
If setup stops partway through, resolve the reported problem and rerun it, or
use `disable.sh`; do not delete the saved rollback state casually.

No `core.metrics_authentication=false`, `insecure_skip_verify=true`, trusted
Docker/LXD socket mount, or shared `admin/admin` password is needed.

## 5. Start Prometheus and Grafana

Still inside the VM:

```sh
cd /opt/easymesh-observability
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps --entrypoint promtool prometheus \
  check config /etc/prometheus/prometheus.yml
docker compose up -d
docker compose ps
```

Compose uses host networking intentionally: `127.0.0.1` in these two Docker
containers is the Ubuntu VM, where nested LXD listens. It is **not** a Docker
bridge gateway or the physical host. Neither service mounts an administrative
socket or runs privileged; Grafana and Prometheus run with separate non-root
UIDs. Docker restart policies bring them back after the VM/Docker starts.

Inspect the image digests for your installation record:

```sh
docker image inspect prom/prometheus:v3.14.0 grafana/grafana:13.2.1 \
  --format '{{json .RepoDigests}}'
```

If the appliance has no Internet access, pull the same images on a connected
machine of matching architecture, transfer a `docker save` archive and run
`docker load` inside the VM before `docker compose up -d --pull never`.
The optional monitoring images are not part of the base thin-tar offline
contract unless separately packaged and checksummed.

## 6. Open the three UIs through SSH

For this local-only alternative, listeners are inaccessible directly from the LAN. The
EasyMesh ports `18889`, `18890` and `18891` remain unchanged. Use an SSH session
whose final destination is the **VM**, jumping through the outer host.

From the outer host, obtain the VM's management IP:

```sh
lxc list "$VM" -c n4
lxc exec "$VM" -- systemctl is-active ssh.service
```

Use the VM's management/NAT-interface address, not a `10.0.0.x` WLAN address.
The appliance SSH user is `easymesh`. Its public key must already be authorized;
the host's LXD permission does not automatically grant SSH access to the VM.
If necessary, copy **only your workstation public key** to the outer host as
`/tmp/easymesh-observer.pub`, then authorize it without replacing existing keys:

```sh
lxc file push /tmp/easymesh-observer.pub "$VM/tmp/easymesh-observer.pub"
lxc exec "$VM" -- bash -euc '
  install -d -m 0700 -o easymesh -g easymesh /home/easymesh/.ssh
  touch /home/easymesh/.ssh/authorized_keys
  key=$(cat /tmp/easymesh-observer.pub)
  grep -Fqx "$key" /home/easymesh/.ssh/authorized_keys || \
    printf "%s\n" "$key" >> /home/easymesh/.ssh/authorized_keys
  chown easymesh:easymesh /home/easymesh/.ssh/authorized_keys
  chmod 0600 /home/easymesh/.ssh/authorized_keys
  rm /tmp/easymesh-observer.pub
'
rm /tmp/easymesh-observer.pub
```

If SSH is absent, install and enable `openssh-server` inside the Ubuntu VM
under your site's SSH policy. Keep password/root login disabled and verify
the server's host-key fingerprint through `lxc exec` before accepting it.
Never transfer the workstation private key or disable SSH host-key checking.
For the standard Ubuntu guest, after authorizing your public key, run these
commands inside the VM as root:

```sh
install -d -m 0755 /etc/ssh/sshd_config.d
printf '%s\n' 'PermitRootLogin no' 'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' 'PubkeyAuthentication yes' \
  > /etc/ssh/sshd_config.d/00-easymesh-observer.conf
apt-get update
apt-get install -y openssh-server
/usr/sbin/sshd -t
systemctl enable --now ssh.service
systemctl reload ssh.service
/usr/sbin/sshd -T | grep -E '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|allowtcpforwarding) '
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Confirm the effective settings match those intended, including forwarding
being allowed for `easymesh`. Existing site configuration or `Match` rules can
override access. Enabling SSH also opens the guest's SSH listener; restrict it
to the management network according to site policy. The monitoring helper
neither installs SSH nor changes its policy, and disabling monitoring does
not undo these separately administered SSH changes.

On the workstation, replace `VM_MANAGEMENT_IP` with the address just observed:

```sh
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -J rev@192.168.2.140 \
  -L 127.0.0.1:18443:127.0.0.1:8443 \
  -L 127.0.0.1:19090:127.0.0.1:9090 \
  -L 127.0.0.1:13000:127.0.0.1:3000 \
  easymesh@VM_MANAGEMENT_IP
```

Leave that SSH process running:

| UI | Workstation URL |
| --- | --- |
| Nested LXD | `https://127.0.0.1:18443` |
| Prometheus | `http://127.0.0.1:19090` |
| Grafana | `https://127.0.0.1:13000` |

For rev150, change the jump host to `rev@192.168.2.150` and use its VM IP.
For simultaneous sessions, use local ports `28443`, `29090`, `23000` for that
second tunnel. Set its installed `.env` to
`GRAFANA_PUBLIC_URL=https://127.0.0.1:23000/` and recreate Grafana with
`docker compose up -d grafana`. The guest ports remain `8443/9090/3000`.

Set `GRAFANA_PUBLIC_URL=https://127.0.0.1:13000/` for the first tunnel as well,
then `docker compose up -d grafana`. Do not bind SSH forwards to `0.0.0.0` or
expose unauthenticated Prometheus. For shared LAN access, use the browser-ready
helper instead and retain its authentication and network restrictions.

## 7. Authenticate to nested LXD

The LXD UI needs its own browser identity; a Grafana account or room-viewer
operator token does not grant LXD access.

1. Open `https://127.0.0.1:18443`. Verify the self-signed server certificate's
   SHA-256 fingerprint against the certificate read inside this VM:

   ```sh
   openssl x509 -in /var/snap/lxd/common/lxd/server.crt \
     -noout -fingerprint -sha256
   ```

2. Follow the UI's browser-certificate creation/import instructions. Keep its
   private key private and select that certificate when the browser requests it.
3. In a private terminal inside the VM, verify `lxc auth group show local:admins`,
   then run `lxc auth identity create local:tls/lab-browser --group admins`.
   Supply its short-lived identity token to the modern UI. When entering from
   the host, use `lxc exec VM --mode=interactive -- ...`; when using SSH, also
   allocate its terminal with `ssh -t`. See the Windows instructions below for
   group provisioning and the distinction from legacy certificate tokens.
4. Select project `default` and the Instances page. Confirm the expected
   `bpibroadband`, `bpiap` through `bpiap-003`, and `wlan-client` through
   `wlan-client-019` roster. Compare with `lxc --force-local list` in the VM.

For read-only observers, use your LXD version's fine-grained authorization
groups and viewer entitlements instead of distributing administrator browser
certificates. Older restricted TLS certificates constrain projects but are
not equivalent to a read-only account. Audit `lxc auth identity list local:`
and `lxc config trust list`, and revoke
unneeded identities after the demonstration. Stopping/restarting containers
from the UI changes the lab: use the existing lab lifecycle/acceptance runbook,
not arbitrary UI actions during room or release tests.

## 8. Sign in to Grafana and select containers

Retrieve the generated initial password **privately inside the VM**:

```sh
sudo cat /opt/easymesh-observability/secrets/grafana-admin-password
```

Open Grafana through the tunnel, sign in as `admin`, and change the password
in Grafana. Create non-admin accounts for observers. Grafana stores account
state in its persistent volume: editing the initial-password file later does
not reset an existing account's password. Use Grafana's documented password
reset procedure if necessary.

Go to **Dashboards → EasyMesh → EasyMesh nested LXD containers**. Choose the
`lab`, `project`, and `Container` filters. Select one extender or WLAN client
to isolate it, or All to compare the roster. Allow at least two scrapes for
rate graphs; the default time range is one hour and refresh is 30 seconds.

The included panels show exporter reachability, running-container count, CPU,
used memory including cache, per-interface receive/transmit traffic, per-device disk I/O,
processes, available filesystem bytes and OOM-counter increases. CPU 100%
means one core, not the container's full quota. Interface/bridge counters can
count the same packet at multiple layers. Filesystem availability may describe
shared backing storage; absent disk/OOM metrics are not a zero-value guarantee.
Stopped instances remain in LXD UI but do not provide live instance samples.

On this LXD 6.9 container exporter, `MemTotal` is the configured memory limit
and `MemFree` is the remaining amount; the memory panel subtracts the latter
from the former. This is not process RSS. The RSS metric listed in the upstream
reference is not emitted by this appliance's cgroup-v2 containers. Check the
live metric `HELP` text and compare with `lxc query /1.0/instances/NAME/state`
when upgrading LXD rather than assuming all documented families are present
or graphing the memory limit as usage.

The dashboard and data source are file-provisioned and intentionally not
editable in place. To customize, change the source JSON and reinstall it, or
use Save as to create a separately named dashboard. Do not change the managed
UID inadvertently: it is also used by the UI link below.

### Optional Metrics link from the LXD UI

Inside the VM, first record any existing setting, then configure a
browser-facing link (not the Docker-internal Grafana address):

```sh
lxc --force-local config get user.ui_grafana_base_url
lxc --force-local config set user.ui_grafana_base_url \
  'https://127.0.0.1:13000/d/easymesh-lxd/easymesh-lxd?orgId=1&var-project={project}&var-name={instance}'
```

The `{project}` and `{instance}` placeholders select the clicked LXD instance
in this dashboard. With the SSH tunnel open, the instance's Metrics link can
open the corresponding Grafana view. Use `23000` in the second-VM example.
This URL belongs to the operator's browser, so it must match the chosen
browser access method. Restore its previous value, or unset it if originally
empty, when disabling this optional integration.

The upstream full LXD dashboard is an alternative: import Grafana dashboard
`19131` and select the Prometheus data source. Recent revisions also include
Loki/log panels; those require a separate Loki setup and are outside this
metrics-only bundle. Do not treat their empty log panels as a scrape failure.

## 9. Validate the complete path

Inside the VM, check authenticated scraping without bypassing TLS validation:

```sh
cd /opt/easymesh-observability
curl --fail --silent --show-error --max-time 15 \
  --cacert tls/server.crt --cert tls/metrics.crt --key tls/metrics.key \
  https://127.0.0.1:8444/1.0/metrics > /tmp/nested-lxd-metrics.txt
grep '^lxd_cpu_effective_total' /tmp/nested-lxd-metrics.txt

curl -fsS --max-time 10 http://127.0.0.1:9090/-/ready
curl --cacert secrets/grafana.crt -fsS --max-time 10 https://127.0.0.1:3000/api/health
curl -fsS --max-time 10 http://127.0.0.1:9090/api/v1/targets \
  | jq '.data.activeTargets[] | {labels,health,lastError}'
curl -fsSG --max-time 10 http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=count(lxd_cpu_effective_total{job="lxd",type="container",project="default"})' \
  | jq '.data.result'
lxc --force-local list --format json | jq '[.[] | select(.status == "Running" and .type == "container")] | length'
ss -lnt | grep -E ':(8443|8444|9090|3000)\b'
```

For the running 20-client roster, both counts should be 25. A count mismatch
needs investigation, not a dashboard query that hides it. For local-only setup,
all four listeners are on loopback; browser-ready setup binds 8443/3000 to the
VM management IP (use that IP for the Grafana health request). Verify that a request **without** a metrics
client certificate does not return metric samples; a TLS rejection or HTTP
authorization error is expected:

```sh
curl --silent --show-error --max-time 10 --cacert tls/server.crt \
  -o /tmp/unauthenticated-metrics-response -w '%{http_code}\n' \
  https://127.0.0.1:8444/1.0/metrics
```

Finally, inspect the browser dashboard for actual `bpibroadband`, extender and
WLAN-client series, then repeat `easymesh-labctl check`. Retain versions, labels,
scrape status, container counts and the health result with installation evidence.
Do not store private keys, Grafana passwords or browser trust tokens there.

## 10. Troubleshooting

| Symptom | Check / action |
| --- | --- |
| Only one appliance VM appears | You opened the outer host's LXD UI; tunnel to the VM's nested listener |
| Browser cannot connect | Check the SSH final destination, VM management IP, listener and local-port collision |
| UI certificate prompt loops | Verify the server fingerprint, import/select the browser certificate, then complete its trust-token flow |
| Setup refuses existing listener | Inspect the current LXD configuration; do not blindly replace another operator's listener |
| Metrics certificate denied | Check the daemon for that job: nested LXD for `lxd`, outer host LXD for `lxd-outer`; verify fingerprint, type, project restriction and expiry |
| Prometheus reports `x509` error | Inspect the server SAN and trust anchor; refresh the copied server certificate after intentional rotation, not `insecure_skip_verify` |
| Metrics key permission denied | Keep `tls/` mode 0750 and files 0640, group 65534, matching the Prometheus UID/GID |
| Grafana password file denied | Keep its file group 472 and mode 0640; use the supplied UID/GID settings |
| Empty rate graph immediately after startup | Wait for multiple 30-second samples and choose a recent time range |
| Exporter UP, some containers missing | Compare nested LXD project, running state and `name` labels; stopped instances have no live samples |
| Grafana redirects to wrong port | Correct `GRAFANA_PUBLIC_URL` and recreate the Grafana container; match the tunnel port |
| Monitoring services keep restarting | Check `docker compose logs --tail=100`, free space, memory caps and Docker status |
| No radio signal or room-steering graph | LXD metrics are container resource metrics, not EasyMesh/1905/RF telemetry |

For a non-snap LXD installation or a server certificate without loopback SAN,
adapt the server-certificate path and `tls_config.server_name` deliberately.
Pin the correct trust anchor and use a name/IP actually covered by the SAN.
This helper intentionally targets the standard standalone snap-based appliance,
not an arbitrary LXD cluster or an unrelated pre-existing monitoring stack.

## 11. Lifecycle, backup and removal

If outer monitoring is enabled, first run `bash observability/disable-outer-metrics.sh VM`
on the **physical host**. The inner `disable.sh` refuses while the outer state
exists, to avoid leaving its certificate trusted on the host. See the outer
monitoring section for listener cleanup and certificate renewal.

The following Compose lifecycle commands run **inside the VM**:

```sh
cd /opt/easymesh-observability
docker compose stop
docker compose start
docker compose logs --tail=100
docker compose down
```

`stop`/`down` retain data. To disable this integration and restore the LXD
settings saved before setup:

```sh
sudo bash /opt/easymesh-observability/disable.sh
```

Disable removes only its recorded metrics certificate. It preserves settings
changed by another operator instead of overwriting them, and reports that
manual review is needed. It does not remove browser identities, the optional
Grafana UI link, data volumes, images or local credential files.

Before an upgrade, stop the monitoring services and back up the installed
configuration plus both Compose data volumes using your Docker-volume backup
procedure. Keep that backup encrypted and access-controlled: Grafana's database
and the setup directory contain credentials. Record the current image digests.
Do not run `docker system prune` or a volume-wide prune on this appliance;
Boardfarm has unrelated Docker resources.

For deliberate full removal, after backup and successful `disable.sh`, remove
only this project's volumes and local installation:

```sh
cd /opt/easymesh-observability
docker compose down --volumes
cd /
sudo rm -rf /opt/easymesh-observability
```

Review/revoke browser trust entries and restore/unset the optional
`user.ui_grafana_base_url` separately. Certificate renewal likewise requires
an explicit procedure: stop scraping, revoke the old metrics fingerprint,
archive/remove that certificate and key, rerun setup to create a new pair,
restart the services and repeat TLS/authentication/target checks. Setup refuses
expired or mismatched credentials rather than silently accepting them.

### Thin-tar release hygiene

Enable this stack **after import**, once per deployed VM. Do not distribute an
enabled builder's metrics keys, browser identities, initial Grafana password,
TSDB or Grafana database in a thin tar. Both stacks' exporters reject a VM with
`/opt/easymesh-observability`: disable it, remove its
volumes/local credentials and any test UI trust/link configuration before
exporting. Retain only the source templates in the checkout. An offline
monitoring-image archive can be supplied separately without embedding secrets.

## 12. Windows Chrome access to the current rev140 lab

This incorporates the supplied `lxd-ui-and-monitoring-windows-access.md`
addendum. Its successful browser enrollment and Grafana login were recorded
against **0906**, nested LXD 6.9 (`6.9-ab8fad2`, snap revision 40424, held),
VM `10.142.138.243`, ports `18892`/`18893`. Those are historical observations,
not instructions to restart that VM. The active **0907** examples here use
`rdkeasymesh-20-0907`, VM `10.142.138.250`, ports `48892`/`48893`.
Read-only inspection on 2026-09-08 found 0907 running, 0906 stopped, nested
LXD 6.9 with an existing `admins` group, and both monitoring services running.
The addendum confirmed login, not an independent dashboard-data audit.

### Grafana login from PowerShell

```powershell
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- cat /opt/easymesh-observability/secrets/grafana-admin-password"
```

Open `https://192.168.2.140:48893/login`; use **admin** and that generated
per-VM password, **not admin/admin**. If it was changed previously, use the
changed password: the file initializes the account only on first run. Do not
recreate services, delete volumes or change configuration to fix a forgotten
password; use Grafana's account recovery procedure. Keep the password out of
chat/logs and create separate Viewer-role accounts for observers.

The home dashboard is **EasyMesh nested LXD containers**, with lab/project/
Container filters. A fully running 20-client lab normally has **25 nested
containers**: one colocated controller/Agent-1, four extenders and 20 clients.
Six mesh roles do not mean six mesh containers. Allow two or more 30-second
scrapes for rate graphs; these graphs are resource usage, not SNR/steering.

### Modern LXD identity enrollment

First check the group through your trusted SSH connection:

```powershell
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- lxc auth group show local:admins"
```

The expected administrator permission is `entity_type: server`, `url: /1.0`,
`entitlement: admin`. If the group is absent on a fresh installation, a trusted
operator can deliberately provision it inside the VM:

```sh
lxc auth group create local:admins
lxc auth group permission add local:admins server admin
```

Do not blindly elevate an existing group. Use separately designed viewer
permissions for observers; the following token grants full inner-LXD management.
In Chrome, follow the UI's client-certificate generation/import instructions
and select that certificate when requested. At the enrollment page, run:

```powershell
ssh -t rev@rev140 "lxc exec local:rdkeasymesh-20-0907 --mode=interactive -- lxc auth identity create local:tls/windows-chrome-ui --group admins"
```

Paste the complete token into
`https://192.168.2.140:48892/ui/login/certificate-add`, click **Connect**, then
open **Instances**, project `default`. An enrolled browser needs no new token
on each visit. For another browser, use a fresh descriptive identity name;
an existing-name error is not a reason to delete a working browser identity.

Both terminal options matter: `ssh -t` allocates the SSH terminal and
`--mode=interactive` carries it into the VM. With nonterminal stdin LXD 6.9
can wait for certificate input until EOF, appearing to hang. The two `local:`
prefixes select different local daemons: the outer host for the VM and the
nested daemon for its browser identity. An expired outer HTTPS CLI client
certificate does not prevent this trusted SSH/local Unix-socket path.

| Token command | Redemption endpoint |
| --- | --- |
| `lxc config trust add` | `/1.0/certificates` (legacy certificate flow) |
| `lxc auth identity create tls/NAME` | `/1.0/auth/identities/tls` (modern identity flow) |

Do not submit the legacy token to the modern identity endpoint. This mismatch
does not demonstrate an LXD version bug; the supplied successful enrollment
did not require a snap update. An identity without group permissions cannot
administer the server. The separate Prometheus command
`lxc config trust add CERT --type=metrics` remains correct: do not replace it
with an administrative browser identity.

### TLS checks and read-only troubleshooting

Compare Chrome's displayed SHA-256 server fingerprint with the corresponding
certificate over trusted SSH before using **Advanced → Proceed**, if offered:

```powershell
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- openssl x509 -in /var/snap/lxd/common/lxd/server.crt -noout -fingerprint -sha256"
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- openssl x509 -in /opt/easymesh-observability/secrets/grafana.crt -noout -fingerprint -sha256"
```

Server trust and the browser's client certificate are separate. These LAN
endpoints need no SSH tunnel; do not overwrite them with the local-only setup.
Access troubleshooting does not require restarting LXD, Grafana or lab nodes.

```powershell
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- lxc --force-local list"
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- lxc auth identity list local:"
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- lxc auth group show local:admins"
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- docker compose --project-directory /opt/easymesh-observability ps"
ssh rev@rev140 "lxc config device show local:rdkeasymesh-20-0907"
```

For pending-identity errors, check token type, issuing VM, expiry and reuse.
For repeated enrollment prompts, check which client certificate Chrome chose.
If only the appliance VM is listed, you opened outer rather than nested LXD.
For empty Grafana panels, check filters, recent time range and Prometheus
targets before changing services. A wrong redirect calls for checking
`GRAFANA_PUBLIC_URL` in `.env` (0907 expects `https://192.168.2.140:48893/`).

## 13. Add outer LXD VM metrics without another monitoring stack

This integrates the monitoring portion of `lxd-grafana.txt` and replaces its
one-off 0906 helper with a reusable, persistent setup. It is **opt-in** and
works with either lab backend. No Node Exporter, extra container, Prometheus
or Grafana instance is added. The nested dashboard stays the home page.

The layers remain distinct:

| Source | Prometheus job | Dashboard / scope |
| --- | --- | --- |
| Inner LXD `127.0.0.1:8444` inside VM | `lxd`, `layer=nested` | `easymesh-lxd`: container CPU/memory/network/disk |
| Physical host's authenticated metrics listener | `lxd-outer`, `layer=outer` | `easymesh-lxd-outer`: the selected appliance VM's guest resources |

Outer VM metrics are **not** physical-host totals, hardware health or the QEMU
process's RSS/CPU. Physical-host monitoring would require a separate exporter
and is outside this setup. When this VM stops, its Prometheus and Grafana also
stop: continuous observation of that outage needs an independent collector.
There is still a modest resource/scrape cost; this is 30-second infrastructure
monitoring, not instrumentation for subsecond optimizer profiling. LXD caches
metric collection for approximately eight seconds.

### Enable on the physical host

Prerequisites: an already running managed monitoring installation in the VM;
local LXD access on the outer host; host `python3`, `lxc`, `openssl`, `ss` and
read access to `/var/snap/lxd/common/lxd/server.crt`; guest `curl`, `openssl`,
Docker Compose and its running Prometheus. Use a standalone snap-based LXD
host, not an arbitrary cluster. Run from a private writable directory for
backups. Do not run monitoring setup/removal concurrently.

The 2026-09-08 read-only check found rev140 outer LXD 5.21.7 LTS with no metrics
listener. Its existing certificate has DNS SAN **rev140**, not the LAN IP.
Do not regenerate that host identity or disable TLS verification. The target
can be an IP while Prometheus verifies `server_name: rev140`.

A read-only scrape through that host's existing Unix socket also confirmed
the active 0907 VM exports **six per-vCPU idle series** while
`lxd_cpu_effective_total` is **zero**. Guest total/available memory, CPU,
network, disk, process and filesystem families were present. This validates
the dashboard's metric choices without opening any host port; it is not an
end-to-end acceptance of the optional HTTPS scrape or new Grafana dashboard.

```sh
SOURCE=/home/rev/yocto/rdkb-bpi-nosrc-vcpe-0905-clean/meta-cmf-bananapi-vcpe
bash "$SOURCE/gen/vm/lxd/observability/enable-rev140-outer-lxd-metrics.sh"
```

Equivalent generic command, also suitable for prplMesh with its actual VM,
host IP, certificate DNS SAN and label:

```sh
bash observability/enable-outer-metrics.sh \
  rdkeasymesh-20-0907 192.168.2.140 rev140 rev140-rdk-0907
```

Optional environment: `LAB_OUTER_METRICS_PORT` (default `8444`) and
`LAB_OUTER_PROJECT` (default `default`, the outer VM's project). Prefer a host
bridge/VPN address reachable only by the appliance where possible. The rev140
preset uses its explicit LAN IP; restrict inbound TCP 8444 to the VM/management
network with your host firewall. No wildcard bind, unauthenticated metrics or
outer `core.https_address` change is made. Existing conflicting listeners,
occupied ports, insecure authentication and mismatched trust are refused.

For future imports, the existing `--monitoring` path can opt in to both layers:

```sh
LAB_OUTER_METRICS_ADDRESS=192.168.2.140 LAB_OUTER_TLS_NAME=rev140 \
  LAB_LXD_UI_PORT=48892 LAB_GRAFANA_PORT=48893 \
  bash import.sh --profile 20 --monitoring
```

Without `LAB_OUTER_METRICS_ADDRESS`, new deployments remain nested-only.
Use actual deployment ports and VM names; this command is for a **new import**,
not a reason to reimport the existing 0907 lab. The same variables work with
`enable.sh VM HOST_IPV4 LABEL`. Outer-only setup does not invoke the inner
identity-rotation/restart path and downloads no images.

### Authentication, persistence and failure handling

The existing per-VM metrics certificate is reused, but trusted **separately**
on outer LXD with `--type=metrics --restricted --projects=PROJECT`. Only its
public certificate leaves the VM; the host's public server certificate is
copied in. Neither private key is copied. The certificate cannot administer
outer instances. Its authorization permits metrics for the whole selected
project; the job requests that project and keeps only samples matching the
exact project, VM name and `type="virtual-machine"`. This retention filter is
**not** an instance-level authorization boundary. LXD may still collect other
instances' metrics internally.

`state/outer-metrics.json` records the target and certificate fingerprints.
`setup.sh` renders the managed job again from that state on repeat installation;
it no longer disappears as with the supplied one-off script. Credentials and
the nested dashboard remain unchanged. A changed target/identity requires
disabling the previous integration before enabling the replacement. An older
unmanaged `lxd-outer` job is refused: back it up and deliberately remove its
old marked block/trust before migrating; do not install two outer jobs.

The helper stages configuration and checks it with the running image's
`promtool`, verifies mTLS from the VM and requires actual VM CPU metric series,
then signals **SIGHUP** to Prometheus and waits for the outer target to be UP.
It preserves the live config file's inode for Docker's individual bind mount.
Grafana discovers the atomically installed dashboard at its 30-second poll.
No LXD, Grafana, lab-node or VM restart and no autostart change is needed.

Enable failures attempt to restore the previous config/CA/dashboard/state,
reload Prometheus, revert only unchanged settings modified by that attempt,
and remove only newly added outer trust. Inspect any explicit rollback error
and the private `lxd-outer-metrics-*` backup directory if host/VM communication
fails; remote rollback cannot be guaranteed during an outage. Do not restart
the lab to solve a scrape error. Backups include configuration and public
certificates, never the metrics private key or Grafana password.

### Open, interpret and validate

After enabling, open `https://192.168.2.140:48893/d/easymesh-lxd-outer` with the
existing Grafana login, or **Dashboards → EasyMesh → EasyMesh outer LXD VM**.
Select Host/Lab/Project/VM. Wait 60–90 seconds for rate panels. Expect the selected
running VM, not the 25 nested containers; those remain on the original dashboard.

- CPU execution sums user/nice/system/IRQ/softIRQ time; 100% means one vCPU.
- The normalized CPU panel divides by the count of exported per-vCPU idle
  series, **not `lxd_cpu_effective_total`**, which was zero in the supplied VM
  sample. Idle, I/O wait and steal are not counted as execution.
- VM used memory is `MemTotal - MemAvailable`, unlike the nested cgroup
  dashboard's `MemTotal - MemFree`. Neither is QEMU RSS.
- Network and disk counters are guest-device counters, not RF measurements.
  Process/filesystem families vary with exporter/agent version: **No data**
  means unsupported/missing, not zero resource use.

Read-only target check from PowerShell:

```powershell
ssh rev@rev140 "lxc exec local:rdkeasymesh-20-0907 -- curl --noproxy '*' -fsS http://127.0.0.1:9090/api/v1/targets"
```

Confirm `lxd`, `prometheus` and `lxd-outer` are UP, the outer target is
`192.168.2.140:8444`, its label is `layer=outer`, and `lastError` is empty.
In Grafana Explore verify `up{job="lxd-outer"}` and
`count by (name,project,type) (lxd_cpu_seconds_total{job="lxd-outer",mode="idle"})`.
The latter should contain only the chosen VM/project/type, with its reported
vCPU count. Compare against the outer `lxc config show VM --expanded` CPU
limit and guest CPU roster; inspect mismatches instead of substituting zeros.
Repeat enablement should preserve listener identity, credentials and both
running monitoring containers. Guest CPU families missing despite valid TLS
call for checking the LXD VM agent, not changing the nested EasyMesh stack.

### Removal and renewal

Run on the same outer host/project before removing monitoring or rotating the
shared metrics client certificate:

```sh
bash observability/disable-outer-metrics.sh rdkeasymesh-20-0907
```

This removes the managed scrape/dashboard/state and revokes the recorded
outer metrics trust; nested monitoring and its trust remain. The authenticated
host listener is intentionally retained because other consumers may use it.
Only after checking `lxc --force-local config trust list`, other scrapers and
the saved `host-before.json` should you unset `core.metrics_address` if this
setup originally created it and nobody else needs it. Do not disable metrics
authentication or alter a pre-existing shared listener.

For renewal, disable outer first, then follow the nested certificate-renewal
procedure, and enable outer again with the new public certificate. For a host
server identity rotation, disable outer before planned rotation, review the
new SAN/fingerprint, then re-enable. Do not bypass verification to recover.
If the appliance is lost, use the recorded fingerprint to revoke only that
metrics trust on outer LXD manually. Installed credentials/state/data must
never enter a thin tar; existing export guards continue to reject them.

## Sources and relationship to the example

The [VCPE metrics example](https://www.vcpe.dev/docs/metrics.html) demonstrates
the LXD → Prometheus → Grafana flow. This implementation keeps that flow but
targets the nested daemon and replaces unauthenticated scraping/TLS bypasses
with a metrics-only certificate and verified TLS.

- [LXD UI access](https://canonical.com/lxd/docs/latest/howto/access_ui/) describes browser authentication.
- [LXD 6.9 authentication flows](https://github.com/canonical/lxd/blob/ab8fad2/doc/howto/server_expose.md) distinguishes certificate and identity tokens.
- [LXD 6.9 identity CLI](https://github.com/canonical/lxd/blob/ab8fad2/lxc/auth.go) covers nonterminal certificate input.
- [Grafana initial administrator password](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#admin_password) explains first-run initialization.
- [Prometheus management API](https://prometheus.io/docs/prometheus/latest/management_api/) documents SIGHUP configuration reload without enabling the HTTP lifecycle API.
- [LXD metrics setup](https://canonical.com/lxd/docs/latest/metrics/) documents the endpoint and metrics certificate.
- [Provided LXD metrics](https://canonical.com/lxd/docs/latest/reference/provided_metrics/) defines the metric families.
- [LXD Grafana integration](https://canonical.com/lxd/docs/latest/howto/grafana/) covers the upstream dashboard and UI link.
- [LXD UI URL builder](https://github.com/canonical/lxd-ui/blob/main/src/util/grafanaUrl.tsx) defines instance/project link substitution.
- [Prometheus installation](https://prometheus.io/docs/prometheus/latest/installation/) covers containerized operation and persistence.
- [Grafana Docker configuration](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/) describes configuration and file-backed secrets.
- [LXD permissions](https://canonical.com/lxd/docs/latest/reference/permissions/) distinguishes viewer access from administrative access.
