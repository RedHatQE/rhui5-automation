"""Various Compliance Tests"""

# To skip the registration of CDS and HAProxy nodes --
# because you want to save time in each client test case and do this beforehand -- run:
# export RHUISKIPSETUP=1
# in your shell before running this script.
# The cleanup will be skipped, too, so you ought to clean up eventually.

from os import getenv

from os.path import basename

import nose
from stitches.expect import Expect

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

RHUA = ConMgr.connect()
CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])
HAPROXY = ConMgr.connect(ConMgr.get_lb_hostname())

FETCH_RPMS = "rpm -qa --qf '%{NAME} %{RSAHEADER:pgpsig}\n'"
RH_KEY_ID = "199e2f91fd431d51"
GPG_RPM = "gpg-pubkey"

OFFICIAL_REGISTRY = "registry.redhat.io"

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_00_setup():
    """add CDS & HAProxy nodes"""
    if not getenv("RHUISKIPSETUP"):
        RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
        RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

def test_01_deprecation_warnings():
    """check for deprecation warnings from the installer playbook"""
    Expect.expect_retval(RHUA,
                         "grep -i 'DEPRECATION WARNING' "
                         "/var/lib/rhui/log/rhui-installer_logger.log*",
                         1)

def test_02_rpm_signatures():
    """check if all packages in RHUI containers are signed"""
    for connection, container in [[RHUA, "rhua"], [CDS, "cds"], [HAPROXY, "ha"]]:
        _, stdout, _ = connection.exec_command(f"{container} {FETCH_RPMS}")
        rpmdata = stdout.read().decode().splitlines()
        names_sigs = [data.split() for data in rpmdata]
        unsigned = [data[0] for data in names_sigs if data[-1] != RH_KEY_ID and data[0] != GPG_RPM]
        nose.tools.ok_(not unsigned, msg=f"unsigned RPMs in the {container} container: {unsigned}")

def test_03_default_registry():
    """check if the default registry in the right one"""
    config_registry = Config.get_from_rhui_tools_conf(RHUA, "rhui", "default_container_registry")
    nose.tools.eq_(config_registry, OFFICIAL_REGISTRY)

def test_99_cleanup():
    """clean up"""
    if not getenv("RHUISKIPSETUP"):
        RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
        RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
        ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
