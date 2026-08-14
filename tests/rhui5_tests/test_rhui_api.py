"""RHUI API Tests"""

# To skip the upload of an entitlement certificate and the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename
import time

from configparser import ConfigParser
import json
import logging
import nose
from stitches.expect import Expect
import yaml

from rhui5_tests_lib.cfg import Config, RHUI_CFG_HOST_BAK_DIR, RHUI_CFG_BAK
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.installer import RHUIInstaller
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline import RHUIManagerCLI
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance
from rhui5_tests_lib.rhui_api import RHUIAPI
from rhui5_tests_lib.util import Util
from rhui5_tests_lib.yummy import Yummy

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
# __reusable_clients_with_cds
# To make this script communicate with a client machine different from cli01.example.com, run:
# export RHUICLI=hostname
# in your shell before running this script, replacing "hostname" with the actual client host name.
# This allows for multiple client machines in one stack.
CLI = ConMgr.connect(getenv("RHUICLI", ConMgr.get_cli_hostnames()[0]))

CUSTOM_REPO = "test-api-repo"
CR_DISPLAY_NAME = CUSTOM_REPO.replace("-", " ").title()
CUSTOM_REPO_UN = "test-api-repo-un"
ENT = "test-api-cert"
ENT_DIR = "/root"
ENT_DIR_HOST = "/var/lib/rhui" + ENT_DIR
RPM = "test-api-rpm"
VER = "5.0"
VER2 = str(float(VER) + 1)
REL = "1.rhui"
CUSTOM_RPMS_DIR = "/root/test_files"
CUSTOM_RPMS_DIR_HOST = "/var/lib/rhui" + CUSTOM_RPMS_DIR
KEY_FILENAME = "test_gpg_key"
UPLOAD_RPM = "rhui-rpm-upload-test-1-1.noarch.rpm"
UPLOAD_RPM_2_NAME_VR = ["rhui-rpm-upload-trial", "1-1"]
UPLOAD_RPM_3 = "rhui-rpm-upload-tryout"
DOWNDIR = "/tmp/test-api-dir"
TEST_PKG_RESERVED = "compat-sap-c++-10"

class TestRhuiApi():
    """class for RHUI API tests"""

    def __init__(self):
        self.version = Util.get_rhel_version(CLI)["major"]
        arch = Util.get_arch(CLI)
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.rh_repo_id = doc["yum_repos"][self.version][arch]["id"]
                self.rh_repo_label = doc["yum_repos"][self.version][arch]["label"]
                self.rh_repo_path = doc["yum_repos"][self.version][arch]["path"]
                self.test_package = doc["yum_repos"][self.version][arch]["test_package"]
                self.product_name = doc["product"]["name"]
                self.product_ids = doc["product"]["ids"]
            except KeyError:
                raise nose.SkipTest(f"No test repo defined for RHEL {self.version} on {arch}") \
                from None

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_00_init():
        """initialize the environment"""
        enabled = Config.get_from_rhui_tools_conf(RHUA, "api", "restapi_support_enabled")
        if enabled != "True":
            Config.set_rhui_tools_conf(RHUA, "api", "restapi_support_enabled", "True")
            Config.set_rhui_tools_conf(RHUA, "api", "session_length", "1200", False)
            RHUIInstaller.rerun()
            time.sleep(30)
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)
            RHUIManagerCLI.cert_upload(RHUA)
        RHUIAPI.get_ca_cert(RHUA)
        RHUIAPI.get_cookie(RHUA)

    def test_01_repo_unused(self):
        """fetch unused products and check if the test product and its repos are there"""
        api_response = RHUIAPI.repo_unused()
        try:
            repo_unused_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        unused_products = repo_unused_dict["products"]
        matched_products = [pr for pr in unused_products if pr["name"] == self.product_name]
        nose.tools.ok_(matched_products, msg=f"unused products: {unused_products}")
        nose.tools.eq_(matched_products[0]["name"], self.product_name)
        nose.tools.eq_(matched_products[0]["repo_ids"], self.product_ids)

    def test_02_add_repos(self):
        """create custom repos and add Red Hat repos"""
        # first, a protected repo
        RHUIAPI.repo_create_custom(CUSTOM_REPO,
                                   CR_DISPLAY_NAME,
                                   protected=True)
        # then, an unprotected repo and a custom GPG key
        RHUIAPI.repo_create_custom(CUSTOM_REPO_UN,
                                   gpg_public_keys=[f"{CUSTOM_RPMS_DIR}/{KEY_FILENAME}"])
        # a Red Hat repo by its ID, sync it at the same time
        RHUIAPI.repo_add([self.rh_repo_id], sync_now=True)
        # Red Hat repos by their product name
        RHUIAPI.repo_add(product_names=[self.product_name])
        # check the packages in the first product repo -
        # not that a package should be there, but the repo ID contains a dot,
        # which can cause issues
        api_response = RHUIAPI.packages_list(self.product_ids[0])
        response_lines = [json.loads(line) for line in api_response.splitlines()]
        nose.tools.ok_("error" not in response_lines[0],
                       msg=f"response: {response_lines}")

    def test_03_list_repos(self):
        """list repos and check if they're all present"""
        api_response = RHUIAPI.repo_list()
        try:
            repo_list_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        # check the number of repos (two custom, one added by its ID and several by the product)
        nose.tools.eq_(len(repo_list_dict["repositories"]), 3 + len(self.product_ids))
        actual_repos = [repo["id"] for repo in repo_list_dict["repositories"]]
        expected_repos = [CUSTOM_REPO, CUSTOM_REPO_UN, self.rh_repo_id] + self.product_ids
        nose.tools.eq_(sorted(actual_repos), sorted(expected_repos))

    def test_04_repo_info(self):
        """get repository details and check them"""
        # check the two custom repos and the main RH repo, one by one
        for repo in CUSTOM_REPO, CUSTOM_REPO_UN, self.rh_repo_id:
            # also get sync info in the case of the RH repo
            api_response = RHUIAPI.repo_info(repo, repo == self.rh_repo_id)
            try:
                repo_info_dict = json.loads(api_response)
            except json.decoder.JSONDecodeError as err:
                raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
            nose.tools.eq_(repo_info_dict["id"], repo)
            # targetted checks for the individual repos
            if repo == CUSTOM_REPO:
                nose.tools.eq_(repo_info_dict["description"], CR_DISPLAY_NAME)
            elif repo == CUSTOM_REPO_UN:
                nose.tools.ok_(repo_info_dict["pulp_labels"]["base_path"].startswith("unprotected"),
                               msg=f"labels: {repo_info_dict['pulp_labels']}")
                nose.tools.ok_(repo_info_dict["gpg_key"],
                               msg="No GPG key is configured for the repo.")
            else:
                nose.tools.eq_(repo_info_dict["pulp_labels"]["base_path"], self.rh_repo_path)
                nose.tools.ok_("last_sync_date" in repo_info_dict,
                               msg=f"repo info: {repo_info_dict}")

    def test_05_repo_sync(self):
        """sync one of the Red Hat repos"""
        # first sync the last (newest) repo from the product list
        api_response = RHUIAPI.repo_sync([self.product_ids[-1]])
        try:
            response_lines = [json.loads(line) for line in api_response.splitlines()]
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        sync_tasks = [line for line in response_lines if line["type"] == "scheduled"]
        # expect one such task for the repo to sync
        nose.tools.eq_(len(sync_tasks), 1)
        # and it should be the right repo
        nose.tools.eq_(sync_tasks[0]["repo_id"], self.product_ids[-1])

    def test_06_wait_for_sync(self):
        """wait until the repo is synced, then sync the rest of the repos"""
        time.sleep(5)
        # wait until there are no waiting tasks
        while json.loads(RHUIAPI.tasks_waiting())["tasks"]:
            time.sleep(10)
        # wait until there are no running tasks
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        # sync the rest of the repos by using the "all" variant
        api_response = RHUIAPI.repo_sync(sync_all=True)
        try:
            response_lines = [json.loads(line) for line in api_response.splitlines()]
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        sync_tasks = [line for line in response_lines if line["type"] == "scheduled"]
        # expect as many tasks as there are repos in the product plus the base RH repo
        nose.tools.eq_(len(sync_tasks), len(self.product_ids) + 1)
        time.sleep(5)
        # wait until there are no waiting tasks
        while json.loads(RHUIAPI.tasks_waiting())["tasks"]:
            time.sleep(10)
        # wait until there are no running tasks
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        # verify the status by using the freshness check
        Expect.expect_retval(RHUA, "rhua rhui-manager status --freshness", timeout=60)
        # check for a package with a reserved character
        api_response = RHUIAPI.packages_list(self.product_ids[-1], name=TEST_PKG_RESERVED)
        response_lines = [json.loads(line) for line in api_response.splitlines()]
        total = response_lines[-1]["total"]
        # should be > 0; 0 would mean a problem
        nose.tools.ok_(total, msg=f"response: {response_lines}")

    def test_07_delete_repos(self):
        """delete several repositories"""
        api_response = RHUIAPI.repo_delete(self.product_ids)
        try:
            response_lines = [json.loads(line) for line in api_response.splitlines()]
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        delete_tasks = [line for line in response_lines if line["type"] == "repo"]
        # expect as many such tasks as there were repos to delete
        nose.tools.eq_(len(delete_tasks), len(self.product_ids))
        # wait until there are no running tasks
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        # check the repos that remained
        api_response = RHUIAPI.repo_list(True)
        repo_list_dict = json.loads(api_response)
        nose.tools.eq_(len(repo_list_dict["repositories"]), 3)
        # check if sync information is in the response
        nose.tools.ok_(all("last_sync_date" in info for info in repo_list_dict["repositories"]),
                       msg=f"repo list: {repo_list_dict}")

    def test_08_list_packages(self):
        """list packages in the Red Hat repo and check for a test package"""
        api_response = RHUIAPI.packages_list(self.rh_repo_id)
        try:
            response_lines = [json.loads(line) for line in api_response.splitlines()]
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        package_dict = [line for line in response_lines if line["type"] == "package"]
        package_list = [item["package"]["name"] for item in package_dict]
        nose.tools.ok_(self.test_package in package_list,
                       msg=f"packages: {package_list}")

    def test_09_upload_packages(self):
        """upload packages to custom repositories and check them"""
        api_response = RHUIAPI.packages_upload(CUSTOM_REPO, f"{CUSTOM_RPMS_DIR}/{UPLOAD_RPM}")
        try:
            upload_task_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        nose.tools.eq_(upload_task_dict["repo_id"], CUSTOM_REPO)
        nose.tools.eq_(upload_task_dict["packages"], [UPLOAD_RPM])
        time.sleep(5)
        # wait until there are no running tasks
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        # check the package list after the upload
        n, v, r = UPLOAD_RPM.replace(".noarch.rpm", "").rsplit("-", 2)
        api_response = RHUIAPI.packages_list(CUSTOM_REPO, name=n, version=v, release=r)
        response_lines = [json.loads(line) for line in api_response.splitlines()]
        package_dict = [line for line in response_lines if line["type"] == "package"]
        filename_list = [item["package"]["filename"] for item in package_dict]
        nose.tools.eq_(filename_list, [UPLOAD_RPM])
        # upload all RPMs in a directory; just check the result
        api_response = RHUIAPI.packages_upload(CUSTOM_REPO, CUSTOM_RPMS_DIR)
        time.sleep(5)
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        api_response = RHUIAPI.packages_list(CUSTOM_REPO)
        response_lines = [json.loads(line) for line in api_response.splitlines()]
        package_dict = [line for line in response_lines if line["type"] == "package"]
        filename_list = [item["package"]["filename"] for item in package_dict]
        filename_list.sort()
        nose.tools.eq_(filename_list, Util.get_rpms_in_dir(RHUA, CUSTOM_RPMS_DIR_HOST))

    def test_10_remove_packages(self):
        """remove packages from custom repositories and check them"""
        # remove the first package by its name only
        rpm_name = UPLOAD_RPM.rsplit("-", 2)[0]
        api_response = RHUIAPI.packages_remove(CUSTOM_REPO, rpm_name)
        try:
            remove_task_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        nose.tools.eq_(remove_task_dict["repo_id"], CUSTOM_REPO)
        nose.tools.eq_(remove_task_dict["packages"], [UPLOAD_RPM])
        # remove the second package by its name and version-release
        (rpm_name, rpm_vr) = UPLOAD_RPM_2_NAME_VR
        try:
            api_response = RHUIAPI.packages_remove(CUSTOM_REPO, rpm_name, rpm_vr)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        remove_task_dict = json.loads(api_response)
        nose.tools.eq_(remove_task_dict["repo_id"], CUSTOM_REPO)
        nose.tools.eq_(remove_task_dict["packages"],
                                        ["-".join(UPLOAD_RPM_2_NAME_VR) + ".noarch.rpm"])
        # wait and check the result
        time.sleep(5)
        # wait until there are no running tasks
        while json.loads(RHUIAPI.tasks_running())["tasks"]:
            time.sleep(10)
        # check the package list after the removal
        api_response = RHUIAPI.packages_list(CUSTOM_REPO)
        response_lines = [json.loads(line) for line in api_response.splitlines()]
        package_dict = [line for line in response_lines if line["type"] == "package"]
        filename_list = [item["package"]["filename"] for item in package_dict]
        nose.tools.ok_(len(filename_list) == 1
                       and UPLOAD_RPM not in filename_list
                       and not filename_list[0].startswith(rpm_name),
                       msg=f"file names: {filename_list}")

    def test_11_cds_k8s(self):
        """generate K8s configuration and check it"""
        secret = "testsecret"
        expected_kinds = ["ConfigMap", "Deployment", "Secret", "Service"]
        api_response = RHUIAPI.cds_k8s(secret)
        # try one more time if there's an issue
        if "curl:" in api_response:
            time.sleep(10)
            api_response = RHUIAPI.cds_k8s(secret)
        try:
            k8s_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        # check the JSON keys
        nose.tools.eq_(list(k8s_dict.keys()), ["ssl_cert_secret_name", "manifest"])
        nose.tools.eq_(k8s_dict["ssl_cert_secret_name"], secret)
        # check if the manifest exists, can be loaded as YAML, and contains the right stuff
        k8s_yaml = yaml.safe_load_all(k8s_dict["manifest"])
        data = list(k8s_yaml)
        nose.tools.eq_(sorted([item["kind"] for item in data]), expected_kinds)

    def test_12_labels(self):
        """list repo labels"""
        api_response = RHUIAPI.client_labels()
        try:
            label_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        label_list = label_dict["repo_labels"]
        # check if the test repo labels is present
        nose.tools.ok_(self.rh_repo_label in label_list,
                       msg=f"labels: {label_list}")

    def test_13_generate_ent_cert(self):
        """generate an entitlement certificate"""
        api_response = RHUIAPI.client_cert([CUSTOM_REPO, self.rh_repo_label],
                                           ENT,
                                           35*365,
                                           ENT_DIR)
        try:
            cert_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        nose.tools.eq_(cert_dict["status"], "created")
        nose.tools.eq_(cert_dict["cert_path"], f"{ENT_DIR}/{ENT}.crt")
        nose.tools.eq_(cert_dict["key_path"], f"{ENT_DIR}/{ENT}.key")
        # also check the files
        Expect.expect_retval(RHUA, f"test -f {ENT_DIR_HOST}/{ENT}.crt")
        Expect.expect_retval(RHUA, f"test -f {ENT_DIR_HOST}/{ENT}.key")

    def test_14_create_cli_rpm(self):
        """create a client configuration RPM from the entitlement certificate"""
        expected_path = f"{ENT_DIR}/{RPM}-{VER}/build/RPMS/noarch/{RPM}-{VER}-{REL}.noarch.rpm"
        api_response = RHUIAPI.client_rpm(ENT_DIR,
                                          RPM,
                                          [],
                                          [CUSTOM_REPO_UN],
                                          f"{ENT_DIR}/{ENT}.crt",
                                          f"{ENT_DIR}/{ENT}.key",
                                          REL,
                                          VER)
        try:
            rpm_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        nose.tools.eq_(rpm_dict["status"], "created")
        nose.tools.eq_(rpm_dict["rpm_path"], expected_path)
        # check if the rpm was created
        Expect.expect_retval(RHUA, f"test -f /var/lib/rhui/{expected_path}")
        # also try creating an RPM using labels rather than a prepared cert and key,
        # and with some other different parameters
        proxy = "_none_"
        api_response = RHUIAPI.client_rpm(ENT_DIR,
                                          RPM,
                                          [self.rh_repo_label],
                                          [CUSTOM_REPO_UN],
                                          "",
                                          "",
                                          REL,
                                          VER2,
                                          2 * 365,
                                          proxy,
                                          "",
                                          True)
        try:
            rpm_dict = json.loads(api_response)
        except json.decoder.JSONDecodeError as err:
            raise RuntimeError(f"error: {err}, API response: '{api_response}'") from err
        nose.tools.eq_(rpm_dict["status"], "created")
        # check the repo file
        repo_file = f"{ENT_DIR_HOST}/{RPM}-{VER2}/build/BUILD/{RPM}-{VER2}/rh-cloud.repo"
        _, stdout, _ = RHUA.exec_command(f"cat {repo_file}")
        yum_cfg = ConfigParser()
        yum_cfg.read_file(stdout)
        rh_section = f"rhui-{self.rh_repo_label}"
        unprot_section = f"rhui-custom-{CUSTOM_REPO_UN}"
        nose.tools.ok_(rh_section in yum_cfg.sections(), msg=f"sections: {yum_cfg.sections()}")
        nose.tools.ok_(unprot_section in yum_cfg.sections(), msg=f"sections: {yum_cfg.sections()}")
        nose.tools.ok_(all(yum_cfg.get(r, "proxy") == proxy for r in yum_cfg.sections()))
        nose.tools.ok_(all("sslcacert" not in yum_cfg.options(r) for r in yum_cfg.sections()))

    @staticmethod
    def test_15_install_conf_rpm():
        """install the client configuration RPM"""
        # get rid of undesired repos first
        Util.remove_amazon_rhui_conf_rpm(CLI)
        Util.disable_beta_repos(CLI)
        Util.install_pkg_from_rhua(RHUA,
                                   CLI,
                                   f"{ENT_DIR_HOST}/{RPM}-{VER}/build/RPMS/noarch/" +
                                   f"{RPM}-{VER}-{REL}.noarch.rpm")
        # verify the installation
        Expect.expect_retval(CLI, f"rpm -q {RPM}")

    def test_16_inst_rpm_custom_repo(self):
        """check if RPMs can be fetched from the custom and the Red Hat repos"""
        Yummy.install(CLI, [UPLOAD_RPM_3], False)
        Yummy.download(CLI, [self.test_package], DOWNDIR)

    def test_99_cleanup(self):
        """clean up"""
        RHUIAPI.repo_delete([self.rh_repo_id, CUSTOM_REPO, CUSTOM_REPO_UN])
        Expect.expect_retval(RHUA, f"rm -f {ENT_DIR_HOST}/{ENT}*")
        Expect.expect_retval(RHUA, f"rm -rf {ENT_DIR_HOST}/{RPM}*")
        Expect.expect_retval(CLI, f"rm -rf {DOWNDIR}")
        Util.remove_rpm(CLI, [RPM, UPLOAD_RPM_3])
        if not getenv("RHUISKIPSETUP"):
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)
            RHUIManager.remove_rh_certs(RHUA)
        if RHUA.recv_exit_status(f"test -f {RHUI_CFG_HOST_BAK_DIR}/{RHUI_CFG_BAK}") == 0:
            Config.restore_rhui_tools_conf(RHUA)
            RHUIInstaller.rerun()
            time.sleep(30)
        RHUIAPI.del_cookie()

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
