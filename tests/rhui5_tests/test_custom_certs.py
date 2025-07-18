"""Tests for custom certificates"""

# To keep the custom certificates after installing them, run:
# export RHUIKEEPCUSTOMCERTS=1
# in your shell before running this script.
#
# This will also preserve CDS01 and the HAProxy node.
#
# If you have multiple CDS nodes, run:
# rhuitestsetup --ssl-like-cds-one
# Else, run:
# rhuitestsetup
#
# Regardless of the number of your CDS nodes, run:
# export RHUISKIPSETUP=1
# and continue with client tests using this custom SSL configuration.

from os import getenv
from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui5_tests_lib.cfg import RHUI_ROOT
from rhui5_tests_lib.conmgr import ConMgr, SUDO_USER_NAME
from rhui5_tests_lib.installer import RHUIInstaller
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_instance import RHUIManagerInstance
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)

LAUNCHPAD = ConMgr.connect(ConMgr.get_launchpad_hostname())
RHUA = ConMgr.connect()
CDS_HOSTNAME = ConMgr.get_cds_hostnames()[0]
CDS = ConMgr.connect(CDS_HOSTNAME)
HAPROXY_HOSTNAME = ConMgr.get_lb_hostname()
NFS_HOSTNAME = ConMgr.get_nfs_hostname()

CUSTOM_CERTS_DIR = "/root/test_files/custom_certs"
CUSTOM_CERTS_DIR_HOST = "/var/lib/rhui" + CUSTOM_CERTS_DIR
ORIG_SSL_CERTS_BASEDIR = f"{RHUI_ROOT}/cds-config/ssl"
ORIG_CERTS_BASEDIR = "/var/lib/rhui/pki"
ORIG_CERTS_SUBDIR = "certs"
ORIG_KEYS_SUBDIR = "private"
BACKUPDIR = f"{RHUI_ROOT}/bak"
LOCALDIR = "/tmp/bak"

FILES = {
         "rhui": "ca",
         "client_ssl": "client_ssl_ca",
         "client_entitlement": "client_entitlement_ca",
         "cds_ssl": "ssl"
        }

def _check_crt_key():
    """check if the cert and the key are on the CDS"""
    for ext in ["crt", "key"]:
        _, stdout, _ = RHUA.exec_command(f"md5sum {CUSTOM_CERTS_DIR_HOST}/{FILES['cds_ssl']}.{ext}")
        expected_sum = stdout.read().decode().split()[0]

        crt_file = f"{ORIG_SSL_CERTS_BASEDIR}/{HAPROXY_HOSTNAME}.{ext}"
        _, stdout, _ = CDS.exec_command(f"md5sum {crt_file}")
        actual_sum = stdout.read().decode().split()[0]
        nose.tools.eq_(expected_sum, actual_sum)

def _delete_crt_key():
    """delete the cert and the key from the storage"""
    Expect.expect_retval(RHUA, f"rm -f {ORIG_SSL_CERTS_BASEDIR}/*")

def _check_instance_add_error():
    """check the error message after adding an instance incorrectly"""
    _, stdout, _ = RHUA.exec_command("tail -1 /var/lib/rhui/root/.rhui/rhui.log")
    lastlogline = stdout.read().decode().strip()
    expected_error = f"Error: CDS: {CDS_HOSTNAME} is already configured " \
                     "with different SSL certificates."
    nose.tools.eq_(lastlogline, expected_error)

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_check_custom_files():
    """check if all the custom certificates and keys exist"""
    for basefile in FILES.values():
        Expect.expect_retval(RHUA, f"test -f {CUSTOM_CERTS_DIR_HOST}/{basefile}.crt")
        Expect.expect_retval(RHUA, f"test -f {CUSTOM_CERTS_DIR_HOST}/{basefile}.key")

def test_02_backup():
    """back up the original certificates and keys"""
    Expect.expect_retval(RHUA, f"mkdir -p {BACKUPDIR}")
    Expect.expect_retval(RHUA, f"cp -r {ORIG_CERTS_BASEDIR}/{ORIG_CERTS_SUBDIR} {BACKUPDIR}")
    Expect.expect_retval(RHUA, f"cp -r {ORIG_CERTS_BASEDIR}/{ORIG_KEYS_SUBDIR} {BACKUPDIR}")
    Expect.expect_retval(RHUA, f"chown -R {SUDO_USER_NAME}:{SUDO_USER_NAME} {BACKUPDIR}")

def test_03_rerun_installer():
    """rerun the installer with the custom certificates and keys"""
    vols = {}
    vols["rhui-ca.crt"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['rhui']}.crt"
    vols["rhui-ca.key"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['rhui']}.key"
    vols["client-ssl-ca.crt"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['client_ssl']}.crt"
    vols["client-ssl-ca.key"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['client_ssl']}.key"
    vols["client-entitlement-ca.crt"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['client_entitlement']}.crt"
    vols["client-entitlement-ca.key"] = f"{CUSTOM_CERTS_DIR_HOST}/{FILES['client_entitlement']}.key"
    RHUIInstaller.rerun(other_volumes=vols)

def test_04_check_installed_files():
    """check if the custom certificates and keys were really installed"""
    for _, fname in FILES.items():
        # only check CA certs and keys, though
        if not fname.endswith("ca"):
            continue
        Expect.expect_retval(RHUA, "diff -u "
                                   f"{CUSTOM_CERTS_DIR_HOST}/{fname}.crt "
                                   f"{ORIG_CERTS_BASEDIR}/{ORIG_CERTS_SUBDIR}/{fname}.crt")
        Expect.expect_retval(RHUA, "diff -u "
                                   f"{CUSTOM_CERTS_DIR_HOST}/{fname}.key "
                                   f"{ORIG_CERTS_BASEDIR}/{ORIG_KEYS_SUBDIR}/{fname}.key")

def test_05_add_cds():
    """[TUI] add a CDS with a custom SSL cert and key"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerInstance.add_instance(RHUA,
                                     "cds",
                                     CDS_HOSTNAME,
                                     ssl_crt=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.crt",
                                     ssl_key=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key")

def test_06_check_cds():
    """check if the files are on the CDS"""
    _check_crt_key()

def test_07_delete_cds():
    """delete the CDS so it can be added using the CLI"""
    RHUIManagerInstance.delete_all(RHUA, "cds")
    # also delete the files from the CDS
    _delete_crt_key()

def test_08_add_cds():
    """[CLI] add a CDS with a custom SSL cert and key"""
    RHUIManagerCLIInstance.add(RHUA,
                               "cds",
                               CDS_HOSTNAME,
                               ssl_crt=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.crt",
                               ssl_key=f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key",
                               unsafe=True)

def test_09_check_cert_on_cds():
    """check if the files are on the CDS"""
    _check_crt_key()

def test_10_add_cds_without_custom_ssl():
    """check if another CDS cannot be added without a custom SSL certificate"""
    # first, the function to add a CDS with that configuration should return False
    nose.tools.ok_(not RHUIManagerCLIInstance.add(RHUA, "cds", "foo.example.com", unsafe=True))
    # also, an appropriate error should be logged
    _check_instance_add_error()

def test_11_add_cds_with_other_custom_ssl():
    """check if another CDS cannot be added with a different SSL certificate"""
    # first, the function to add a CDS with that configuration should return False
    keyfile = f"{CUSTOM_CERTS_DIR}/{FILES['cds_ssl']}.key"
    nose.tools.ok_(not RHUIManagerCLIInstance.add(RHUA,
                                                  "cds",
                                                  "foo.example.com",
                                                  ssl_crt="/etc/issue",
                                                  ssl_key=keyfile,
                                                  unsafe=True))
    # also, an appropriate error should be logged
    _check_instance_add_error()

def test_12_add_haproxy():
    """add an HAProxy node (no special parameters)"""
    nose.tools.ok_(RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True))

def test_13_check_nodes():
    """check if only the expected nodes are present"""
    expected_nodes = [CDS_HOSTNAME, HAPROXY_HOSTNAME]
    actual_nodes = RHUIManagerCLIInstance.list(RHUA, "cds") + \
                   RHUIManagerCLIInstance.list(RHUA, "haproxy")
    nose.tools.eq_(expected_nodes, actual_nodes)

def test_99_cleanup():
    """clean up: rerun the installer with the original certificates and keys, remove the nodes"""
    if getenv("RHUIKEEPCUSTOMCERTS"):
        raise nose.SkipTest("Prevented")
    Expect.expect_retval(LAUNCHPAD, f"mount {NFS_HOSTNAME}:/export /mnt")
    Expect.expect_retval(LAUNCHPAD, f"mkdir {LOCALDIR}")
    Expect.expect_retval(LAUNCHPAD, f"cp -a /mnt/bak/* {LOCALDIR}")
    vols = {}
    vols["rhui-ca.crt"] = f"{LOCALDIR}/{ORIG_CERTS_SUBDIR}/{FILES['rhui']}.crt"
    vols["rhui-ca.key"] = f"{LOCALDIR}/{ORIG_KEYS_SUBDIR}/{FILES['rhui']}.key"
    vols["client-ssl-ca.crt"] = f"{LOCALDIR}/{ORIG_CERTS_SUBDIR}/{FILES['client_ssl']}.crt"
    vols["client-ssl-ca.key"] = f"{LOCALDIR}/{ORIG_KEYS_SUBDIR}/{FILES['client_ssl']}.key"
    vols["client-entitlement-ca.crt"] = \
        f"{LOCALDIR}/{ORIG_CERTS_SUBDIR}/{FILES['client_entitlement']}.crt"
    vols["client-entitlement-ca.key"] = \
        f"{LOCALDIR}/{ORIG_KEYS_SUBDIR}/{FILES['client_entitlement']}.key"
    RHUIInstaller.rerun(other_volumes=vols)
    Expect.expect_retval(RHUA, f"rm -rf {BACKUPDIR}")
    Expect.expect_retval(LAUNCHPAD, "umount /mnt")
    Expect.expect_retval(LAUNCHPAD, f"rm -rf {LOCALDIR}")
    RHUIManagerCLIInstance.delete(RHUA, "cds", [CDS_HOSTNAME], force=True)
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", [HAPROXY_HOSTNAME], force=True)
    ConMgr.remove_ssh_keys(RHUA)
    _delete_crt_key()

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
