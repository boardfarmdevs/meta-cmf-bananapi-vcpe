# Optional remote access gateway

The [setup and operator manual](../../doc/easymesh/reference/deployment/remote-access.md)
owns installation, Tailscale Serve/Funnel publication, exclusive sessions,
firewall scope, maintenance and rollback.

- `install-host.sh`: installs dependencies and systemd units on the outer host;
  does not expose services, change the VM or enable VM autostart.
- `manage.py`: discovers a named RDK VM, manages users, publishes selected
  endpoints, controls maintenance, and removes only its own firewall/Serve state.
- `gateway.py`: loopback HTTP/SSE/WebSocket proxy and browser portal. All views
  share one authenticated, time-limited reservation.
- `remote_state.py`: transactional persistent reservation/session storage.

Use the manual's private-access procedure first. **Never publish the backend
ports directly with Funnel**; use the gateway listeners and keep its firewall
enabled. Native control services and RF behavior remain unchanged.
