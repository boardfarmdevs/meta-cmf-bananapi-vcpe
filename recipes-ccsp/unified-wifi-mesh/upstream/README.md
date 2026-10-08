# unified-wifi-mesh: fixes to report upstream

The lab's unified-wifi-mesh patches that fix defects any deployment can meet, each ready to file
with RDK (rdkcentral/unified-wifi-mesh): a report with a minimal reproduction, and the patch
rebased on plain upstream.

| Lab patch | Report | Patch for upstream | Lab status |
| --- | --- | --- | --- |
| [0243](../unified-wifi-mesh/0243-ctrl-radio-count-initialised-and-the-radio-array-bounded.patch) | [em_ctrl crashes when a new agent onboards](0243-report.md) | [0001](0001-ctrl-initialise-the-counts-of-a-data-model-built-fro.patch) | in the gateway image since 8 October 2026 (image 15); its health audit passed, then an 8-hour soak with physical pods |

**Base.** Upstream commit `1ef3cfd3014296defd2c5b575584e5f1d8195e0f` (31 August 2026,
`v0.2.0-102-g1ef3cfd3`), the commit the lab's recipe builds. The patch applies with `git am`; the
lab's version is the same change on top of its own series.

**Check.** `python3 gen/tests/controller-radio-array-bounds-test.py SRC` takes a unified-wifi-mesh
source tree; on upstream it fails without the patch and passes with it.

Further reports are added here once RDK has received them.
