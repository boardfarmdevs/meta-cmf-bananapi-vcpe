# em_ctrl crashes when a new agent onboards: a data model built from the network keeps stack garbage as its radio count

**Component:** controller (`onewifi_em_ctrl`), `src/dm/dm_easy_mesh.cpp`,
`src/ctrl/dm_easy_mesh_ctrl.cpp`. **Base:** upstream `1ef3cfd3`. **Patch:**
[0001](0001-ctrl-initialise-the-counts-of-a-data-model-built-fro.patch).

## What happens

The controller crashed (SIGSEGV) when an agent onboarded for the first time. Its backtrace:

```
dm_radio_t::operator=(dm_radio_t const&)
dm_easy_mesh_t::operator=(dm_easy_mesh_t const&)   dm_easy_mesh.cpp, the radio copy loop
em_cmd_t::init(dm_easy_mesh_t&)
em_cmd_bsta_cap_t::em_cmd_bsta_cap_t(em_cmd_params_t, dm_easy_mesh_t&)
dm_easy_mesh_ctrl_t::analyze_bsta_cap_req(em_bus_event_t*, em_cmd_t**)
```

The faulting address was just past the top of the stack. Before the crash, the controller had
already rejected every agent's Topology Response for a while: the heap was corrupted first.

## Cause

`analyze_bsta_cap_req()`, `analyze_sta_link_metrics()` and `analyze_unassoc_sta_metrics_query()`
start with `dm_easy_mesh_t dm = *this;`. The controller (`dm_easy_mesh_ctrl_t`) is a
`dm_network_t`, so this constructs `dm` with `dm_easy_mesh_t(const dm_network_t&)`. That
constructor initialises only `m_wifi_data`, so `m_num_radios` and the other counts hold whatever
was on the stack. `em_cmd_t::init()` then copies `dm` into the command, and `operator=` copies
`obj.m_num_radios` radios into `m_radio[EM_MAX_BANDS]`, however many that is:

- with a moderate value, the copy writes past `m_radio` into the heap-allocated command and what
  follows it;
- with a large one, it reads off the top of the stack and the process dies.

The outcome depends on the stack's contents, so the crash is intermittent. Three related
unbounded appends make the same overflow reachable from the wire or from a model:
- both Radio Basic Capability handlers take `get_radio(get_num_radios())`, which is NULL at
  `EM_MAX_BANDS`, and dereference it;
- `put_radio`, `commit_config()`'s new radio, the `em_insert` orchestration, the RadioList decode,
  the policy request and the radio-enable target all write `m_radio[m_num_radios]` without a
  check;
- the policy request's guard compares against `EM_MAX_RADIO_PER_AGENT` (4) for an array of
  `EM_MAX_BANDS` (3).

## Minimal reproduction

Deterministic, without a network: construct a model from a network over memory that is not
zero, as the stack is.

```cpp
alignas(dm_easy_mesh_t) unsigned char memory[sizeof(dm_easy_mesh_t)];
memset(memory, 0xa5, sizeof(memory));
dm_network_t net;
dm_easy_mesh_t *dm = new (memory) dm_easy_mesh_t(net);
// upstream: dm->m_num_radios == 0xa5a5a5a5; copying *dm copies that many radios
```

`gen/tests/controller-radio-array-bounds-test.py SRC` compiles exactly this from the source
tree, together with the copy (a source that claims 1000 radios) and both handlers' new-radio step
(a full array). On upstream it fails at the first assertion.

In a network: an agent that onboards for the first time makes the controller run
`analyze_bsta_cap_req()` (its Backhaul STA Capability Query). Whether it crashes then depends on
the stack.

## Fix

- `dm_easy_mesh_t(const dm_network_t&)` delegates to the default constructor, which zeroes the
  counts.
- `operator=` copies at most `EM_MAX_BANDS` radios.
- Every radio append checks the array first and logs what it drops.
- The policy guard uses `EM_MAX_BANDS`.

The change is platform-independent.

## Verification

- The check above passes with the patch on upstream and on the lab's tree.
- In the lab (RDK-B gateway image with the patch, 8 October 2026): agents onboarding for the
  first time, physical pods among them, without a crash. The health audit passed (model,
  identities, ownership, services, traffic to 100 clients). An 8-hour soak followed.
