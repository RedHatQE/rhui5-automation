"""Tests for changing the RHUI remote share"""

from os.path import basename
import time

import logging
import nose

from rhui5_tests_lib.cfg import Config, RHUI_ROOT
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.installer import RHUIInstaller
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]

RHUA = ConMgr.connect()
CDS = ConMgr.connect(CDS_HOSTNAME)

OLD_FS_SERVER = f"{ConMgr.get_nfs_hostname()}:/export"
NEW_FS_SERVER = f"{ConMgr.get_rhua_hostname()}:/export"
OLD_FS_OPTIONS = "rw"
NEW_FS_OPTIONS = "timeo=100"

def _check_rhui_mountpoint(connection, fs_server, options=""):
    """check the RHUI mountpoint"""
    mount_info_files = ["/proc/mounts", "/etc/fstab"]
    _, stdout, _ = connection.exec_command("ls /usr/lib/systemd/system/rhui_*.service")
    output = stdout.read().decode().strip()
    fun = basename(output).replace("rhui_", "").replace(".service", "")
    for mount_info_file in mount_info_files:
        cat = "cat" if mount_info_file == "/etc/fstab" else f"{fun} cat"
        _, stdout, _ = connection.exec_command(f"{cat} {mount_info_file}")
        mounts = stdout.read().decode().splitlines()
        matches = [line for line in mounts if RHUI_ROOT in line]
        # there must be only one such share
        nose.tools.eq_(len(matches), 1,
                       msg=f"unexpected matches in {mount_info_file}: {matches}")
        # and it must be using the expected FS server
        properties = matches[0].split()
        actual_share = properties[0]
        test = actual_share.startswith(fs_server)
        nose.tools.ok_(test,
                       msg=f"{fs_server} not found in {mount_info_file}, found: {actual_share}")
        # if also checking options, find and compare them; options are in the fourth column
        if options:
            actual_options = properties[3]
            test = options in actual_options
            nose.tools.ok_(test,
                           msg=f"{options} not found in {mount_info_file}, found: {actual_options}")

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_add_cds():
    """add a CDS"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLIInstance.add(RHUA, "cds", CDS_HOSTNAME, unsafe=True)
    # check that
    cds_list = RHUIManagerCLIInstance.list(RHUA, "cds")
    nose.tools.ok_(cds_list)

def test_02_rerun_installer():
    """rerun the installer with a different remote FS server and custom mount options"""
    RHUIInstaller.rerun(other_args=f"--remote-fs-server {NEW_FS_SERVER} "
                                   f"--rhua-mount-options {NEW_FS_OPTIONS}")
    time.sleep(30)

def test_03_check_rhua_mountpoint():
    """check if the new remote share has replaced the old one on the RHUA"""
    _check_rhui_mountpoint(RHUA, NEW_FS_SERVER, NEW_FS_OPTIONS)
    # also check the configuration file
    saved_mount_options = Config.get_from_rhui_tools_conf(RHUA, "rhui", "rhua_mount_options")
    nose.tools.eq_(saved_mount_options, NEW_FS_OPTIONS)

def test_04_reinstall_cds():
    """reinstall the CDS"""
    RHUIManagerCLIInstance.reinstall(RHUA, "cds", CDS_HOSTNAME)

def test_05_check_cds_mountpoint():
    """check if the new remote share is now used on the CDS"""
    _check_rhui_mountpoint(CDS, NEW_FS_SERVER, NEW_FS_OPTIONS)

def test_06_rerun_installer():
    """rerun the installer with no mount point options and expect no changes"""
    RHUIInstaller.rerun()
    time.sleep(30)
    # check the mount point
    _check_rhui_mountpoint(RHUA, NEW_FS_SERVER, NEW_FS_OPTIONS)
    # check the configuration file
    saved_mount_options = Config.get_from_rhui_tools_conf(RHUA, "rhui", "rhua_mount_options")
    nose.tools.eq_(saved_mount_options, NEW_FS_OPTIONS)

def test_07_wrong_mount_options():
    """try running the installer with disallowed/conflicting mount options and expect it to fail"""
    RHUIInstaller.rerun(other_args="--rhua-mount-options rw,fail", expect_trouble=True)

def test_99_cleanup():
    """clean up: delete the CDS and rerun the installer with the original remote FS"""
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    RHUIInstaller.rerun(other_args=f"--remote-fs-server {OLD_FS_SERVER} "
                                   f"--rhua-mount-options {OLD_FS_OPTIONS}")
    # did it work?
    _check_rhui_mountpoint(RHUA, OLD_FS_SERVER)
    # finish the cleanup
    ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
