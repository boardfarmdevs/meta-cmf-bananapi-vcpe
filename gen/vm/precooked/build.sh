#!/usr/bin/env bash
set -euo pipefail

vm_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$vm_dir"

case "${1:-all}" in
prepare)
    exec "$vm_dir/prepare-assets.sh"
    ;;
up)
    "$vm_dir/prepare-assets.sh"
    exec vagrant up --provision
    ;;
test)
    vagrant ssh -c 'sudo systemctl start easymesh-lab.service'
    vagrant ssh -c 'sudo systemctl --no-pager status boardfarm-lab.service easymesh-lab.service'
    vagrant ssh -c 'bash /home/vagrant/health-audit.sh'
    ;;
reboot-test)
    vagrant reload
    vagrant ssh -c 'sudo systemctl start easymesh-lab.service'
    vagrant ssh -c 'sudo systemctl --no-pager status boardfarm-lab.service easymesh-lab.service'
    vagrant ssh -c 'bash /home/vagrant/health-audit.sh'
    ;;
package)
    mkdir -p artifacts
    box_output=${EASYMESH_BOX_OUTPUT:-artifacts/easymesh-lab-$(date -u +%Y%m%dT%H%M%SZ).box}
    vagrant ssh -c 'sudo /usr/local/sbin/easymesh-package-cleanup'
    vagrant halt
    vagrant package --output "$box_output"
    sha256sum "$box_output" | tee "$box_output.sha256"
    ;;
all)
    "$vm_dir/prepare-assets.sh"
    vagrant up --provision
    "$0" reboot-test
    "$0" package
    ;;
*)
    echo "usage: $0 {prepare|up|test|reboot-test|package|all}" >&2
    exit 2
    ;;
esac
