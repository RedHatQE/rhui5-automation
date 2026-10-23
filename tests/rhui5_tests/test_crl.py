"""Tests for certificate revocation lists"""

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename
import re
import time

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager_client import RHUIManagerClient
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

CRT_RPM_NAME = "crl"
CRT_RPM_DIR = "/root/" + CRT_RPM_NAME
CRT_RPM_DIR_HOST = "/var/lib/rhui" + CRT_RPM_DIR
UNPROT_REPO = f"test-{CRT_RPM_NAME}-unprot"
CRL_COMMENT = "Test CRL"

class TestCRL():
    """class to test certificate revocation lists"""

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

    def test_02_add_repos(self):
        """add the tested repos"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLI.cert_upload(RHUA)
        RHUIManagerCLI.repo_add_by_repo(RHUA, [self.repo_id])
        RHUIManagerCLI.repo_create_custom(RHUA, UNPROT_REPO)

    def test_03_create_cert(self):
        """create an entitlement certificate"""
        RHUIManagerCLI.client_cert(RHUA,
                                   [self.repo_label],
                                   CRT_RPM_NAME,
                                   365,
                                   CRT_RPM_DIR)

    @staticmethod
    def test_04_revoke_cert():
        """revoke the cert by its path"""
        RHUIManagerCLI.client_revoke(RHUA, f"{CRT_RPM_DIR}/{CRT_RPM_NAME}.crt", comment=CRL_COMMENT)

    def test_05_create_cli_config_rpm(self):
        """create a client configuration RPM (using the prepared cert)"""
        cert_path_basename = f"{CRT_RPM_DIR}/{CRT_RPM_NAME}"
        RHUIManagerCLI.client_rpm(RHUA,
                                  [f"{cert_path_basename}.key", f"{cert_path_basename}.crt"],
                                  [CRT_RPM_NAME],
                                  CRT_RPM_DIR,
                                  [UNPROT_REPO])

    @staticmethod
    def test_06_install_conf_rpm():
        """install the client configuration RPM"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{CRT_RPM_DIR_HOST}/{CRT_RPM_NAME}-2.0/build/RPMS/noarch/" +
                                   f"{CRT_RPM_NAME}-2.0-1.noarch.rpm")

    @staticmethod
    def test_07_check_crl():
        """check the revocation list on the RHUA"""
        crl = RHUIManagerCLI.client_revoked(RHUA)
        # shouldn't be empty
        nose.tools.ok_(crl, msg=f"Current CRL: {crl}")
        # the cert's SN should be in the list
        sn = Util.cert_serial(RHUA, f"{CRT_RPM_DIR_HOST}/{CRT_RPM_NAME}.crt")
        nose.tools.eq_(int(crl[0][0]), sn)
        nose.tools.eq_(crl[0][2], CRL_COMMENT)

    @staticmethod
    def test_08_rhui_manager_status():
        """check the revocation list in rhui-manager status"""
        _, stdout, _ = RHUA.exec_command("rhua rhui-manager status")
        output = stdout.read().decode()
        match = re.search("Denylist.*OK", output)
        nose.tools.ok_(match, msg=f"Output: {output}")
        nose.tools.ok_("1 revoked serial" in output, msg=f"Output: {output}")

    @staticmethod
    def test_09_check_repolist_revoked_cert():
        """check the repo list on the client, should fail"""
        # first wait a bit to make sure the updated denylist has been noticed
        time.sleep(6)
        _, _, stderr = CLI.exec_command("yum -v repolist")
        error = stderr.read().decode()
        nose.tools.ok_("Status code: 403" in error, msg=error)

    @staticmethod
    def test_10_check_repolist_only_unprot():
        """check the repo list with only the unprotected repo, should pass"""
        cus_repo = "rhui-custom-" + UNPROT_REPO
        cmd = f"yum --disablerepo=* --enablerepo={cus_repo} -v repolist"
        Expect.expect_retval(CLI, cmd)

    @staticmethod
    def test_11_unrevoke_cert():
        """unrevoke the cert"""
        RHUIManagerCLI.client_unrevoke(RHUA, f"{CRT_RPM_DIR}/{CRT_RPM_NAME}.crt")

    @staticmethod
    def test_12_check_crl():
        """check the revocation list on the RHUA again, should be empty"""
        crl = RHUIManagerCLI.client_revoked(RHUA)
        # shouldn't be empty
        nose.tools.ok_(not crl, msg=f"Current CRL: {crl}")

    @staticmethod
    def test_13_check_repolist_unrevoked_cert():
        """check the repo list on the client, should pass"""
        # first wait a bit to make sure the updated denylist has been noticed
        time.sleep(11)
        cmd = "yum -v repolist"
        Expect.expect_retval(CLI, cmd)

    @staticmethod
    def test_14_revoke_serial():
        """revoke the cert by its serial number"""
        sn = Util.cert_serial(RHUA, f"{CRT_RPM_DIR_HOST}/{CRT_RPM_NAME}.crt")
        RHUIManagerCLI.client_revoke(RHUA, serial=sn, force=True)
        # just check it on the RHUA
        crl = RHUIManagerCLI.client_revoked(RHUA)
        # shouldn't be empty
        nose.tools.ok_(crl, msg=f"Current CRL: {crl}")
        # is the SN there?
        nose.tools.eq_(int(crl[0][0]), sn)
        # no comment?
        nose.tools.eq_(len(crl[0]), 2)
        # unrevoke it
        RHUIManagerCLI.client_unrevoke(RHUA, f"{CRT_RPM_DIR}/{CRT_RPM_NAME}.crt")

    @staticmethod
    def test_15_revoke_tui():
        """check cert revocation in the TUI"""
        sn = Util.cert_serial(RHUA, f"{CRT_RPM_DIR_HOST}/{CRT_RPM_NAME}.crt")
        # two ways: by the cert or by the SN; the rest is the same
        for i in range(2):
            odd_or_even = i % 2
            if odd_or_even:
                RHUIManagerClient.revoke(RHUA,
                                         f"{CRT_RPM_DIR}/{CRT_RPM_NAME}.crt",
                                         comment=CRL_COMMENT)
            else:
                RHUIManagerClient.revoke(RHUA, serial=sn)
            # check it
            crl = RHUIManagerClient.revoked(RHUA)
            # shouldn't be empty
            nose.tools.ok_(crl, msg=f"Current CRL: {crl}")
            # the cert's SN should be in the list
            nose.tools.eq_(int(crl[0][0]), sn)
            # the comment should be there for the path-based revocation only
            if odd_or_even:
                nose.tools.eq_(crl[0][2], CRL_COMMENT)
            else:
                nose.tools.eq_(len(crl[0]), 2)
            # unrevoke it
            sn_with_optional_comment = str(sn) + ((" - " + CRL_COMMENT) if odd_or_even else "")
            RHUIManagerClient.unrevoke(RHUA, [sn_with_optional_comment])

    def test_99_cleanup(self):
        """clean up"""
        Util.remove_rpm(CLI, [CRT_RPM_NAME])
        for repo in [self.repo_id, UNPROT_REPO]:
            RHUIManagerCLI.repo_delete(RHUA, repo)
        Expect.expect_retval(RHUA, f"rm -rf {CRT_RPM_DIR_HOST}")
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
