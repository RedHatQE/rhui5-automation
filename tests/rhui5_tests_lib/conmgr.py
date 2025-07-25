"""Connection Manager for RHUI Test Cases"""

import re
import logging

from stitches.connection import Connection
from stitches.expect import Expect

SHORT_HOSTNAMES = {"RHUA": "rhua",
                   "NFS": "nfs",
                   "LB": "lb",
                   "CDS": "cds",
                   "HAProxy": "hap",
                   "client": "cli"}
DOMAIN = "example.com"

USER_NAME = "root"
USER_KEY = "/root/.ssh/id_ecdsa_test"
SUDO_USER_NAME = "ec2-user"
SUDO_USER_KEY = "/root/.ssh/id_ecdsa_launchpad"

def _list_hostnames(nodes, fake=False):
    """return a list of hostnames of the given node type"""
    # if "fake" is on and no hostnames are found, a hostname is made up and returned as
    # a single list item
    host_pattern = fr"{nodes}[0-9]+\.{re.escape(DOMAIN)}"
    with open("/etc/hosts", encoding="utf-8") as hostsfile:
        all_hosts = hostsfile.read()
    matched_hosts = re.findall(host_pattern, all_hosts)
    if matched_hosts or not fake:
        return matched_hosts
    logging.warning("No hosts found. Using a fake hostname. Proceed with caution.")
    return [f"{nodes}01.{DOMAIN}"]

class ConMgr():
    """simplify connections to RHUI nodes & clients by providing handy constants and methods"""
    @staticmethod
    def get_launchpad_hostname():
        """return the hostname of the launchpad node"""
        return f"launchpad.{DOMAIN}"

    @staticmethod
    def get_nfs_hostname():
        """return the hostname of the NFS node"""
        return f"{SHORT_HOSTNAMES['NFS']}.{DOMAIN}"

    @staticmethod
    def get_rhua_hostname():
        """return the hostname of the RHUA node"""
        return f"{SHORT_HOSTNAMES['RHUA']}.{DOMAIN}"

    @staticmethod
    def get_lb_hostname():
        """return the hostname of the CDS Load Balancer node"""
        return f"{SHORT_HOSTNAMES['LB']}.{DOMAIN}"

    @staticmethod
    def get_cds_hostnames(fake=True):
        """return a list of CDS hostnames"""
        return _list_hostnames(SHORT_HOSTNAMES["CDS"], fake)

    @staticmethod
    def get_haproxy_hostnames(fake=True):
        """return a list of HAProxy hostnames; there's usually only a single HAProxy node in RHUI"""
        return _list_hostnames(SHORT_HOSTNAMES["HAProxy"], fake)

    @staticmethod
    def get_cli_hostnames(fake=True):
        """return a list of client hostnames"""
        return _list_hostnames(SHORT_HOSTNAMES["client"], fake)

    @staticmethod
    def connect(hostname="", username=USER_NAME, sshkey=USER_KEY):
        """create a connection to the specified host"""
        return Connection(hostname or ConMgr.get_rhua_hostname(), username, sshkey)

    @staticmethod
    def add_ssh_keys(connection, hostnames, keytype="rsa"):
        """gather SSH keys for the given hosts"""
        hosts_file = "/var/lib/rhui/root/.ssh/known_hosts"
        Expect.expect_retval(connection,
                             f"ssh-keyscan -t {keytype} {' '.join(hostnames)} >> {hosts_file}")

    @staticmethod
    def remove_ssh_keys(connection, hostnames="", keep_localhost=True):
        """remove SSH keys that belong to the given (or all) hosts"""
        hosts_file = "/root/.ssh/known_hosts"
        key_file_exists = connection.recv_exit_status(f"rhua test -f {hosts_file}") == 0
        if key_file_exists:
            if not hostnames:
                if keep_localhost:
                    Expect.expect_retval(connection, f"rhua sed -i '/^localhost/!d' {hosts_file}")
                else:
                    Expect.expect_retval(connection, f"rhua rm -f {hosts_file}")
                return
            for host in hostnames:
                Expect.expect_retval(connection, f"rhua ssh-keygen -R {host}")
