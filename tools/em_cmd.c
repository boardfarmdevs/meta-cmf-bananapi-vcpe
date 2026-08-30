/* Minimal non-interactive driver for libemcli.
 *
 * The shipped libemcli.so (built from src/rdkb-cli) implements the whole
 * em_ctrl command path -- TLS to EM_CTRL_PORT and the binary em_event_t
 * marshalling -- but the image ships no executable that drives it. This is
 * that executable, scriptable rather than the readline REPL in src/cli/main.c
 * (which in any case calls an init() the rdkb-cli variant does not export).
 *
 *   em_cmd list                     enumerate the commands em_ctrl accepts
 *   em_cmd <command> [json-file]    run one, optionally with a payload
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <arpa/inet.h>
#include "em_cli_apis.h"

#define EM_CTRL_TCP_PORT 0xc001

int main(int argc, char *argv[])
{
    const char *c;
    em_network_node_t *node = NULL, *res;
    char *out;

    if (argc < 2 || strcmp(argv[1], "list") == 0) {
        for (c = get_first_cmd_str(); c != NULL; c = get_next_cmd_str(c)) {
            printf("%s\n", c);
        }
        return 0;
    }

    if (set_remote_addr(inet_addr("127.0.0.1"), EM_CTRL_TCP_PORT, true) != 0) {
        fprintf(stderr, "set_remote_addr failed\n");
        return 1;
    }

    if (argc > 2) {
        if ((node = get_network_tree_by_file(argv[2])) == NULL) {
            fprintf(stderr, "could not load payload: %s\n", argv[2]);
            return 1;
        }
    }

    if ((res = exec(argv[1], strlen(argv[1]) + 1, node)) == NULL) {
        fprintf(stderr, "exec(\"%s\") returned NULL\n", argv[1]);
        return 1;
    }

    if ((out = get_network_tree_string(res)) != NULL) {
        printf("%s\n", out);
        free_network_tree_string(out);
    }
    return 0;
}
