"""Various Compliance Tests"""

from os.path import basename

from stitches.expect import Expect

from rhui5_tests_lib.conmgr import ConMgr

RHUA = ConMgr.connect()

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_deprecation_warnings():
    """check for deprecation warnings from the installer playbook"""
    Expect.expect_retval(RHUA,
                         "grep -i 'DEPRECATION WARNING' "
                         "/var/lib/rhui/log/rhui-installer_logger.log*",
                         1)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
