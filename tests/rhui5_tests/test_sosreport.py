"""Test case for sosreport and RHUI"""

import logging
from os.path import basename
from shutil import rmtree
from tempfile import mkdtemp

from stitches.expect import Expect

from rhui5_tests_lib.cfg import RHUI_ROOT
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.sos import Sos

logging.basicConfig(level=logging.DEBUG)

TMPDIR = mkdtemp()
SOSREPORT_LOCATION = f"{TMPDIR}/sosreport_location_rhua"

RHUA = ConMgr.connect()

RHUI_FILES = [
              "/var/lib/rhui/config/rhua/rhui-tools.conf",
              "/var/lib/rhui/log/pulp/api.log",
              "/var/lib/rhui/log/pulp/content.log",
              "/var/lib/rhui/log/pulp/worker.log",
              "/var/lib/rhui/log/rhua_ansible.log",
              "/var/lib/rhui/log/rhui-subscription-sync.log",
              "/var/lib/rhui/root/.rhui/rhui.log",
             ]
RHUI_CMDS = [
             "rhui-manager status",
             "rhui-manager cert info",
             Sos.dir_listing_cmd(RHUI_ROOT)
            ]
PULP_FILES = [
              "/etc/pulp/settings.py"
             ]

WANTED_FILES = RHUI_FILES + \
               Sos.installer_log_paths(RHUA) + \
               [Sos.containerized_path(file) for file in PULP_FILES] + \
               [Sos.encode_sos_command(cmd) for cmd in RHUI_CMDS]

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_00_init():
    """initialize the RHUI environment before running sosreport"""
    Expect.expect_retval(RHUA, "rhua rhui-subscription-sync || :")

def test_01_rhua_sosreport_run():
    """run sosreport on the RHUA node"""
    sosreport_location = Sos.run(RHUA)
    if sosreport_location is None:
        raise RuntimeError("sosreport failed")
    with open(SOSREPORT_LOCATION, "w", encoding="utf-8") as location:
        location.write(sosreport_location)

def test_02_rhua_sosreport_check():
    """check if the sosreport archive from the RHUA node contains the desired files"""
    with open(SOSREPORT_LOCATION, encoding="utf-8") as location:
        sosreport_location = location.read()
    Sos.check_files_in_archive(RHUA, WANTED_FILES, sosreport_location)

def test_03_check_confidential_data():
    """check if known confidential information is obfuscated in the archive"""
    with open(SOSREPORT_LOCATION, encoding="utf-8") as location:
        sosreport_location = location.read()
    # cookies
    for cookie in ["csrftoken", "sessionid"]:
        Sos.is_obfuscated(RHUA,
                          cookie,
                          "/var/lib/rhui/root/.rhui/http-localhost:24817/cookies.txt",
                          sosreport_location)
    # container registry password
    Sos.is_obfuscated(RHUA,
                      "podman_password",
                      "/var/lib/rhui/config/rhua/rhui-tools.conf",
                      sosreport_location)

def test_99_cleanup():
    """delete the archive and its checksum file, local cache"""
    with open(SOSREPORT_LOCATION, encoding="utf-8") as location:
        sosreport_file = location.read()
        Expect.expect_retval(RHUA, f"rm -f {sosreport_file}*")
    rmtree(TMPDIR)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
