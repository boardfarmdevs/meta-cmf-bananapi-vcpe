/* steer_drv: drive libemcli's command channel non-interactively.
 * Usage: steer_drv "<command> OneWifiMesh" <payload.json>
 * Reconstructed per doc/easymesh/README.md "roaming and client steering".
 */
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <arpa/inet.h>
#include <stdbool.h>

extern int   set_remote_addr(unsigned int ip, unsigned int port, bool valid);
extern void *get_network_tree_by_file(const char *file);
extern void *exec(char *in, size_t in_len, void *node);

int main(int argc, char **argv)
{
    void *node;

    if (argc < 3) {
        fprintf(stderr, "usage: %s \"<command> OneWifiMesh\" <payload.json>\n", argv[0]);
        return 2;
    }

    set_remote_addr(inet_addr("127.0.0.1"), 49153, true);

    node = get_network_tree_by_file(argv[2]);
    if (node == NULL) {
        fprintf(stderr, "steer_drv: could not parse %s\n", argv[2]);
        return 1;
    }

    exec(argv[1], strlen(argv[1]), node);
    return 0;
}
