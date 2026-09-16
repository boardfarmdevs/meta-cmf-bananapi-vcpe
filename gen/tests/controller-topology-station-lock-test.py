"""Verify station-map mutation is serialized with topology publication."""

from pathlib import Path
import sys


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for position in range(opening, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start : position + 1]
    raise AssertionError(f"unterminated function: {signature}")


root = Path(sys.argv[1])
source = (root / "src/em/config/em_configuration.cpp").read_text()
assert '#include "em_network_topo.h"' in source
assert "std::recursive_mutex g_network_topology_mutex;" in source
topology_source = (root / "src/ctrl/em_network_topo.cpp").read_text()
assert "std::recursive_mutex g_network_topology_mutex;" not in topology_source

body = function_body(
    source,
    "int em_configuration_t::handle_topology_notification",
)
lock = body.index("std::unique_lock<std::recursive_mutex> topology_lock")
disassociation = body.index("if (assoc_event == false)", lock)
live_remove = body.index("remove_non_mlo_sta_assoc(dm, sta_info)", disassociation)
association_put = body.index("hash_map_put(dm->m_sta_assoc_map", live_remove)
unlock = body.index("topology_lock.unlock()", association_put)
dispatch = body.index("get_mgr()->io_process(em_bus_event_type_sta_assoc")

assert lock < disassociation < live_remove < association_put < unlock < dispatch
assert body[lock:dispatch].count("topology_lock") == 2

print(
    "PASS: topology-notification station-map mutation holds the publication "
    "mutex and releases it before association event dispatch"
)
