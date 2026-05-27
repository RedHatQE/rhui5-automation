"""Tests for optional SSL CA certificates"""

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv, mkdir
from os.path import basename
from shutil import rmtree

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui5_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

CONF_RPM_NAME = "omit-ca"
TMP_DIR = f"/tmp/{CONF_RPM_NAME}"
RPM_DIR = "/root"
RPM_DIR_HOST = "/var/lib/rhui/root"
CACERT_RHUA = "/var/lib/rhui/pki/certs/ca.crt"
CACERT_FILE = "rhui-ca.crt"
CACERT_TEST = f"{TMP_DIR}/{CACERT_FILE}"
CACERT_CLI = f"/etc/pki/ca-trust/source/anchors/{CACERT_FILE}"
CACERT_RPM = "/etc/pki/rhui/ca.crt"

class TestOmitCACert():
    """class to test optional SSL CA certificates"""

    def __init__(self):
        version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.repo_id = doc["yum_repos"][version][arch]["id"]
                self.repo_label = doc["yum_repos"][version][arch]["label"]
            except KeyError as version:
                raise nose.SkipTest(f"No test repo defined for RHEL {version}")

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_initial_run():
        """log in to RHUI, add CDS & HAProxy nodes"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

    def test_02_add_repo(self):
        """add and sync the tested repo"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLI.cert_upload(RHUA)
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id], True)

    def test_03_create_cli_config_rpm(self):
        """create an entitlement certificate and a client configuration RPM (in one step)"""
        RHUIManagerCLI.client_rpm(RHUA,
                                  [self.repo_label],
                                  [CONF_RPM_NAME],
                                  RPM_DIR,
                                  ca=False)

    @staticmethod
    def test_04_install_conf_rpm():
        """install the client configuration RPM"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{RPM_DIR_HOST}/{CONF_RPM_NAME}-2.0/build/RPMS/noarch/" +
                                   f"{CONF_RPM_NAME}-2.0-1.noarch.rpm")

    def test_05_check_repolist_without_cacert(self):
        """check the repo list on the client, should fail"""
        _, _, stderr = CLI.exec_command("yum -v repolist")
        error = stderr.read().decode()
        nose.tools.ok_("unable to get local issuer certificate" in error, msg=error)

    def test_06_check_repolist_with_cacert(self):
        """add the CA cert to the list of trusted CA certs and try again, should work"""
        mkdir(TMP_DIR)
        Util.fetch(RHUA, CACERT_RHUA, CACERT_TEST)
        CLI.sftp.put(CACERT_TEST, CACERT_CLI)
        Expect.expect_retval(CLI, "update-ca-trust extract")
        Expect.expect_retval(CLI, "yum -v repolist")

    def test_07_cacert_not_in_client_rpm(self):
        """check if there is no SSL CA cert in the client configuration RPM"""
        _, stdout, _ = CLI.exec_command(f"rpm -ql {CONF_RPM_NAME}")
        rpm_file_list = stdout.read().decode().splitlines()
        nose.tools.ok_(CACERT_RPM not in rpm_file_list, msg=rpm_file_list)

    def test_99_cleanup(self):
        """clean up"""
        rmtree(TMP_DIR)
        Expect.expect_retval(CLI, f"rm -f {CACERT_CLI}")
        Expect.expect_retval(CLI, "update-ca-trust")
        Util.remove_rpm(CLI, [CONF_RPM_NAME])
        RHUIManagerCLI.repo_delete(RHUA, self.repo_id)
        Expect.expect_retval(RHUA, f"rm -rf {RPM_DIR_HOST}/{CONF_RPM_NAME}*")
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
