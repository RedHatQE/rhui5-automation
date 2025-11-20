""" RHSM integration in RHUI """

from stitches.expect import Expect

from rhui5_tests_lib.helpers import Helpers
from rhui5_tests_lib.cfg import Config

class RHSMRHUI():
    """Subscription management for RHUI"""
    @staticmethod
    def register_system(connection, username="", password="", fail_if_registered=False):
        """register with RHSM"""
        # if username or password isn't specified, it will be obtained using
        # the get_credentials method on the remote host -- only usable with the RHUA
        # if the system is already registered, it will be unregistered first,
        # unless fail_if_registered == True
        if fail_if_registered and Helpers.is_registered(connection):
            raise RuntimeError("The system is already registered.")
        if not username or not password:
            username, password = Config.get_credentials(connection)
        Expect.expect_retval(connection,
                             "subscription-manager register --force --type rhui " +
                             f"--username {username} --password {password}",
                             timeout=60)

    @staticmethod
    def unregister_system(connection):
        """unregister from RHSM"""
        Expect.expect_retval(connection, "subscription-manager unregister", timeout=20)

    @staticmethod
    def copy_entitlement(connection, directory):
        """copy test entitlement files from the specified test dir to the entitlement dir"""
        source_directory = f"/var/lib/rhui/root/test_files/{directory}"
        Expect.expect_retval(connection, f"cp {source_directory}/*.pem /etc/pki/entitlement/")

    @staticmethod
    def clear_entitlement(connection):
        """clear the entitlement files"""
        dirs_to_purge = ["/etc/pki/entitlement", "/var/lib/rhui/pki/entitlement"]
        Expect.expect_retval(connection, f"rm -rf {' '.join([d + '/*' for d in dirs_to_purge])}")
