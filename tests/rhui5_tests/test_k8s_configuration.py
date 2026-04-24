"""K8s Configuration Tests"""

from os.path import basename

import nose
from stitches.expect import Expect
import yaml

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

RHUA = ConMgr.connect()

CUSTOM_CERTS_DIR = "/root/test_files/custom_certs"
TEST_FILES = [
              "/root/empty",
              "/root/noeol",
              "/var/lib/rhui/container-config/auth.json",
              "/usr/share/rhui-tools/playbooks/cds-register.yml"
             ]
EXPECTED_KINDS = ["ConfigMap", "Deployment", "Secret", "Service"]

def _check_playbook_recap(output):
    """check if there was no Ansible failure"""
    nose.tools.ok_("failed=0" in output, msg=f"oops: {output}")

def _get_data_from_config(config):
    """get the data (list) from the configuration"""
    k8s_yaml = yaml.safe_load_all(config)
    return list(k8s_yaml)

def _check_config_kinds(config):
    """check if all the expected 'kinds' are present"""
    data = _get_data_from_config(config)
    nose.tools.eq_(sorted([item["kind"] for item in data]), EXPECTED_KINDS)

def _check_injected_files(config):
    """check if the injected files are present"""
    data = _get_data_from_config(config)
    nose.tools.eq_(len(data[1]["binaryData"]), len(TEST_FILES))

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_prepare_files():
    """prepare test files to inject"""
    # empty file
    Expect.expect_retval(RHUA, f"touch /var/lib/rhui{TEST_FILES[0]}")
    # file with noeol
    Expect.expect_retval(RHUA, f"echo -n qwerty > /var/lib/rhui{TEST_FILES[1]}")
    # other files will be taken directly from the container

def test_02_generate_examine_default_yaml():
    """generate and examine a basic (default) configuration"""
    configuration = RHUIManagerCLIInstance.k8s(RHUA)
    # no failures from the playbook?
    _check_playbook_recap(configuration["playbook"])
    # all the kinds in the YAML?
    _check_config_kinds(configuration["yaml"])

def test_03_generate_examine_custom_yaml():
    """generate and examine a configuration with custom files"""
    inject = [[tfile, f"/tmp/{basename(tfile)}"] for tfile in TEST_FILES]
    configuration = RHUIManagerCLIInstance.k8s(RHUA,
                                               f"{CUSTOM_CERTS_DIR}/ssl.key",
                                               f"{CUSTOM_CERTS_DIR}/ssl.crt",
                                               inject)
    # no failures from the playbook?
    _check_playbook_recap(configuration["playbook"])
    # all the kinds in the YAML?
    _check_config_kinds(configuration["yaml"])
    # all the files in the YAML?
    _check_injected_files(configuration["yaml"])

def test_04_bad_args():
    """check if incorrectly specified files to inject are rejected"""
    # format - try just a local file
    configuration = RHUIManagerCLIInstance.k8s(RHUA, inject="/etc/motd", raw=True)
    nose.tools.ok_("must be formed" in configuration["yaml"],
                   msg=f"oops: {configuration}")
    # not an absolute path
    configuration = RHUIManagerCLIInstance.k8s(RHUA, inject=[["foo"]])
    nose.tools.ok_("must be an absolute file path" in configuration["yaml"],
                   msg=f"oops: {configuration}")
    # no such file
    configuration = RHUIManagerCLIInstance.k8s(RHUA, inject=[["/foo"]])
    nose.tools.ok_("must exist" in configuration["yaml"],
                   msg=f"oops: {configuration}")
    # mode out of range
    configuration = RHUIManagerCLIInstance.k8s(RHUA, inject=[["/etc/issue", "/tmp/issue", "7777"]])
    nose.tools.ok_("not in the allowed range" in configuration["yaml"],
                   msg=f"oops: {configuration}")
    # mode not octal
    configuration = RHUIManagerCLIInstance.k8s(RHUA, inject=[["/etc/issue", "/tmp/issue", "8"]])
    nose.tools.ok_("cannot be parsed as an octal number" in configuration["yaml"],
                   msg=f"oops: {configuration}")

def test_99_cleanup():
    """clean up"""
    Expect.expect_retval(RHUA, f"rm -f /var/lib/rhui{TEST_FILES[0]}")
    Expect.expect_retval(RHUA, f"rm -f /var/lib/rhui{TEST_FILES[1]}")

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
