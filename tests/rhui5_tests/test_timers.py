"""Tests of RHUI systemd timers"""

from os.path import basename
import re

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

def test_00_check_timer_files():
    """check if the expected units match the timer files on the RHUA"""
    # if this test fails, either the list of expected units needs updating,
    # or the timer is missing from rhui-tools
    _, stdout, _ = RHUA.exec_command("rhua ls -w1 /usr/lib/systemd/system")
    all_systemd_files = stdout.read().decode().splitlines()
    rhui_timer_re = re.compile(r"^rhui-(.*)\.timer$")
    rhui_timers = [rhui_timer_re.search(file).group(1) for file in all_systemd_files \
                   if file.startswith("rhui-") and file.endswith(".timer")]
    nose.tools.eq_(rhui_timers, EXPECTED_UNITS)

def test_01_check_timers():
    """check if all RHUI timers are active"""
    active = [Helpers.check_service(RHUA, f"rhui-{unit}.timer", "rhua") for unit in EXPECTED_UNITS]
    name_status_zip = zip(EXPECTED_UNITS, active)
    nose.tools.ok_(all(active), msg=f"error: {list(name_status_zip)}")

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
