# Optional nested-LXD visibility

Run this setup inside the Ubuntu appliance VM, not inside a Yocto/Alpine
container and not on the physical outer LXD host.

The complete installation, browser authentication, SSH tunneling, dashboard,
validation, backup and rollback procedure is in
[LXD UI and container monitoring](../../../../doc/easymesh/reference/lxd-ui-and-monitoring.md).

```sh
sudo bash setup.sh rev140-0905
cd /opt/easymesh-observability
sudo docker compose config --quiet
sudo docker compose pull
sudo docker compose up -d
```

Nothing runs automatically from this source directory. Setup installs copies
under `/opt/easymesh-observability`, generates local credentials, trusts only
a metrics certificate, and configures loopback HTTPS listeners. Docker uses
host networking to reach those listeners without adding a bridge or LXD node.
There is no Docker/LXD socket mount, privileged exporter or nested-container agent.

Do not export an enabled monitoring installation in a thin release: it contains
per-installation credentials and persistent time-series data. Disable and clean
it using the reference guide first. Ship these templates only.
