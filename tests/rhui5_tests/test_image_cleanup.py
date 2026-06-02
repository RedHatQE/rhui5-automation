"""Image Cleanup Tests"""

# To skip the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv
from os.path import basename
import time

import logging
import nose
from stitches.expect import Expect
import yaml

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.installer import RHUIInstaller
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

HOSTNAMES = {"RHUA": ConMgr.get_rhua_hostname(),
             "CDS": ConMgr.get_cds_hostnames()[0],
             "HAProxy": ConMgr.get_lb_hostname()}

RHUA = ConMgr.connect()
CDS = ConMgr.connect(HOSTNAMES["CDS"])
HAPROXY = ConMgr.connect(HOSTNAMES["HAProxy"])

PODMAN_CMD = "cd /tmp ; sudo -u rhui podman"

class TestImageCleanup():
    """class for image cleanup tests"""
    def __init__(self):
        self.registry = "gitlab"
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            self.pseudo_old_container = doc["container_alt"][self.registry]["name"]

    @staticmethod
    def setup_class():
        """announce the beginning of the test run"""
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_login_add_nodes():
        """log in to RHUI, add nodes"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.initial_run(RHUA)
            RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
            RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

    def test_02_pull_another_container(self):
        """pull a test container"""
        url = Config.get_registry_url(self.registry)
        source = f"{url.replace('https://', '')}/{self.pseudo_old_container}"
        for con in [RHUA, CDS, HAPROXY]:
            Expect.expect_retval(con, f"{PODMAN_CMD} pull {source}")

    def test_03_check_images(self):
        """check if the images were pulled"""
        for con in [RHUA, CDS, HAPROXY]:
            _, stdout, _ = con.exec_command(f"{PODMAN_CMD} images")
            output = stdout.read().decode()
            nose.tools.ok_(self.pseudo_old_container in output, msg=output)

    def test_04_rerun_installer(self):
        """rerun the installer, reinstall the nodes"""
        RHUIInstaller.rerun()
        time.sleep(30)
        RHUIManagerCLIInstance.reinstall(RHUA, "cds", all_nodes=True)
        RHUIManagerCLIInstance.reinstall(RHUA, "haproxy", all_nodes=True)

    def test_05_check_images(self):
        """check if the images were removed"""
        for con in [RHUA, CDS, HAPROXY]:
            _, stdout, _ = con.exec_command(f"{PODMAN_CMD} images")
            output = stdout.read().decode()
            nose.tools.ok_(self.pseudo_old_container not in output, msg=output)

    def test_06_check_timers(self):
        """check if the timers exist"""
        for con in [RHUA, CDS, HAPROXY]:
            _, stdout, _ = con.exec_command("systemctl list-timers")
            output = stdout.read().decode()
            nose.tools.ok_("rhui-container-image-prune.timer" in output, msg=output)

    def test_99_cleanup(self):
        """clean up"""
        if not getenv("RHUISKIPSETUP"):
            RHUIManager.remove_rh_certs(RHUA)
            RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
            RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
            ConMgr.remove_ssh_keys(RHUA)

    @staticmethod
    def teardown_class():
        """announce the end of the test run"""
        print(f"*** Finished running {basename(__file__)}. ***")
