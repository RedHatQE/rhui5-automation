""" Test case for proxy settings"""

# To skip the upload of an entitlement certificatev --
# because you want to save time with similar test cases and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

# To actually sync the test repo via the proxy, this test must run in a cloudformation
# stack that was deployed with such a service, ie. with --proxy on the deployment
# command line, which installs and configures squid on the load balancer node.

import logging
from os import getenv
from os.path import basename

import nose
import yaml

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.pulp_api import PulpAPI
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline import RHUIManagerCLI

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
PROXY_HOSTNAME = ConMgr.get_lb_hostname()
ALT_PROXY_HOSTNAME = ConMgr.get_haproxy_hostnames()[0]
PROXY_PROTOCOL = "http"
PROXY_PORT = 3128
PROXY_USER = "pruser"
PROXY_PASS = "qwerty"
PROXY_URL = f"{PROXY_PROTOCOL}://{PROXY_HOSTNAME}:{PROXY_PORT}"
ALT_PROXY_URL = f"{PROXY_PROTOCOL}://{ALT_PROXY_HOSTNAME}:{PROXY_PORT}"
PROXY_CON = ConMgr.connect(PROXY_HOSTNAME)

def _get_password_from_pulpcore_manager(connection, remote):
    """get the proxy password from the database"""
    # ...because it's a hidden field that the Pulp CLI/API can't retrieve
    # warning: the code produces literally "None" if the password isn't set;
    # if that's the case, we'll use the proper NoneType
    pycode = "from pulpcore.app.models import Remote; " \
            f"rem = Remote.objects.get(name='{remote}'); " \
             "print(rem.proxy_password)"
    hostcmd = f"cd /tmp ; echo \"{pycode}\" | sudo -u rhui podman exec -i rhui5-rhua"
    concmd = "sudo -u pulp env PULP_SETTINGS=/etc/pulp/settings.py /usr/bin/pulpcore-manager shell"
    _, stdout, _ = connection.exec_command(f"{hostcmd} {concmd}")
    output = stdout.read().decode().strip()
    return None if output == "None" else output

class TestProxyUpdates():
    """class for the proxy update tests """
    def __init__(self):
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            self.test_repo = doc["status_repos"]["good"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_00_rhui_init():
        """log in to RHUI and upload a certificate"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLI.cert_upload(RHUA)

    def test_01_add_repo(self):
        """add a test repo"""
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.test_repo])

    def test_02_check_default_repo_proxy(self):
        """check the proxy URL of the remote for the unsynced repo, should be empty/None"""
        remote_data = PulpAPI.get_remote(RHUA, self.test_repo)
        actual_proxy_url = remote_data["proxy_url"]
        nose.tools.eq_(actual_proxy_url, None)

    @staticmethod
    def test_03_add_proxy_configuration():
        """edit the RHUI configuration to add the proxy settings"""
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_protocol", PROXY_PROTOCOL)
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_host", PROXY_HOSTNAME, False)
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_port", str(PROXY_PORT), False)

    def test_04_sync_repo(self):
        """sync the test repo, which should apply the settings to the repo"""
        is_proxy_available = PROXY_CON.recv_exit_status("systemctl status squid") == 0
        # sync the repo mainly to apply the settings to it, it's okay if the sync fails because
        # the stack wasn't installed with squid on the load balancer node
        RHUIManagerCLI.repo_sync(RHUA, self.test_repo, is_proxy_available)

    def test_05_check_added_repo_proxy(self):
        """check the proxy URL of the remote for the synced repo, should be the expected URL"""
        remote_data = PulpAPI.get_remote(RHUA, self.test_repo)
        actual_proxy_url = remote_data["proxy_url"]
        nose.tools.eq_(actual_proxy_url, PROXY_URL)

    @staticmethod
    def test_06_change_proxy_hostname():
        """edit the RHUI configuration again to change the proxy hostname"""
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_host", ALT_PROXY_HOSTNAME, False)

    @staticmethod
    def test_07_cli_update_proxy_settings():
        """use the CLI to immediately update the proxy settings"""
        RHUIManagerCLI.proxy_update(RHUA)

    def test_08_check_changed_repo_proxy(self):
        """check the proxy URL of the remote again, should be the new expected URL"""
        remote_data = PulpAPI.get_remote(RHUA, self.test_repo)
        actual_proxy_url = remote_data["proxy_url"]
        nose.tools.eq_(actual_proxy_url, ALT_PROXY_URL)

    @staticmethod
    def test_09_set_proxy_credentials():
        """edit the RHUI configuration again to set a proxy username and password"""
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_user", PROXY_USER, False)
        Config.set_rhui_tools_conf(RHUA, "proxy", "proxy_pass", PROXY_PASS, False)

    def test_10_cli_force_credentialss(self):
        """use the CLI to set the credentials, should require --force"""
        # first try without --force, should have no effect (the password field should remain empty)
        RHUIManagerCLI.proxy_update(RHUA)
        actual_password = _get_password_from_pulpcore_manager(RHUA, self.test_repo)
        nose.tools.eq_(actual_password, None)
        # now with --force
        RHUIManagerCLI.proxy_update(RHUA, True)
        actual_password = _get_password_from_pulpcore_manager(RHUA, self.test_repo)
        nose.tools.eq_(actual_password, PROXY_PASS)

    def test_11_clear_proxy_configuration(self):
        """restore the RHUI configuration to empty values for the proxy"""
        Config.restore_rhui_tools_conf(RHUA)

    @staticmethod
    def test_12_cli_update_proxy_settings():
        """use the CLI to immediately update the proxy settings"""
        RHUIManagerCLI.proxy_update(RHUA)

    def test_13_check_cleared_repo_proxy(self):
        """check the proxy URL of the remote again, should be empty/None"""
        remote_data = PulpAPI.get_remote(RHUA, self.test_repo)
        actual_proxy_url = remote_data["proxy_url"]
        nose.tools.eq_(actual_proxy_url, None)

    def test_99_cleanup(self):
        """clean up"""
        RHUIManagerCLI.repo_delete(RHUA, self.test_repo)
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
