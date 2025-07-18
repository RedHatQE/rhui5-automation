"""Methods for the RHUI installer"""

from stitches.expect import Expect

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr, SUDO_USER_NAME

DEFAULT_IMAGES = {
                  "installer": "rhui5/installer",
                  "rhua": "rhui5/rhua",
                 }

class RHUIInstaller():
    """The rhui-installer command-line interface"""
    @staticmethod
    def rerun(installer_image=DEFAULT_IMAGES["installer"],
              rhua_image=DEFAULT_IMAGES["rhua"],
              other_args="",
              other_volumes=None,
              expect_trouble=False):
        """Rerun the installer (with the given arguments and/or volumes, if provided)"""
        rhua = ConMgr.connect()
        launchpad = ConMgr.connect(ConMgr.get_launchpad_hostname())
        registry, _, _ = Config.get_registry_data(rhua)
        cmd = f"cd /tmp ; sudo -u {SUDO_USER_NAME} " \
              f"podman run --rm " \
              f"-v /home/{SUDO_USER_NAME}/.ssh/id_ecdsa_launchpad:/ssh-keyfile:Z"
        if other_volumes:
            for key, value in other_volumes.items():
                cmd += f" -v {value}:/{key}:Z"
        cmd = f"{cmd} {registry}/{installer_image} rhui-installer " \
              f"--rhua-container-image {rhua_image} " \
              f"--target-host {ConMgr.get_rhua_hostname()} " \
              f"--target-user {SUDO_USER_NAME} " \
              f"--rerun {other_args}"
        Expect.expect_retval(launchpad, cmd, 2 if expect_trouble else 0, 300)

    @staticmethod
    def usage():
        """Get help (the usage message) from the installer"""
        rhua = ConMgr.connect()
        launchpad = ConMgr.connect(ConMgr.get_launchpad_hostname())
        registry, _, _ = Config.get_registry_data(rhua)
        cmd = f"cd /tmp ; sudo -u {SUDO_USER_NAME} " \
              f"podman run --rm {registry}/rhui5/installer rhui-installer --help"
        _, stdout, _ = launchpad.exec_command(cmd)
        output = stdout.read().decode()
        return output
