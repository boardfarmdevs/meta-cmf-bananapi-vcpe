/* vCPE shim: bridge the dhcp4c_* API names that rdkb-halif-dhcp's
 * dhcp4cApi.h declares to the dhcpv4c_* names that
 * hal-dhcpv4c-generic libapi_dhcpv4c.so actually exports.
 *
 * Upstream bpi packaging bug -- the header recipe and the library
 * recipe were version-bumped out of step. Affects both arm and vCPE;
 * arm just doesn't notice because it can't compile far enough to load
 * the data model. Without this shim, libtr181.so fails to dlopen and
 * CcspPandMSsp runs without any TR-181 parameters.
 */
#include <ccsp/dhcp4cApi.h>

extern int dhcpv4c_get_ert_lease_time(unsigned int *pValue);
int dhcp4c_get_ert_lease_time(unsigned int *pValue) { return dhcpv4c_get_ert_lease_time(pValue); }

extern int dhcpv4c_get_ert_remain_lease_time(unsigned int *pValue);
int dhcp4c_get_ert_remain_lease_time(unsigned int *pValue) { return dhcpv4c_get_ert_remain_lease_time(pValue); }

extern int dhcpv4c_get_ert_remain_renew_time(unsigned int *pValue);
int dhcp4c_get_ert_remain_renew_time(unsigned int *pValue) { return dhcpv4c_get_ert_remain_renew_time(pValue); }

extern int dhcpv4c_get_ert_remain_rebind_time(unsigned int *pValue);
int dhcp4c_get_ert_remain_rebind_time(unsigned int *pValue) { return dhcpv4c_get_ert_remain_rebind_time(pValue); }

extern int dhcpv4c_get_ert_config_attempts(int *pValue);
int dhcp4c_get_ert_config_attempts(int *pValue) { return dhcpv4c_get_ert_config_attempts(pValue); }

extern int dhcpv4c_get_ert_ifname(char *pName);
int dhcp4c_get_ert_ifname(char *pName) { return dhcpv4c_get_ert_ifname(pName); }

extern int dhcpv4c_get_ert_fsm_state(int *pValue);
int dhcp4c_get_ert_fsm_state(int *pValue) { return dhcpv4c_get_ert_fsm_state(pValue); }

extern int dhcpv4c_get_ert_ip_addr(unsigned int *pValue);
int dhcp4c_get_ert_ip_addr(unsigned int *pValue) { return dhcpv4c_get_ert_ip_addr(pValue); }

extern int dhcpv4c_get_ert_mask(unsigned int *pValue);
int dhcp4c_get_ert_mask(unsigned int *pValue) { return dhcpv4c_get_ert_mask(pValue); }

extern int dhcpv4c_get_ert_gw(unsigned int *pValue);
int dhcp4c_get_ert_gw(unsigned int *pValue) { return dhcpv4c_get_ert_gw(pValue); }

extern int dhcpv4c_get_ert_dns_svrs(ipv4AddrList_t *pList);
int dhcp4c_get_ert_dns_svrs(ipv4AddrList_t *pList) { return dhcpv4c_get_ert_dns_svrs(pList); }

extern int dhcpv4c_get_ert_dhcp_svr(unsigned int *pValue);
int dhcp4c_get_ert_dhcp_svr(unsigned int *pValue) { return dhcpv4c_get_ert_dhcp_svr(pValue); }

extern int dhcpv4c_get_ecm_lease_time(unsigned int *pValue);
int dhcp4c_get_ecm_lease_time(unsigned int *pValue) { return dhcpv4c_get_ecm_lease_time(pValue); }

extern int dhcpv4c_get_ecm_remain_lease_time(unsigned int *pValue);
int dhcp4c_get_ecm_remain_lease_time(unsigned int *pValue) { return dhcpv4c_get_ecm_remain_lease_time(pValue); }

extern int dhcpv4c_get_ecm_remain_renew_time(unsigned int *pValue);
int dhcp4c_get_ecm_remain_renew_time(unsigned int *pValue) { return dhcpv4c_get_ecm_remain_renew_time(pValue); }

extern int dhcpv4c_get_ecm_remain_rebind_time(unsigned int *pValue);
int dhcp4c_get_ecm_remain_rebind_time(unsigned int *pValue) { return dhcpv4c_get_ecm_remain_rebind_time(pValue); }

extern int dhcpv4c_get_ecm_config_attempts(int *pValue);
int dhcp4c_get_ecm_config_attempts(int *pValue) { return dhcpv4c_get_ecm_config_attempts(pValue); }

extern int dhcpv4c_get_ecm_ifname(char *pName);
int dhcp4c_get_ecm_ifname(char *pName) { return dhcpv4c_get_ecm_ifname(pName); }

extern int dhcpv4c_get_ecm_fsm_state(int *pValue);
int dhcp4c_get_ecm_fsm_state(int *pValue) { return dhcpv4c_get_ecm_fsm_state(pValue); }

extern int dhcpv4c_get_ecm_ip_addr(unsigned int *pValue);
int dhcp4c_get_ecm_ip_addr(unsigned int *pValue) { return dhcpv4c_get_ecm_ip_addr(pValue); }

extern int dhcpv4c_get_ecm_mask(unsigned int *pValue);
int dhcp4c_get_ecm_mask(unsigned int *pValue) { return dhcpv4c_get_ecm_mask(pValue); }

extern int dhcpv4c_get_ecm_gw(unsigned int *pValue);
int dhcp4c_get_ecm_gw(unsigned int *pValue) { return dhcpv4c_get_ecm_gw(pValue); }

extern int dhcpv4c_get_ecm_dns_svrs(ipv4AddrList_t *pList);
int dhcp4c_get_ecm_dns_svrs(ipv4AddrList_t *pList) { return dhcpv4c_get_ecm_dns_svrs(pList); }

extern int dhcpv4c_get_ecm_dhcp_svr(unsigned int *pValue);
int dhcp4c_get_ecm_dhcp_svr(unsigned int *pValue) { return dhcpv4c_get_ecm_dhcp_svr(pValue); }

extern int dhcpv4c_get_emta_remain_lease_time(unsigned int *pValue);
int dhcp4c_get_emta_remain_lease_time(unsigned int *pValue) { return dhcpv4c_get_emta_remain_lease_time(pValue); }

extern int dhcpv4c_get_emta_remain_renew_time(unsigned int *pValue);
int dhcp4c_get_emta_remain_renew_time(unsigned int *pValue) { return dhcpv4c_get_emta_remain_renew_time(pValue); }

extern int dhcpv4c_get_emta_remain_rebind_time(unsigned int *pValue);
int dhcp4c_get_emta_remain_rebind_time(unsigned int *pValue) { return dhcpv4c_get_emta_remain_rebind_time(pValue); }

