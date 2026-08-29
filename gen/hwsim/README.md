# hwsim module build

`build-hwsim.sh` obtains the source matching the running Ubuntu kernel, applies
the lab patches, and builds an out-of-tree `mac80211_hwsim.ko`. Linux 6.8 and
7.0 are supported; the optional kernel-medium evaluation is accepted only on
Linux 7.0.

Normal build and installation:

```sh
gen/hwsim/build-hwsim.sh --6ghz --install
```

This preserves the default data path: the kernel option remains disabled and
the lab starts userspace wmediumd.

An isolated VM can explicitly load the experimental kernel backend:

```sh
HWSIM_KERNEL_MEDIUM=1 gen/hwsim/build-hwsim.sh --6ghz --load
```

Never use `--load` while a BPI or WLAN-client container owns an hwsim PHY. For
the complete design, controls, results, and limitations, see
[the kernel-medium reference](../../doc/easymesh/reference/hwsim-kernel-medium.md).

The destructive two-radio QEMU evaluator is:

```sh
sudo gen/hwsim/tests/evaluate-medium-backends.py \
  --duration 10 --rate 20M --output /tmp/medium-eval.json
```

Run it only in an isolated VM with the lab stopped.
