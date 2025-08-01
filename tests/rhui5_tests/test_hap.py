'''HAProxy management tests'''

from os.path import basename
import re
import time

import logging
import nose
from stitches.expect import CTRL_C, Expect

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.helpers import Helpers
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_instance import RHUIManagerInstance, NoSuchInstance

logging.basicConfig(level=logging.DEBUG)

HA_HOSTNAME = ConMgr.get_lb_hostname()

RHUA = ConMgr.connect()
HAPROXY = ConMgr.connect(HA_HOSTNAME)

def setup():
    '''
       announce the beginning of the test run
    '''
    print(f"*** Running {basename(__file__)}: ***")

def test_01_initial_run():
    '''
        log in to RHUI
    '''
    RHUIManager.initial_run(RHUA)

def test_02_list_empty_hap():
    '''
        check if there are no HAProxy Load-balancers
    '''
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_equal(hap_list, [])

def test_03_add_hap():
    '''
        add an HAProxy Load-balancer
    '''
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME)

def test_04_list_hap():
    '''
        check if the HAProxy Load-balancer was added
    '''
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])

def test_05_readd_hap():
    '''
        add the HAProxy Load-balancer again (reapply the configuration)
    '''
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME, update=True)

def test_06_list_hap():
    '''
        check if the HAProxy Load-balancer is still tracked
    '''
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])

def test_07_delete_nonexisting_hap():
    '''
        try deleting an untracked HAProxy Load-balancer, should be rejected (by rhui5_tests_lib)
    '''
    nose.tools.assert_raises(NoSuchInstance,
                             RHUIManagerInstance.delete,
                             RHUA,
                             "loadbalancers",
                             ["foo" + HA_HOSTNAME])

def test_08_delete_hap():
    '''
        delete the HAProxy Load-balancer
    '''
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [HA_HOSTNAME])

def test_09_list_hap():
    '''
        list HAProxy Load-balancers again, expect none
    '''
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_equal(hap_list, [])

def test_10_check_cleanup():
    '''
        check if the haproxy service was stopped
    '''
    nose.tools.ok_(not Helpers.check_service(HAPROXY, "haproxy", "ha"),
                   msg="haproxy is still running on " + HA_HOSTNAME)

def test_11_add_hap_uppercase():
    '''
        add (and delete) an HAProxy Load-balancer with uppercase characters
    '''
    # for RHBZ#1572623
    chunks = HA_HOSTNAME.split(".")
    chunks[0] = chunks[0].upper()
    host_up = ".".join(chunks)
    nose.tools.assert_not_equal(HA_HOSTNAME, host_up)
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", host_up)
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [host_up])
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_equal(hap_list, [])

def test_12_delete_unreachable():
    '''
    add a Load-balancer, make it unreachable, and see if it can still be deleted from the RHUA
    '''
    # for RHBZ#1639996
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME)
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])

    Helpers.break_hostname(RHUA, HA_HOSTNAME)

    # delete it
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [HA_HOSTNAME])
    # check it
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_equal(hap_list, [])

    Helpers.unbreak_hostname(RHUA)

    # the node remains configured (haproxy)... unconfigure it properly
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME)
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [HA_HOSTNAME])

def test_13_delete_select_0():
    '''
    add an LB and see if no issue occurs if it and "a zeroth" (ghost) LBs are selected for deletion
    '''
    # for RHBZ#1305612
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME)
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])

    # try the deletion
    RHUIManager.screen(RHUA, "loadbalancers")
    Expect.enter(RHUA, "d")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "0")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "1")
    Expect.expect(RHUA, "Enter value")
    Expect.enter(RHUA, "c")
    state = Expect.expect_list(RHUA,
                               [(re.compile(".*Are you sure.*", re.DOTALL), 1),
                                (re.compile(".*An unexpected error.*", re.DOTALL), 2)])
    if state == 1:
        Expect.enter(RHUA, "y")
        RHUIManager.quit(RHUA, timeout=180)
    else:
        Expect.enter(RHUA, "q")
        time.sleep(5)

    # the LB list ought to be empty now; if not, delete the LB and fail
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    if hap_list:
        RHUIManagerInstance.delete_all(RHUA, "loadbalancers")
        raise AssertionError(f"The LB list is not empty after the deletion attempt: {hap_list}")

def test_14_file_paths():
    '''
       check if absolute and valid paths are required
    '''
    Expect.enter(RHUA, "rhua touch /motd")
    time.sleep(5)
    RHUIManager.screen(RHUA, "loadbalancers")
    Expect.enter(RHUA, "a")
    Expect.expect(RHUA, "Hostname")
    Expect.enter(RHUA, "foo")
    Expect.expect(RHUA, "Username")
    Expect.enter(RHUA, "bar")
    Expect.expect(RHUA, "Absolute")
    Expect.enter(RHUA, "baz")
    Expect.expect(RHUA, "Cannot find file")
    Expect.enter(RHUA, "motd")
    state = Expect.expect_list(RHUA,
                               [(re.compile(".*Relative path supplied.*", re.DOTALL), 1),
                                (re.compile(".*Checking SSH authentication.*", re.DOTALL), 2)])
    if state == 2:
        Expect.enter(RHUA, "q")
        raise AssertionError("The relative path was accepted")
    Expect.enter(RHUA, CTRL_C)
    Expect.enter(RHUA, "q")
    time.sleep(5)
    Expect.enter(RHUA, "rhua rm -f /motd")

def test_15_custom_haproxy_config():
    '''
       check the ability to install HAProxy with a custom configuration file
    '''
    default_template = "/usr/share/rhui-tools/templates/haproxy.cfg"
    find = "  maxconn  4000"
    replace_with = "  maxconn  3600"
    cfg = "/root/myhaproxy.cfg"
    Expect.expect_retval(RHUA, f"rhua cp {default_template} {cfg}")
    Expect.expect_retval(RHUA, f"rhua sed -i 's/{find}/{replace_with}/' {cfg}")
    RHUIManagerInstance.add_instance(RHUA, "loadbalancers", HA_HOSTNAME, haproxy_config_file=cfg)
    # check if the node was added
    hap_list = RHUIManagerInstance.list(RHUA, "loadbalancers")
    nose.tools.assert_not_equal(hap_list, [])
    # check if the configuration file was actually used
    _, stdout, _ = HAPROXY.exec_command("ha cat /etc/haproxy/haproxy.cfg")
    fetched_cfg = stdout.read().decode().splitlines()
    nose.tools.ok_(replace_with in fetched_cfg)
    # delete the node
    RHUIManagerInstance.delete(RHUA, "loadbalancers", [HA_HOSTNAME])
    Expect.expect_retval(RHUA, f"rhua rm -f {cfg}")

def teardown():
    '''
       announce the end of the test run
    '''
    print(f"*** Finished running {basename(__file__)}. ***")
