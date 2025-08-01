'''Entitlement management tests'''

from os.path import basename

import logging
import nose
from stitches.expect import Expect

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_entitlement import RHUIManagerEntitlements, \
                                                    BadCertificate, \
                                                    IncompatibleCertificate, \
                                                    MissingCertificate
from rhui5_tests_lib.rhuimanager_repo import RHUIManagerRepo
from rhui5_tests_lib.util import Util

logging.basicConfig(level=logging.DEBUG)

RHUA = ConMgr.connect()
DATADIR = "/root/test_files"
DATADIR_HOST = "/var/lib/rhui" + DATADIR

class TestEntitlement():
    '''
       class for entitlement tests
    '''

    @staticmethod
    def setup_class():
        '''
           announce the beginning of the test run
        '''
        print(f"*** Running {basename(__file__)}: ***")

    @staticmethod
    def test_01_initial_run():
        '''
            log in to RHUI
        '''
        RHUIManager.initial_run(RHUA)

    @staticmethod
    def test_02_list_rh_entitlements():
        '''
           list Red Hat content certificate entitlements
        '''
        entitlements = RHUIManagerEntitlements.list_rh_entitlements(RHUA)
        nose.tools.ok_(isinstance(entitlements, list))

    @staticmethod
    def test_03_list_cus_entitlements():
        '''
           list custom content certificate entitlements, expect none
        '''
        entlist = RHUIManagerEntitlements.list_custom_entitlements(RHUA)
        nose.tools.assert_equal(len(entlist), 0)

    @staticmethod
    def test_04_upload_rh_certificate():
        '''
           upload a new or updated Red Hat content certificate
        '''
        entlist = RHUIManagerEntitlements.upload_rh_certificate(RHUA)
        nose.tools.assert_not_equal(len(entlist), 0)

    @staticmethod
    def test_05_list_rh_entitlements():
        '''
           list Red Hat content certificate entitlements
        '''
        entitlements = RHUIManagerEntitlements.list_rh_entitlements(RHUA)
        nose.tools.ok_(entitlements)

    @staticmethod
    def test_06_add_custom_repo():
        '''
           add a custom repo to protect by a client entitlement certificate
        '''
        RHUIManagerRepo.add_custom_repo(RHUA, "custom-enttest")

    @staticmethod
    def test_07_list_cust_entitlements():
        '''
           list custom content certificate entitlements, expect one
        '''
        entlist = RHUIManagerEntitlements.list_custom_entitlements(RHUA)
        nose.tools.assert_equal(len(entlist), 1)

    @staticmethod
    def test_08_remove_custom_repo():
        '''
           remove the custom repo
        '''
        RHUIManagerRepo.delete_repo(RHUA, ["custom-enttest"])
        nose.tools.assert_equal(RHUIManagerRepo.list(RHUA), [])

    @staticmethod
    def test_09_list_cust_entitlements():
        '''
           list custom content certificate entitlements, expect none
        '''
        entlist = RHUIManagerEntitlements.list_custom_entitlements(RHUA)
        nose.tools.assert_equal(len(entlist), 0)

    @staticmethod
    def test_10_remove_certificates():
        '''
            clean up uploaded entitlement certificates
        '''
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_11_upload_exp_cert():
        '''
           upload an expired certificate, expect a proper refusal
        '''
        cert = "rhcert_expired.pem"
        nose.tools.assert_raises(BadCertificate,
                                 RHUIManagerEntitlements.upload_rh_certificate,
                                 RHUA,
                                 f"{DATADIR}/{cert}")

    @staticmethod
    def test_12_upload_incompat_cert():
        '''
           upload an incompatible certificate, expect a proper refusal
        '''
        cert = "rhcert_incompatible.pem"
        if Util.cert_expired(RHUA, f"{DATADIR_HOST}/{cert}"):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        nose.tools.assert_raises(IncompatibleCertificate,
                                 RHUIManagerEntitlements.upload_rh_certificate,
                                 RHUA,
                                 f"{DATADIR}/{cert}")

    @staticmethod
    def test_13_upload_semi_bad_cert():
        '''
           upload a certificate containing a mix of valid and invalid repos
        '''
        # for RHBZ#1588931 & RHBZ#1584527
        cert = "rhcert_partially_invalid.pem"
        if Util.cert_expired(RHUA, f"{DATADIR_HOST}/{cert}"):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        RHUIManagerEntitlements.upload_rh_certificate(RHUA, f"{DATADIR}/{cert}")

    @staticmethod
    def test_14_remove_semi_bad_cert():
        '''
            remove the certificate
        '''
        RHUIManager.remove_rh_certs(RHUA)

    @staticmethod
    def test_15_upload_nonexist_cert():
        '''
            try uploading a certificate file that does not exist, should be handled gracefully
        '''
        nose.tools.assert_raises(MissingCertificate,
                                 RHUIManagerEntitlements.upload_rh_certificate,
                                 RHUA,
                                 "/this_file_cant_be_there")
    @staticmethod
    def test_16_upload_empty_cert():
        '''
           upload a certificate that contains no entitlements
        '''
        # for RHBZ#1497028
        cert = "rhcert_empty.pem"
        if Util.cert_expired(RHUA, f"{DATADIR_HOST}/{cert}"):
            raise nose.exc.SkipTest("The given certificate has already expired.")
        nose.tools.assert_raises(IncompatibleCertificate,
                                 RHUIManagerEntitlements.upload_rh_certificate,
                                 RHUA,
                                 f"{DATADIR}/{cert}")


    @staticmethod
    def test_17_check_longlife_cert():
        '''
           check if a certificate that won't expire until a few decades later can be used
        '''
        cert = "entcert_longlife.crt"
        cmd = "rhua python3.11 -c \"from rhsm import certificate;" \
                                  f"certificate.create_from_file('{DATADIR}/{cert}')\""
        Expect.expect_retval(RHUA, cmd)

    @staticmethod
    def teardown_class():
        '''
           announce the end of the test run
        '''
        print(f"*** Finished running {basename(__file__)}. ***")
