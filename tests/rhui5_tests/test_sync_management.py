'''Repo syncing and scheduling tests'''

from os.path import basename

import logging
import nose
import yaml

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.pulp_api import PulpAPI
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_repo import RHUIManagerRepo
from rhui5_tests_lib.rhuimanager_sync import RHUIManagerSync
from rhui5_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements
from rhui5_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
DEFAULT_SOCK_READ_TIMEOUT = 1800
DEFAULT_TOTAL_TIMEOUT = 3600
CUSTOM_SOCK_READ_TIMEOUT = 2000
CUSTOM_TOTAL_TIMEOUT = 4000

class TestSync():
    '''
       class for repository synchronization tests
    '''

    def __init__(self):
        # Test the RHEL-7 x86_64 repo
        version = 7
        arch = "x86_64"
        with open("/etc/rhui5_tests/tested_repos.yaml", encoding="utf-8") as configfile:
            doc = yaml.safe_load(configfile)
            try:
                self.yum_repo_name = doc["yum_repos"][version][arch]["name"]
                self.yum_repo_version = doc["yum_repos"][version][arch]["version"]
                self.yum_repo_kind = doc["yum_repos"][version][arch]["kind"]
                self.yum_repo_id = doc["yum_repos"][version][arch]["id"]
            except KeyError as version:
                raise nose.SkipTest(f"No test repo defined for RHEL {version} on {arch}.")

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    def test_01_setup(self):
        '''add a repo to sync '''
        RHUIManager.initial_run(RHUA)
        RHUIManagerEntitlements.upload_rh_certificate(RHUA)
        entlist = RHUIManagerEntitlements.list_rh_entitlements(RHUA)
        nose.tools.assert_not_equal(len(entlist), 0)
        nose.tools.ok_(self.yum_repo_name in entlist)
        RHUIManagerRepo.add_rh_repo_by_repo(RHUA, [Util.format_repo(self.yum_repo_name,
                                                                    self.yum_repo_version,
                                                                    self.yum_repo_kind)])

    def test_02_sync_repo(self):
        '''sync a RH repo '''
        RHUIManagerSync.sync_repo(RHUA, [Util.format_repo(self.yum_repo_name,
                                                          self.yum_repo_version)])

    def test_03_check_sync_started(self):
        '''ensure that the sync started'''
        RHUIManagerSync.check_sync_started(RHUA, [Util.format_repo(self.yum_repo_name,
                                                                   self.yum_repo_version)])

    def test_04_wait_till_repo_synced(self):
        '''wait until the repo is synced'''
        RHUIManagerSync.wait_till_repo_synced(RHUA, [Util.format_repo(self.yum_repo_name,
                                                                      self.yum_repo_version)])

    def test_05_export_repo(self):
        '''export the repo'''
        RHUIManagerSync.export_repos(RHUA, [Util.format_repo(self.yum_repo_name,
                                                             self.yum_repo_version)])

    def test_06_check_default_timeouts(self):
        '''check the default timeout properties of the remote'''
        remote_data = PulpAPI.get_remote(RHUA, self.yum_repo_id)
        actual_sock_read_timeout = remote_data["sock_read_timeout"]
        nose.tools.eq_(actual_sock_read_timeout, DEFAULT_SOCK_READ_TIMEOUT)
        actual_total_timeout = remote_data["total_timeout"]
        nose.tools.eq_(actual_total_timeout, DEFAULT_TOTAL_TIMEOUT)

    def test_07_set_custom_timeouts(self):
        '''set custom timeout properties and resync the repo'''
        Config.set_rhui_tools_conf(RHUA, "rhui", "sock_read_timeout", str(CUSTOM_SOCK_READ_TIMEOUT))
        Config.set_rhui_tools_conf(RHUA, "rhui", "total_timeout", str(CUSTOM_TOTAL_TIMEOUT), False)
        RHUIManagerSync.sync_repo(RHUA, [Util.format_repo(self.yum_repo_name,
                                                          self.yum_repo_version)])

    def test_08_check_custom_timeouts(self):
        '''check the custom timeout properties of the remote'''
        remote_data = PulpAPI.get_remote(RHUA, self.yum_repo_id)
        actual_sock_read_timeout = remote_data["sock_read_timeout"]
        nose.tools.eq_(actual_sock_read_timeout, CUSTOM_SOCK_READ_TIMEOUT)
        actual_total_timeout = remote_data["total_timeout"]
        nose.tools.eq_(actual_total_timeout, CUSTOM_TOTAL_TIMEOUT)

    def test_99_cleanup(self):
        '''clean up'''
        Config.restore_rhui_tools_conf(RHUA)
        RHUIManagerRepo.delete_repo(RHUA,
                                    [Util.format_repo(self.yum_repo_name, self.yum_repo_version)])
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
