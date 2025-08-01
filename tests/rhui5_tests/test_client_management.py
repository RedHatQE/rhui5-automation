'''Client management tests'''

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

# To use this test just to set the RHUI environment up with repos for further manual tests, run:
# export RHUIPREP=1
# in your shell before running this script.

from os import getenv
from os.path import basename, join
import re
from shutil import rmtree
from tempfile import mkdtemp

import logging
import nose
import requests
from stitches.expect import Expect
import urllib3
import yaml

from rhui5_tests_lib.cfg import LEGACY_CA_DIR
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.helpers import Helpers
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_client import RHUIManagerClient
from rhui5_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements
from rhui5_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui5_tests_lib.rhuimanager_repo import RHUIManagerRepo
from rhui5_tests_lib.rhuimanager_sync import RHUIManagerSync
from rhui5_tests_lib.util import Util
from rhui5_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))
CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])

CUSTOM_REPO = "custom-i386-x86_64"
CUSTOM_PATH = CUSTOM_REPO.replace("-", "/")
ENT = "test_ent_cli"
ENT_DIR = "/root"
ENT_DIR_HOST = "/var/lib/rhui" + ENT_DIR
RPM = "test_cli_rpm"
VER = "3.0"
REL = "1.rhui"
CUSTOM_RPMS_DIR = "/root/test_files"
CUSTOM_RPMS_DIR_HOST = "/var/lib/rhui" + CUSTOM_RPMS_DIR
DOWNDIR = "/tmp/client_management"

LEGACY_CA_FILE = "legacy_ca.crt"

TMPDIR = mkdtemp()

class TestClient():
    '''
       class for client tests
    '''

    def __init__(self):
        try:
            self.custom_rpm = Util.get_rpms_in_dir(RHUA, CUSTOM_RPMS_DIR_HOST)[0]
        except IndexError:
            raise RuntimeError(f"No custom RPMs to test in {CUSTOM_RPMS_DIR_HOST}") from None
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.yum_repo_name = doc["yum_repos"][self.version][arch]["name"]
                self.yum_repo_version = doc["yum_repos"][self.version][arch]["version"]
                self.yum_repo_kind = doc["yum_repos"][self.version][arch]["kind"]
                self.yum_repo_path = doc["yum_repos"][self.version][arch]["path"]
                self.test_package = doc["yum_repos"][self.version][arch]["test_package"]
            except KeyError:
                raise nose.SkipTest(f"No test repo defined for RHEL {self.version} on {arch}") \
                from None

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_init():
        '''log in to RHUI'''
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_upload_rh_certificate():
        '''
           upload a new or updated Red Hat content certificate
        '''
        if not getenv("RHUISKIPSETUP"):
            entlist = RHUIManagerEntitlements.upload_rh_certificate(RHUA)
            nose.tools.assert_not_equal(len(entlist), 0)

    @staticmethod
    def test_03_add_cds():
        '''
            add a CDS
        '''
        if not getenv("RHUISKIPSETUP"):
            cds_list = RHUIManagerInstance.list(RHUA, "cds")
            nose.tools.assert_equal(cds_list, [])
            RHUIManagerInstance.add_instance(RHUA, "cds")

    @staticmethod
    def test_04_add_hap():
        '''
            add an HAProxy Load-balancer
        '''
        if not getenv("RHUISKIPSETUP"):
            hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
            nose.tools.assert_equal(hap_list, [])
            RHUIManagerInstance.add_instance(RHUA, "loadbalancers")

    def test_05_add_upload_sync_stuff(self):
        '''
           add a custom and RH content repos to protect by a cli entitlement cert, upload rpm, sync
        '''
        RHUIManagerRepo.add_custom_repo(RHUA, CUSTOM_REPO, "", CUSTOM_PATH)
        RHUIManagerRepo.upload_content(RHUA,
                                       [CUSTOM_REPO],
                                       join(CUSTOM_RPMS_DIR, self.custom_rpm))
        RHUIManagerRepo.add_rh_repo_by_repo(RHUA,
                                            [Util.format_repo(self.yum_repo_name,
                                                              self.yum_repo_version,
                                                              self.yum_repo_kind)])
        RHUIManagerSync.sync_repo(RHUA,
                                  [Util.format_repo(self.yum_repo_name, self.yum_repo_version)])

    def test_06_generate_ent_cert(self):
        '''
           generate an entitlement certificate
        '''
        RHUIManagerClient.generate_ent_cert(RHUA,
                                            [CUSTOM_REPO, self.yum_repo_name],
                                            ENT,
                                            ENT_DIR,
                                            35*365)
        Expect.expect_retval(RHUA, f"test -f {ENT_DIR_HOST}/{ENT}.crt")
        Expect.expect_retval(RHUA, f"test -f {ENT_DIR_HOST}/{ENT}.key")

    @staticmethod
    def test_07_create_cli_rpm():
        '''
           create a client configuration RPM from the entitlement certificate
        '''
        RHUIManagerClient.create_conf_rpm(RHUA,
                                          ENT_DIR,
                                          f"{ENT_DIR}/{ENT}.crt",
                                          f"{ENT_DIR}/{ENT}.key",
                                          RPM,
                                          VER,
                                          REL)
        # check if the rpm was created
        Expect.expect_retval(RHUA,
                             f"test -f {ENT_DIR_HOST}/{RPM}-{VER}/build/RPMS/noarch/" +
                             f"{RPM}-{VER}-{REL}.noarch.rpm")

    @staticmethod
    def test_08_ensure_gpgcheck_conf():
        '''
           ensure that GPG checking is enabled in the client configuration
        '''
        repo_file = f"{ENT_DIR_HOST}/{RPM}-{VER}/build/BUILD/{RPM}-{VER}/rh-cloud.repo"
        Expect.expect_retval(RHUA, r"grep -q '^gpgcheck\s*=\s*1$' " + repo_file)

    @staticmethod
    def test_09_check_cli_crt_sig():
        '''check if SHA-256 is used in the client certificate signature'''
        # for RHBZ#1628957
        sigs_expected = ["sha256", "sha256"]
        _, stdout, _ = RHUA.exec_command("openssl x509 -noout -text -in " +
                                         f"{ENT_DIR_HOST}/{ENT}.crt")
        cert_details = stdout.read().decode()
        sigs_actual = re.findall("sha[0-9]+", cert_details)
        nose.tools.eq_(sigs_expected, sigs_actual)

    @staticmethod
    def test_10_install_conf_rpm():
        '''
           install the client configuration RPM
        '''
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        # make sure the system isn't registered with RHSM
        Expect.expect_retval(CLI, "subscription-manager unregister || :")
        # auto-enable sub-man's yum/dnf plugins
        Expect.expect_retval(CLI, "subscription-manager config --rhsm.auto_enable_yum_plugins=1")
        # check the status of the plugin
        Expect.expect_retval(CLI,
                             "grep -q enabled.*1 /etc/yum/pluginconf.d/subscription-manager.conf")
        # now install the client config RPM
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{ENT_DIR_HOST}/{RPM}-{VER}/build/RPMS/noarch/" +
                                   f"{RPM}-{VER}-{REL}.noarch.rpm")

        # verify the installation by checking the client configuration RPM version
        Expect.expect_retval(CLI, f"[ `rpm -q --queryformat \"%{{VERSION}}\" {RPM}` = '{VER}' ]")

    def test_11_check_repo_sync_status(self):
        '''
           check if RH repos have been synced so RPMs can be installed from them
        '''
        RHUIManagerSync.wait_till_repo_synced(RHUA,
                                              [Util.format_repo(self.yum_repo_name,
                                                                self.yum_repo_version)])

    def test_12_inst_rpm_custom_repo(self):
        '''
           install an RPM from the custom repo
        '''
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        test_rpm_name = self.custom_rpm.rsplit('-', 2)[0]
        Yummy.install(CLI, [test_rpm_name], False)

    def test_13_down_rpm_rh_repo(self):
        '''
           download an RPM from the RH repo
        '''
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        Yummy.download(CLI, [self.test_package], DOWNDIR)
        # but make sure the RPM is taken from the RHUI
        Util.check_package_url(CLI, self.test_package, self.yum_repo_path)

    def test_14_unauthorized_access(self):
        '''
           verify that RHUI repo content cannot be fetched without an entitlement certificate
        '''
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        # try HEADing the repodata file for the already added repo
        # the HTTP request must not complete (not even with HTTP 403);
        # it is supposed to raise an SSLError instead
        cds_lb = ConMgr.get_lb_hostname()
        nose.tools.ok_(not requests.head(f"https://{cds_lb}/pulp/content/" +
                                         f"{self.yum_repo_path}/repodata/repomd.xml",
                                         timeout=10,
                                         verify=False).ok)
        # also check the protected custom repo
        nose.tools.ok_(not requests.head(f"https://{cds_lb}/pulp/content/" +
                                         f"protected/{CUSTOM_PATH}/repodata/repomd.xml",
                                         timeout=10,
                                         verify=False).ok)

    def test_15_check_cli_plugins(self):
        '''
           check if irrelevant Yum plug-ins are not enabled on the client with the config RPM
        '''
        # for RHBZ#1415681
        cmd = "yum" if self.version <= 7 else "dnf -v"
        cmd += " repolist enabled | egrep '^Loaded plugins.*(rhnplugin|subscription-manager)'"
        Expect.expect_retval(CLI, cmd, 1)
        # trigger sub-man (shouldn't re-enable its plugin) and re-check the plugins
        # (for RHBZ#1957871)
        Expect.expect_retval(CLI, "subscription-manager facts")
        Expect.expect_retval(CLI, cmd, 1)
        Expect.expect_retval(CLI,
                             "grep -q enabled.*0 /etc/yum/pluginconf.d/subscription-manager.conf")
        Expect.expect_retval(CLI, "yum repolist | grep -q 'This system is not registered'", 1)

    @staticmethod
    def test_16_release_handling():
        '''
           check EUS release handling (working with /etc/yum/vars/releasever on the client)
        '''
        # for RHBZ#1504229
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        Expect.expect_retval(CLI, "rhui-set-release --set 7.5")
        Expect.expect_retval(CLI, "[[ $(</etc/yum/vars/releasever) == 7.5 ]]")
        Expect.expect_retval(CLI, "[[ $(rhui-set-release) == 7.5 ]]")
        Expect.expect_retval(CLI, "rhui-set-release -s 6.5")
        Expect.expect_retval(CLI, "[[ $(</etc/yum/vars/releasever) == 6.5 ]]")
        Expect.expect_retval(CLI, "[[ $(rhui-set-release) == 6.5 ]]")
        Expect.expect_retval(CLI, "rhui-set-release -u")
        Expect.expect_retval(CLI, "test -f /etc/yum/vars/releasever", 1)
        Expect.expect_retval(CLI, "rhui-set-release -s 7.1")
        Expect.expect_retval(CLI, "[[ $(</etc/yum/vars/releasever) == 7.1 ]]")
        Expect.expect_retval(CLI, "[[ $(rhui-set-release) == 7.1 ]]")
        Expect.expect_retval(CLI, "rhui-set-release --unset")
        Expect.expect_retval(CLI, "test -f /etc/yum/vars/releasever", 1)
        Expect.expect_retval(CLI, "rhui-set-release foo", 1)
        Expect.ping_pong(CLI, "rhui-set-release --help", "Usage:")
        Expect.ping_pong(CLI, "rhui-set-release -h", "Usage:")

    @staticmethod
    def test_17_legacy_ca():
        '''
            check for proper logs if a legacy CA is used
        '''
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        # get the CA cert from the RHUA and upload it to the CDS
        # the cert is among the extra RHUI files, ie. in the directory also containing custom RPMs
        remote_ca_file = join(CUSTOM_RPMS_DIR_HOST, LEGACY_CA_FILE)
        local_ca_file = join(TMPDIR, LEGACY_CA_FILE)
        Util.fetch(RHUA, remote_ca_file, local_ca_file)
        Helpers.add_legacy_ca(CDS, local_ca_file)
        # re-fetch repodata on the client to trigger the OID validator on the CDS
        Expect.expect_retval(CLI, "yum clean all ; yum -v repolist enabled")
        Expect.expect_retval(CDS,
                             f"egrep 'Found file {LEGACY_CA_DIR}/{LEGACY_CA_FILE}' " +
                             "/var/lib/rhui/log/gunicorn-auth.log")

    def test_99_cleanup(self):
        '''
           remove repos, certs, cli rpms; remove rpms from cli, uninstall cds, hap
        '''
        if getenv("RHUIPREP"):
            raise nose.SkipTest("Only the setup was requested.")
        test_rpm_name = self.custom_rpm.rsplit('-', 2)[0]
        RHUIManagerRepo.delete_all_repos(RHUA)
        nose.tools.assert_equal(RHUIManagerRepo.list(RHUA), [])
        Expect.expect_retval(RHUA, f"rm -f {ENT_DIR_HOST}/{ENT}*")
        Expect.expect_retval(RHUA, f"rm -rf {ENT_DIR_HOST}/{RPM}-{VER}/")
        Expect.expect_retval(CLI, f"rm -rf {DOWNDIR}")
        Util.remove_rpm(CLI, [RPM, test_rpm_name])
        rmtree(TMPDIR)
        Helpers.del_legacy_ca(CDS)
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
            RHUIManagerInstance.delete_all(RHUA, "cds")
            RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
