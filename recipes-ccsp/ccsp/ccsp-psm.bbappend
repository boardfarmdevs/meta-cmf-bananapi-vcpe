vcpe_patch_bbhm() {
    cfg="${D}/usr/ccsp/config/bbhm_def_cfg.xml"
    if [ -f "$cfg" ]; then
        sed -i \
            -e 's|\(dmsb\.ethagent\.ethifcount[^>]*>\)4<|\11<|' \
            -e 's|\(dmsb\.wanmanager\.if\.1\.Name[^>]*>\)[a-z0-9]*<|\1eth0<|' \
            -e 's|\(dmsb\.ethlink\.1\.baseiface[^>]*>\)[a-z0-9]*<|\1eth0<|' \
            -e 's|\(dmsb\.vlanmanager\.1\.baseinterface[^>]*>\)[a-z0-9]*<|\1eth0<|' \
            -e 's|\(dmsb\.l2net\.1\.Members\.Eth[^>]*>\)[^<]*<|\1eth1<|' \
            "$cfg"
        if ! grep -q 'dmsb\.ethagent\.if\.1\.Name' "$cfg"; then
            sed -i 's|\(.*dmsb\.ethagent\.ethifcount.*\)|\1\n  <Record name="dmsb.ethagent.if.1.Name" type="astr">eth0</Record>|' "$cfg"
        fi
    fi
}
do_install[postfuncs] += "vcpe_patch_bbhm"
