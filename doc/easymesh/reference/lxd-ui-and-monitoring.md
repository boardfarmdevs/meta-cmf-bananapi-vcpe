# Nested LXD web UI and container monitoring

Audience: operators who want to inspect the containers **inside** an EasyMesh
LXD VM, then graph their CPU, memory, interface traffic, disk I/O and processes.

This is an opt-in management-plane addition. It does not start automatically
when the lab is built or imported, change RF conditions, install agents in the
Yocto/Alpine containers, or change the immutable client profile. Consult
[current state](../current-state.md) for release acceptance; enabling monitoring
does not turn a failed lab audit into a pass.

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
| `setup.sh` | Install configuration, generate credentials, enable loopback LXD listeners |
| `disable.sh` | Stop this Compose project, revoke its metrics certificate, restore owned LXD settings |
| `compose.yaml` | Version-pinned Prometheus and Grafana services with persistent volumes |
| `.env.example` | Image references and browser-facing Grafana URL |
| `prometheus.yml` | Authenticated nested-LXD scrape and Prometheus self-monitoring |
| `grafana/provisioning/datasources/prometheus.yml` | Provisioned data source, UID `lxd-prometheus` |
| `grafana/provisioning/dashboards/lxd.yml` | File-backed dashboard provisioning |
| `grafana/dashboards/lxd-containers.json` | Container dashboard, UID `easymesh-lxd` |

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
measured consumption. Prometheus keeps up to seven days or 1 GB of TSDB blocks,
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

Setup checks that it is running as root in a configured appliance with a
`bpibroadband` instance. It selects the local Unix-socket LXD server explicitly
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

Default listeners are intentionally inaccessible directly from the LAN. The
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
| Grafana | `http://127.0.0.1:13000` |

For rev150, change the jump host to `rev@192.168.2.150` and use its VM IP.
For simultaneous sessions, use local ports `28443`, `29090`, `23000` for that
second tunnel. Set its installed `.env` to
`GRAFANA_PUBLIC_URL=http://127.0.0.1:23000/` and recreate Grafana with
`docker compose up -d grafana`. The guest ports remain `8443/9090/3000`.

Do not bind SSH forwards to `0.0.0.0`. Do not expose unauthenticated Prometheus
on a host NAT proxy. If shared LAN access is required, deploy an authenticated
TLS reverse proxy and firewall allowlist as a separate, reviewed change;
retain client-certificate authentication for the administrative LXD endpoint.

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
3. In a private terminal inside the VM, run
   `lxc --force-local config trust add`. Give the browser a distinct name and
   supply its generated one-use trust token to the UI. This grants substantial
   management privilege; do not use it for Prometheus or share it in logs.
4. Select project `default` and the Instances page. Confirm the expected
   `bpibroadband`, `bpiap` through `bpiap-003`, and `wlan-client` through
   `wlan-client-019` roster. Compare with `lxc --force-local list` in the VM.

For read-only observers, use your LXD version's fine-grained authorization
groups and viewer entitlements instead of distributing administrator browser
certificates. Older restricted TLS certificates constrain projects but are
not equivalent to a read-only account. Audit `lxc config trust list` and revoke
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
  'http://127.0.0.1:13000/d/easymesh-lxd/easymesh-lxd?orgId=1&var-project={project}&var-name={instance}'
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
curl -fsS --max-time 10 http://127.0.0.1:3000/api/health
curl -fsS --max-time 10 http://127.0.0.1:9090/api/v1/targets \
  | jq '.data.activeTargets[] | {labels,health,lastError}'
curl -fsSG --max-time 10 http://127.0.0.1:9090/api/v1/query \
  --data-urlencode 'query=count(lxd_cpu_effective_total{job="lxd",type="container",project="default"})' \
  | jq '.data.result'
lxc --force-local list --format json | jq '[.[] | select(.status == "Running" and .type == "container")] | length'
ss -lnt | grep -E ':(8443|8444|9090|3000)\b'
```

For the running 20-client roster, both counts should be 25. A count mismatch
needs investigation, not a dashboard query that hides it. Verify that all four
listeners are on loopback. Also verify that a request **without** a metrics
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
| Metrics certificate denied | Verify its fingerprint and `metrics` type in nested LXD, not outer LXD; check expiry |
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

All lifecycle commands run **inside the VM**:

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
TSDB or Grafana database in a thin tar. The standard thin-package cleanup does
not know about this optional directory/Compose project: disable it, remove its
volumes/local credentials and any test UI trust/link configuration before
exporting. Retain only the source templates in the checkout. An offline
monitoring-image archive can be supplied separately without embedding secrets.

## Sources and relationship to the example

The [VCPE metrics example](https://www.vcpe.dev/docs/metrics.html) demonstrates
the LXD → Prometheus → Grafana flow. This implementation keeps that flow but
targets the nested daemon and replaces unauthenticated scraping/TLS bypasses
with a metrics-only certificate and verified TLS.

- [LXD UI access](https://canonical.com/lxd/docs/latest/howto/access_ui/) describes browser authentication.
- [LXD metrics setup](https://canonical.com/lxd/docs/latest/metrics/) documents the endpoint and metrics certificate.
- [Provided LXD metrics](https://canonical.com/lxd/docs/latest/reference/provided_metrics/) defines the metric families.
- [LXD Grafana integration](https://canonical.com/lxd/docs/latest/howto/grafana/) covers the upstream dashboard and UI link.
- [LXD UI URL builder](https://github.com/canonical/lxd-ui/blob/main/src/util/grafanaUrl.tsx) defines instance/project link substitution.
- [Prometheus installation](https://prometheus.io/docs/prometheus/latest/installation/) covers containerized operation and persistence.
- [Grafana Docker configuration](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/) describes configuration and file-backed secrets.
- [LXD permissions](https://canonical.com/lxd/docs/latest/reference/permissions/) distinguishes viewer access from administrative access.
