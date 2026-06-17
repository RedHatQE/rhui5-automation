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

from rhui5_tests_lib.cfg import Config, OFFICIAL_REGISTRY
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

RHUA = ConMgr.connect()
CDS = ConMgr.connect(ConMgr.get_cds_hostnames()[0])
HAPROXY = ConMgr.connect(ConMgr.get_lb_hostname())

FETCH_RPMS = "rpm -qa --qf '%{NAME} %{RSAHEADER:pgpsig}\n'"
RH_KEY_ID = "199e2f91fd431d51"
GPG_RPM = "gpg-pubkey"

USING_TEST_REGISTRY = Config.get_registry_data(RHUA)[0] != OFFICIAL_REGISTRY

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_00_setup():
    """add CDS & HAProxy nodes"""
    if not getenv("RHUISKIPSETUP"):
        if USING_TEST_REGISTRY:
            raise nose.SkipTest("An unofficial registry is used.")
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
    if USING_TEST_REGISTRY:
        raise nose.SkipTest("An unofficial registry is used.")
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

def test_04_invalid_url():
    """check for spam in the subscription sync log"""
    # only makes sense if the RHUA host is registered and the subscription has been synced...
    # anyway:
    log = "/var/lib/rhui/log/rhui-subscription-sync.log"
    log_exists = RHUA.recv_exit_status(f"test -f {log}") == 0
    if not log_exists:
        raise nose.SkipTest(f"{log} doesn't exist (yet), can't test it")
    Expect.expect_retval(RHUA,
                         "grep -c 'Invalid repository download URL' "
                         f"{log}*",
                         1)

def test_05_undesired_egress():
    """check for admitted egress involving a third party"""
    # Pulp analytics are suppossed to be disabled
    # First check the settings
    settings = "/var/lib/rhui/config/pulp/settings.py"
    Expect.expect_retval(RHUA, rf"grep -i 'analytics\s*=\s*false' {settings}")
    # Then check the logs
    log = "/var/lib/rhui/log/pulp/worker.log"
    Expect.expect_retval(RHUA,
                         "zgrep 'Submitted analytics' "
                         f"{log}*",
                         1)

def test_06_wanted_rpms():
    """check for extra RPMs in the containers that CCSPs asked for"""
    Expect.expect_retval(RHUA, "rhua rpm -q rpm-sign && rhua rpmsign --version")
    Expect.expect_retval(RHUA, "rhua rpm -q glibc-all-langpacks")
    # also check RPMs on CDS & HAProxy nodes, but only if they're configured
    if CDS.recv_exit_status("systemctl status rhui_cds") == 0:
        Expect.expect_retval(CDS, "cds rpm -q logrotate && "
                                  "cds systemctl status logrotate.timer | grep Trigger:")
        Expect.expect_retval(HAPROXY, "ha rpm -q logrotate && "
                                      "ha systemctl status logrotate.timer | grep Trigger:")

def test_07_pgsql_locale():
    """check if PostgreSQL can run with a non-defalt locale setting"""
    default_locale = "C.UTF-8"
    other_locale = "ja_JP.UTF-8"
    pgsql_conf = "/var/lib/pgsql/data/postgresql.conf"
    restart_cmd = "rhua systemctl restart postgresql"
    # change the locale
    Expect.expect_retval(RHUA, f"rhua sed -i s/{default_locale}/{other_locale}/ {pgsql_conf}")
    # try restarting the service, but only get the exit code so that this test case can continue
    restart_status = RHUA.recv_exit_status(restart_cmd, timeout=60)
    # revert
    Expect.expect_retval(RHUA, f"rhua sed -i s/{other_locale}/{default_locale}/ {pgsql_conf}")
    Expect.expect_retval(RHUA, restart_cmd)
    # chech the result only in the end
    nose.tools.eq_(restart_status, 0)

def test_99_cleanup():
    """clean up"""
    if not getenv("RHUISKIPSETUP"):
        if USING_TEST_REGISTRY:
            raise nose.SkipTest("An unofficial registry is used.")
        RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
        RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
        ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
