"""Tests of RHUI systemd timers"""

from os.path import basename

import nose

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.helpers import Helpers

RHUA = ConMgr.connect()

EXPECTED_UNITS = ["export-repos-trigger",
                  "orphans-cleanup",
                  "pulp-tmpfiles-cleanup",
                  "purge-upload-dirs",
                  "repo-sync",
                  "symlinks-cleanup-deepscan",
                  "symlinks-cleanup",
                  "synchronize-subscriptions",
                  "tasks-purge",
                  "update-mappings"]

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")


def test_01_check_timers():
    """check if all RHUI timers exist"""
    active = [Helpers.check_service(RHUA, f"rhui-{unit}.timer", "rhua") for unit in EXPECTED_UNITS]
    name_status_zip = zip(EXPECTED_UNITS, active)
    nose.tools.ok_(all(active), msg=f"error: {list(name_status_zip)}")

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
