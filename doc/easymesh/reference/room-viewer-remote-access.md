# Room viewer: local and internet access

## Scope and short answer

**The existing room-viewer transport can cross the internet.** The browser
uses ordinary HTTP requests and Server-Sent Events (SSE), not a local-only
radio protocol. Serving the viewer and its API through the same protected
address needs deployment configuration, not a new viewer transport.

**This document is a design and deployment guide, not an implemented remote
access feature.** No public endpoint, tunnel, proxy, certificate, firewall
change, or connection selector is enabled by this document. Examples require
installation-specific values and subsequent validation. See
[current state](../current-state.md) for accepted deployments and live URLs.

There are two different meanings of “connect to another host”:

| Requirement | Existing capability |
| --- | --- |
| Open the viewer at a local machine's IP and port | Yes, when the room server is listening and reachable there |
| Open that host's viewer over an SSH tunnel or VPN | Yes; no application change required |
| Open that host's viewer through an authenticated HTTPS gateway | Compatible with the current HTTP/SSE API; requires gateway setup and testing |
| Keep the GitHub Pages viewer open and select a different API host | No; endpoint selection and cross-origin support are not implemented |
| Send raw virtual-radio traffic from the browser to wmediumd | Neither required nor how the viewer works |

The lowest-complexity approach is **one lab origin serving both `/viewer/`
and `/api/demo/`**. A local lab can be the default destination; an internet
lab differs only in how that destination is reached and protected.

## 1. What actually travels over the network

```text
Operator's browser
  3D rendering and drag preview
       |
       | HTTP(S): JSON reads, revisioned writes, SSE events
       v
SSH/VPN or authenticated HTTPS gateway
       |
       | private connection to the appliance room server, port 8891
       v
EasyMesh appliance VM
  room-demo server + authoritative room engine + optimizer
       |                                 |
       | local Unix control socket       | local controller API / lxc
       v                                 v
  wmediumd <---- mac80211_hwsim ----> EasyMesh and client containers
```

Only presentation state, telemetry, world geometry and control requests cross
the WAN. Rendering happens in the browser; movement timing, RF application,
readback, steering and traffic checks remain in the appliance. Internet
latency affects display freshness and command acknowledgement, not the local
virtual-radio medium's clock. This does not distribute hwsim radios or
bridge the simulated WLAN across hosts.

The room engine accesses `/run/wmediumd-control.sock` using
`AF_UNIX`/`SOCK_SEQPACKET`. That interface is local to the lab; it is not an
internet TCP service. Do not expose it, the LXD API, or individual containers
to make the viewer work. Run `room-demo` in the appliance environment where
the socket, controller API and local `lxc` operations are available, not on
the operator's laptop or a standalone public relay.

### Current HTTP contract

| Path | Purpose | Backend authorization today |
| --- | --- | --- |
| `/viewer/`, `/viewer/manual.html`, `/viewer/...` | Viewer, manual and bundled assets | No login |
| `GET /healthz` | Process/run status, not a complete mesh health check | No login |
| `GET /api/demo/current` | Initial state and current run identity/revision | No login |
| `GET /api/demo/world` | Live world's geometry and bindings | No login |
| `GET /api/demo/events` | Ordered, long-lived SSE stream | No login |
| `GET /api/demo/events.json` | Event history for replay | No login |
| `GET /api/demo/interactions` | Interactive capabilities and state | No login; interactive server only |
| `GET /api/demo/recording/world` | Recorded world download | No login; interactive server only |
| `POST`, `PUT`, `DELETE` interactive endpoints | Lease, position/presence, movement and recording control | Run-scoped bearer capability; lease and revision rules depend on operation |

The live viewer fetches `/api/demo/current`, loads its `world_url`, then
opens `EventSource('/api/demo/events?after=...')`. These URLs target the
**page's origin**, not an IP embedded in the world. There is no configurable
browser API base URL. Replay and recorded-world downloads also use
root-relative API paths. No WebSocket upgrade or browser-to-radio UDP port
is involved.

The server's default bind is `127.0.0.1:8891`. A VM management-address bind,
or `--listen 0.0.0.0:8891` with appropriate firewall restrictions, is needed
for access from outside that VM. The CLI's `--base-url` means the
**controller API** (default `http://127.0.0.1:8888`), not the viewer's remote
endpoint. Changing it is not how a browser selects another lab.

### Same origin and authentication matter

Browser origins include scheme, host and port. Currently, interactive writes
with an `Origin` header compare its parsed host/port with the request `Host`;
a mismatch returns `403 origin_mismatch`. This is a host/port check, not a
complete scheme-aware origin policy. The updated rev140 room has no operator
capability check, including for requests without `Origin`. The server has neither CORS response headers nor an
`OPTIONS` preflight handler.

Consequently, a reverse proxy must preserve the browser-facing `Host`,
including any non-default port, and leave `Origin` intact. Replacing `Host`
with `127.0.0.1:8891` breaks legitimate proxied writes. Adding CORS headers
alone would not make a separate-origin interactive viewer work.

The rev140 overlay removes operator-token generation, browser prompts and
bearer checks. Anyone admitted to the interactive backend can acquire a free
control lease. `mode=live` hides controls but does not authorize users. The
unchanged rev150/rev120 deployments and original 0906 tars retain their previous
capability behavior until updated separately.

Protect all paths at the network/gateway layer. For WAN use, gateway
authentication is required; implement read-only versus control authorization
there if those audiences differ. The backend is Python's
`ThreadingHTTPServer`, not an internet-facing service with built-in TLS,
user management or admission limits. Python explicitly cautions against using
`http.server` as a production web server; putting a gateway in front does not
remove the need to limit trusted users and resource consumption.
[Python HTTP server documentation](https://docs.python.org/3/library/http.server.html).

## 2. Local machine by IP and port: works now

With the room service running, open its own viewer rather than a separately
hosted copy:

```text
http://LAB_HOST_IP:18891/viewer/?mode=live
http://LAB_HOST_IP:18891/viewer/?mode=interactive
```

Here `18891` represents an outer-host forwarding port to the appliance's
`8891`; use the actual published port for the installation. If the browser
can route directly to the VM's management interface, use
`http://VM_MANAGEMENT_IP:8891/viewer/?mode=live` instead. A forwarded outer
port and the inner server port are different network hops, not two APIs.

All API calls automatically use the same IP and port as the opened page.
`mode=live` observes; `mode=interactive` offers controls and acquires a lease
without an operator prompt on the updated rev140 service. Visiting the room server's `/` redirects
to `/viewer/?mode=live`. Omitting `mode` from `/viewer/` does not request a
live connection; use the explicit live URL.

Plain HTTP does not encrypt lease tokens or telemetry, even on a LAN. Use it
only where that risk is acceptable in an isolated trusted lab; prefer an SSH
tunnel or HTTPS for shared networks. `127.0.0.1` in a browser refers to the
browser's machine, not a remote lab VM, unless a local tunnel supplies the
connection.

Starting or restarting `room-demo` can apply or restore RF. Use the existing
[interactive room manual](../live-room-demo/interactive-room-manual.md) to
operate it; do not start a second room process merely to expose a new URL.

## 3. Remote operator: SSH tunnel or VPN

### SSH forwarding through the outer lab host

Prerequisites: a reachable SSH service on the outer host, verified host key,
authorized key-based login, forwarding permission, and reachability from
that host to the VM's room listener. Guest SSH is not needed for this route.
On the operator's laptop, the illustrative command is:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18891:VM_MANAGEMENT_IP:8891 \
  labuser@ssh.lab.example.net
```

Then open `http://127.0.0.1:18891/viewer/?mode=live`, or replace `live` with
`interactive`. The browser and API share the tunnel origin, so CORS changes
are unnecessary. Keep SSH running; closing it disconnects this access path.
The laptop listener is loopback-only. The WAN leg is encrypted; the
outer-host-to-VM leg must stay on a trusted private network.
[OpenSSH forwarding reference](https://man.openbsd.org/ssh#L).

If the room server listens only on **VM loopback**, the previous forwarding
target cannot reach it. An alternative, after separately enabling and
hardening guest SSH, is:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -J labuser@ssh.lab.example.net \
  -L 127.0.0.1:18891:127.0.0.1:8891 \
  easymesh@VM_MANAGEMENT_IP
```

In that form the forwarding destination is resolved in the final SSH host,
the VM. Guest SSH setup prerequisites are described in the
[container monitoring guide](lxd-ui-and-monitoring.md). Do not assume SSH is
already enabled in an imported appliance.

`ExitOnForwardFailure` detects listener setup failure, not whether the room
service behind the tunnel is healthy. Verify `/healthz` and SSE separately.
[OpenSSH client configuration](https://man.openbsd.org/ssh_config#ExitOnForwardFailure).

### VPN alternative

An approved VPN can give the laptop a private route to the lab host or VM.
Open the viewer at that reachable private address, keeping assets and API
on one origin. Restrict the VPN policy to authorized users and the room
listener; it need not grant access to every container or LXD administration.
Validate routing, overlapping home/lab subnets, and firewall rules. A VPN
does not create a listener on an otherwise loopback-only VM service.

For a small operator group, this or SSH is preferable to publishing a new
web service. Neither requires a change to the room-viewer code.

## 4. Shared internet URL: authenticated HTTPS gateway

Use this when operators should open a normal URL such as:

```text
https://lab.example.net/viewer/?mode=live
https://lab.example.net/viewer/?mode=interactive
```

`lab.example.net` is a placeholder, not a deployed service. The deployment
would require the following:

1. Choose a DNS name and obtain a trusted server certificate for it. Arrange
   renewal, key protection and a default-deny virtual host for other names.
2. Choose access control for **every** viewer/API path. The example below
   uses a dedicated client-certificate CA and mutual TLS (mTLS). Issue a
   separate certificate per authorized person and import it into their
   browser. Define expiry and revocation procedures before publishing.
3. Give the gateway a private path to exactly one room backend. The sample
   upstream `127.0.0.1:28891` is a gateway-local tunnel listener, not a port
   the appliance creates automatically. A private VPN backend is another
   option. Do not carry the upstream HTTP connection over the open internet.
4. Publish only the authenticated HTTPS listener. Keep backend ports `8891`,
   `18891`, and `28891` private wherever they are used. Do not forward the
   controller API, wmediumd console, LXD API or radio sockets as dependencies.
5. Preserve `/viewer/`, `/api/demo/` and `/healthz` at the origin root. Prefer
   separate hostnames for separate labs, rather than `/lab-a/` prefixes that
   conflict with the viewer's root-relative URLs. Do not load-balance one
   run across independent room engines or replay an uncertain write against
   a different backend.

The following is an **illustrative Nginx server block**, not an installed
file. Place it in an appropriate `http` context only after providing the
certificates, backend connection and surrounding host/security configuration:

```nginx
server {
    listen 443 ssl;
    server_name lab.example.net;

    ssl_certificate /etc/nginx/tls/lab-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/lab-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_client_certificate /etc/nginx/tls/room-users-ca.pem;
    ssl_verify_client on;
    ssl_verify_depth 2;

    client_max_body_size 64k;
    client_header_timeout 10s;
    client_body_timeout 10s;

    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header Connection "";
    proxy_set_header Authorization $http_authorization;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 75s;
    proxy_next_upstream off;
    gzip off;

    location = / {
        return 302 /viewer/?mode=live;
    }
    location /viewer/ {
        proxy_pass http://127.0.0.1:28891;
    }
    location /api/demo/ {
        proxy_pass http://127.0.0.1:28891;
    }
    location = /healthz {
        proxy_pass http://127.0.0.1:28891;
    }
    location / {
        return 404;
    }
}
```

Buffering and caching are disabled so events reach the browser promptly.
`proxy_read_timeout` measures the gap between upstream reads; it is not a
maximum run duration. The room server emits a keepalive comment after ten
seconds without events. Any additional ingress/CDN must also permit
long-lived, unbuffered responses. No WebSocket `Upgrade` header is needed.
[Nginx proxy reference](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).

Client-certificate authentication does not consume the room API's bearer
header. Certificate-chain verification and client revocation configuration
belong to the gateway, not to the room engine.
[Nginx TLS reference](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).
The example does not provide a CA, certificate issuance, a revocation list,
automatic renewal, or a complete denial-of-service policy.

A same-origin, cookie-session SSO gateway is another design, provided it
protects SSE and preserves `Authorization: Bearer ...` for room writes. Do
not simply add HTTP Basic authentication or a second bearer requirement:
those also use `Authorization` and conflict with the room capability.
Gateways must not inject an operator token for every viewer. Observation and
RF authority must remain separate.

### Lab behind NAT or CGNAT

A public relay can run the HTTPS gateway while the lab initiates an outbound
SSH tunnel. No inbound connection to the lab router is required. From the
outer lab host, an illustrative reverse forward is:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -R 127.0.0.1:28891:VM_MANAGEMENT_IP:8891 \
  room-tunnel@relay.example.net
```

This supplies the gateway-local upstream used above. The final VM target
must be reachable from the machine running this command. Keep the relay
listener on loopback and allow access only through the authenticated proxy.
[OpenSSH reverse forwarding](https://man.openbsd.org/ssh#R).

Use a dedicated tunnel key/account, verify the relay host key, and restrict
the account to the required remote forward, with no general shell access.
Constrain `PermitListen` to `127.0.0.1:28891` and retain `GatewayPorts no`;
do not make the unauthenticated upstream public.
[OpenSSH server controls](https://man.openbsd.org/sshd_config#PermitListen).
If made persistent later, supervise reconnection and verify backend health;
a live SSH process alone is not a lab acceptance result.

## 5. Why GitHub Pages cannot simply target an arbitrary lab today

The published `mode=no-connect` viewer is deliberately browser-only. Changing
it to `mode=live` makes it request `/api/demo/current` **on the Pages origin**,
where the room server does not exist. An `api`, `host`, or `port` query
parameter has no implemented connection-selection meaning.

Even with a future API URL setting, browser security still applies:

- A different scheme, hostname or port is a different origin. Cross-origin
  JSON writes and authorization headers require a CORS preflight, which the
  current backend does not serve. Responses would need an exact allowed
  viewer origin, not a wildcard credential policy.
  [MDN CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- HTTPS pages ordinarily cannot fetch arbitrary HTTP APIs as active mixed
  content. Loopback and browser-specific local-network exceptions are not a
  portable remote-access design; use HTTPS for an internet API.
  [MDN mixed-content guide](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Mixed_content).
- Public-site access to LAN/loopback addresses can require a local-network
  permission. Chrome documents permission-gated exceptions to mixed-content
  checks for some local destinations. Behavior depends on browser and
  policy; neither CORS nor permission creates network reachability. Do not
  disable browser security or assume historical Private Network Access
  preflight headers are a universal solution.
  [Chrome Local Network Access guidance](https://developer.chrome.com/blog/local-network-access).
- Native `EventSource` has no arbitrary request-header option. The current
  stream sends no custom Authorization header. A separate-origin
  authenticated stream would need an appropriate session design or a
  different streaming client, not a token placed in the event URL.
  [EventSource constructor](https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource).

The uncomplicated solution is to **navigate to the lab's own viewer**. A
link from Pages to that page does not turn the live API into a cross-origin
browser fetch. The gateway serves the matching viewer/assets and backend
from one address.

## 6. Proposed local-default connection experience

This section is a future UI design, **not an available setting**.

### Recommended first step: choose a lab and open its viewer

Provide a small **Connect to lab** destination selector rather than first
making every API call cross-origin:

1. When already served by a room server, keep its own origin as the default.
   This is the existing live transport behavior.
2. For a launcher or static viewer, prefill an installation-configured local
   address such as `http://LAB_HOST_IP:18891`. Allow an explicit remote HTTPS
   address or a remembered, previously confirmed destination to override it.
3. **Connect** opens that origin's `/viewer/?mode=live`. The user can then
   choose interactive operation and separately supply the run capability.
   Navigating to a local IP is different from probing it from Pages.
4. Preserve `mode=no-connect` as an explicit offline choice. Do not have
   Pages silently scan private addresses, request local-network permissions,
   or acquire an RF lease on page load.
5. Remember only a non-secret destination if requested. Show the connected
   origin and run ID prominently. Never carry an operator/lease token to a
   different destination, including after redirects.

Thus the user's normal local machine can be the default **by its IP/port**,
without a new radio transport or CORS support. The connection selector itself
would still require a small future UI change. Today, a bookmark to the local
live URL provides the same destination behavior. Do not hard-code a private
lab address as the default for everyone using the public Pages site.

### Larger alternative: change the API host without leaving the page

If retaining the same static viewer page is a hard requirement, a later
implementation would need all of the following, not merely one `fetch` edit:

- One validated backend-origin resolver used for initial state, SSE,
  interactions, replay, recording export, and server-provided `world_url`.
  Permit only expected HTTP(S) origins; reject URL credentials and unexpected
  cross-origin response URLs before sending capabilities.
- Explicit CORS `OPTIONS` support and a strict full-origin allowlist, plus a
  deliberate replacement for the current write-origin check. Permit only
  required methods (`GET`, `POST`, `PUT`, `DELETE`) and request headers
  (`Content-Type`, `Authorization`, `If-Match`, and applicable event resume
  headers); expose `ETag` if the client reads it. Emit `Vary: Origin` for
  origin-dependent responses, including errors. CORS is not authentication.
- A compatible read/session-authentication mechanism for fetch and SSE.
  Cross-origin cookies would need explicit client credentials options,
  server credential permission, and suitable cookie attributes; browser
  third-party-cookie policy can still block them. Do not use URL secrets.
- Connection switching that closes the old stream, clears queued commands
  and capabilities, and best-effort releases the old lease. Re-read run
  identity and revisions before offering control on the new lab. Never
  silently fail over an active RF session to a different local/remote lab.
- Explicit disconnected/stale state, bounded reconnect behavior, and tests
  for browser permissions, certificate failures, run restarts and WAN loss.

These changes are intentionally not implemented here. A fixed-upstream,
same-origin proxy avoids most of them; an unrestricted public “proxy this
URL” endpoint would instead create a server-side request-forgery risk.

## 7. Disconnects, latency and RF safety

The server can resume an event stream using `Last-Event-ID` or `?after=N`,
and the live viewer uses native EventSource reconnection after an established
stream fails. SSE is a persistent HTTP response, not repeated polling.
[SSE behavior](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).

Resume applies to the **same run** and its event sequence. The current viewer
does not implement a full new-run recovery handshake after a server restart;
reload the page and obtain fresh state/capability if the run changes. If the
initial fetch fails before EventSource is created, reload after connectivity
is restored. Do not infer automatic restart recovery from the word
“reconnecting.”

Interactive leases default to 30 seconds and the viewer normally renews
halfway through that interval. A prolonged outage, suspended laptop or
background-tab throttling can lose the lease. Accepted room state remains;
lease expiry cancels owned movement and freezes the last accepted position.
It does **not** restore the baseline or stop the server-side optimizer. A
scripted run also continues independently of its observers.

Pointer movement is a local preview; the final drag release submits the RF
change. A destination walk runs on the server, not on browser animation
ticks. On a lost acknowledgement, inspect accepted state/revision before
retrying; do not blindly replay a possibly accepted command with a new ID.
Keep the existing command IDs, revision checks and single-writer ownership.

Closing a tunnel, revoking web access or closing a tab is not **Stop and
restore**. Use the server's handled shutdown and verify exact restoration as
described in the [interactive room manual](../live-room-demo/interactive-room-manual.md).
Maintain a separate administrative recovery path before permitting remote
RF control. Access revocation procedures must also consider already-open
SSE connections and existing control leases, not just the next page load.

## 8. Validation before publishing an endpoint

These are checks for a future deployment, not claims that WAN access was
tested as part of writing this document:

1. **Backend:** from the intended proxy/tunnel endpoint, read `/healthz` and
   `/api/demo/current`; confirm the intended run and world. Check the full
   lab health separately using the established acceptance procedure.
2. **Access boundary:** outside the trusted network, direct backend ports
   must be unreachable. Without the gateway identity, viewer assets, JSON,
   recording exports and SSE must all be denied. With an authorized identity,
   the gateway's read/control policy must determine access, not the viewer mode.
3. **Browser:** load `/viewer/?mode=live` and its manual; confirm all assets
   and API requests stay on the intended origin. Inspect for certificate,
   mixed-content, CORS, buffering and stale-state errors.
4. **Streaming:** events should arrive incrementally with increasing IDs.
   Test an idle interval, reconnect within one run, a long session beyond
   proxy idle timeouts, and a separate run restart requiring a fresh page.
5. **Control, in an approved test window:** if observer-only identities exist,
   the gateway must reject their mutation requests. Verify one-browser lease
   ownership, stale-revision rejection, an acknowledged drag, and a
   destination movement through the public URL. This catches forwarded
   `Host`/`Origin` mistakes that read-only checks miss.
6. **Loss and recovery:** interrupt only the test browser's access path;
   verify movement/lease behavior, reconnect, then stop the room through the
   administrative path and confirm exact RF restoration and full lab health.
   Keep evidence with run IDs and timings, but no credentials.

For the mTLS example, read-only command-line probes would be:

```bash
curl --fail --show-error --silent \
  --cert room-user.crt --key room-user.key \
  https://lab.example.net/healthz

curl --fail --show-error --no-buffer --max-time 15 \
  --cert room-user.crt --key room-user.key \
  https://lab.example.net/api/demo/events
```

These certificate paths are placeholders for private, per-user files. Keep
server certificate verification enabled; use an explicitly trusted CA file
if necessary, not `--insecure`. The SSE probe intentionally times out after
15 seconds, so curl exit code 28 is expected if the stream remains open;
inspect the received events/keepalive rather than treating that alone as a
failure. Do not paste TLS private keys or operator tokens into bug reports.

Before ongoing use, also test certificate renewal/revocation, supervised
tunnel reconnection, expected concurrent observers and resource limits. Each
SSE observer holds a backend connection/thread; this is a trusted lab service,
not an anonymously scalable public streaming platform. Validate gateway
configuration before activation and retain a way to revert it. Removing the
gateway/tunnel removes remote access, not the running lab or its RF changes.

## 9. Implementation references

The existing behavior described here can be traced to:

- [Viewer source](../../../gen/wmediumd/configurator/worlds/viewer/index.html):
  mode selection, `apiJson`, `connectLive`, `connectReplay`, and lease renewal.
- [Room HTTP server](../../../gen/demo/room_demo/server.py): routes,
  `_events`, `_require_same_origin`, and revision checks.
- [Room CLI](../../../gen/demo/room_demo/cli.py): listener defaults,
  controller base URL and shutdown/restoration.
- [Interaction state](../../../gen/demo/room_demo/interactions.py) and
  [room engine](../../../gen/demo/room_demo/engine.py): lease expiry,
  movements, serialized mutations and RF ownership.
- [wmediumd control client](../../../gen/wmediumd/configurator/wmdcfg/actuator.py):
  local sequenced-packet socket transport.
- [HTTP contract tests](../../../gen/demo/tests/test_server.py): SSE,
  capability enforcement, cross-origin write rejection and control routes.

For setup and RF operations, continue with the
[interactive room manual](../live-room-demo/interactive-room-manual.md).
For container administration and monitoring, use the separate
[LXD UI and monitoring guide](lxd-ui-and-monitoring.md); its credentials and
ports are not part of the room-viewer transport.
