#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


parser = argparse.ArgumentParser(description="Race production HAL frame dispatch against registration teardown")
parser.add_argument("source", type=Path)
args = parser.parse_args()
source = args.source.read_text()
loop = function(source, "void *nl_recv_func(")
start = loop.rfind("        pthread_mutex_lock(", 0, loop.index("        if (mgmt_fd_isset("))
dispatch = loop[start:loop.index("#ifdef EAPOL_OVER_NL", start)]
assert dispatch.rstrip().endswith("pthread_mutex_unlock(&g_wifi_hal.hapd_lock);")
snapshot = loop[loop.index("prepare_interface_fdset(priv);"):loop.index("ret = select(")]
assert "pthread_mutex_unlock(&g_wifi_hal.hapd_lock);" in snapshot
assert "select(largest_fd + 1" in loop
for kind, handle, flag in (
    ("mgmt", "nl_event", "mgmt_frames_registered"),
    ("spurious", "spurious_nl_event", "spurious_frames_registered"),
):
    registration = function(source, "static int nl80211_register_" + kind + "_frames_locked(")
    assert registration.index("nl_socket_set_nonblocking((struct nl_sock *)interface->" + handle) < registration.index("interface->" + flag + " = 1;")
wrappers = "\n".join(function(source, result + " nl80211_" + operation + "_" + kind + "_frames(")
                     for kind in ("mgmt", "spurious")
                     for operation, result in (("register", "int"), ("unregister", "void")))
program = r'''
#include <cassert>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
struct nl_sock { bool active = false; };
struct wifi_interface_info_t {
    char name[8] = "wifi1";
    int index = 1, nl_event_fd = 8, spurious_nl_event_fd = 9;
    nl_sock socket, spurious;
    nl_sock *nl_event = &socket, *spurious_nl_event = &spurious;
    void *nl_cb = nullptr, *spurious_nl_cb = nullptr;
};
struct wifi_hal_priv_t { wifi_interface_info_t *interface; };
struct { std::recursive_mutex hapd_lock; } g_wifi_hal;
thread_local unsigned int lock_depth = 0;
void tracked_lock(std::recursive_mutex *mutex) { mutex->lock(); lock_depth++; }
void tracked_unlock(std::recursive_mutex *mutex) { assert(lock_depth); lock_depth--; mutex->unlock(); }
#define pthread_mutex_lock tracked_lock
#define pthread_mutex_unlock tracked_unlock
constexpr int NLE_AGAIN = 4;
int response = -NLE_AGAIN, errno_value = 0;
unsigned int registrations = 0, removals = 0, errors = 0;
int nl80211_register_mgmt_frames_locked(wifi_interface_info_t *interface) {
    assert(lock_depth); interface->socket.active = true; registrations++; return 0;
}
void nl80211_unregister_mgmt_frames_locked(wifi_interface_info_t *interface) {
    assert(lock_depth); interface->socket.active = false; removals++;
}
int nl80211_register_spurious_frames_locked(wifi_interface_info_t *interface) {
    assert(lock_depth); interface->spurious.active = true; return 0;
}
void nl80211_unregister_spurious_frames_locked(wifi_interface_info_t *interface) {
    assert(lock_depth); interface->spurious.active = false;
}
bool mgmt_fd_isset(wifi_hal_priv_t *priv, wifi_interface_info_t **interface) {
    assert(lock_depth); *interface = priv->interface; return (*interface)->socket.active;
}
bool spurious_fd_isset(wifi_hal_priv_t *priv, wifi_interface_info_t **interface) {
    assert(lock_depth); *interface = priv->interface; return (*interface)->spurious.active;
}
int nl_recvmsgs(nl_sock *socket, void *) {
    assert(lock_depth && socket->active);
    std::this_thread::sleep_for(std::chrono::microseconds(10));
    assert(socket->active);
    return response;
}
unsigned int if_nametoindex(const char *) { return 1; }
const char *nl_geterror(int) { return "test"; }
template<typename... Values> void wifi_hal_error_print(const char *, Values...) { errors++; }
''' + wrappers + r'''
void dispatch(wifi_hal_priv_t *priv) {
    wifi_interface_info_t *interface = nullptr;
    int res;
''' + dispatch + r'''
}
int main() {
    wifi_interface_info_t interface;
    wifi_hal_priv_t priv{&interface};
    nl80211_register_mgmt_frames(&interface);
    nl80211_register_spurious_frames(&interface);
    dispatch(&priv);
    assert(registrations == 1 && removals == 0 && errors == 0);
    response = -1;
    dispatch(&priv);
    assert(registrations == 2 && removals == 1 && errors == 3);
    response = -NLE_AGAIN;
    std::thread reader([&] { for (unsigned int repeat = 0; repeat < 1000; repeat++) dispatch(&priv); });
    std::thread writer([&] {
        for (unsigned int repeat = 0; repeat < 1000; repeat++) {
            nl80211_unregister_mgmt_frames(&interface);
            nl80211_unregister_spurious_frames(&interface);
            nl80211_register_mgmt_frames(&interface);
            nl80211_register_spurious_frames(&interface);
        }
    });
    reader.join(); writer.join();
    assert(registrations == 1002 && removals == 1001 && errors == 3);
    assert(lock_depth == 0);
    puts("PASS frame receive/teardown lifetime, recursive error recovery and harmless EAGAIN; select remains unlocked");
}
'''
with tempfile.TemporaryDirectory(prefix="hal-frame-socket-lifetime-") as directory:
    executable = Path(directory) / "test"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O2", "-pthread",
                    "-x", "c++", "-", "-o", str(executable)], input=program, text=True, check=True)
    subprocess.run([str(executable)], check=True, timeout=15)
