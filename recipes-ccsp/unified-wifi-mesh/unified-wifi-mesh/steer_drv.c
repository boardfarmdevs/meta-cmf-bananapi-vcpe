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
extern void *get_network_tree_by_key(void *node, const char *key);
extern char *get_node_scalar_value(void *node);
extern void free_node_value(char *value);
extern void free_network_tree(void *node);

int main(int argc, char **argv)
{
    void *node;
    void *result;
    void *status_node;
    char *result_text;
    int success;

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

    result = exec(argv[1], strlen(argv[1]), node);
    free_network_tree(node);
    if (result == NULL) {
        fprintf(stderr, "steer_drv: native command returned no result\n");
        return 1;
    }
    status_node = get_network_tree_by_key(result, "Status");
    result_text = status_node == NULL ? NULL : get_node_scalar_value(status_node);
    if (result_text == NULL) {
        free_network_tree(result);
        return 1;
    }
    success = strcmp(result_text, "Success") == 0;
    printf("steer_drv_status=%s\n", result_text);
    free_node_value(result_text);
    free_network_tree(result);
    return success ? 0 : 1;
}
