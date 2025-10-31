"""Methods for the RHUI installer"""

from stitches.expect import Expect

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr, SUDO_USER_NAME

class RHUIInstaller():
    """The rhui-installer command-line interface"""
    @staticmethod
    def rerun(installer_image="",
              rhua_image="",
              other_args="",
              other_volumes=None,
              expect_trouble=False):
        """Rerun the installer (with the given arguments and/or volumes, if provided)"""
        rhua = ConMgr.connect()
        launchpad = ConMgr.connect(ConMgr.get_launchpad_hostname())
        registry_data = Config.get_registry_data(rhua)
        registry = registry_data[0]
        default_installer_image = registry_data[3]
        default_rhua_image = registry_data[4]
        cmd = f"cd /tmp ; sudo -u {SUDO_USER_NAME} " \
              f"podman run --rm " \
              f"-v /home/{SUDO_USER_NAME}/.ssh/id_ecdsa_launchpad:/ssh-keyfile:Z"
        # if the answers file (still) exists on the launchpad, re-use it, too
        answers_exist = launchpad.recv_exit_status("test -f /tmp/answers.yaml") == 0
        if answers_exist:
            cmd += " -v /tmp/answers.yaml:/answers.yaml:Z"
        # if the auth file (still) exists on the launchpad, re-use it, too
        auth_exists = launchpad.recv_exit_status("test -f /tmp/auth.json") == 0
        if auth_exists:
            cmd += " -v /tmp/auth.json:/auth.json:Z"
        if other_volumes:
            for key, value in other_volumes.items():
                cmd += f" -v {value}:/{key}:Z"
        cmd += f" {registry}/{installer_image or default_installer_image} rhui-installer "
        if rhua_image:
            cmd += f"--rhua-container-image {rhua_image} "
        elif default_rhua_image:
            cmd += f"--rhua-container-image {default_rhua_image} "
        cmd = f"{cmd}" \
              f"--target-host {ConMgr.get_rhua_hostname()} " \
              f"--target-user {SUDO_USER_NAME} " \
              f"--rerun {other_args}"
        Expect.expect_retval(launchpad, cmd, 2 if expect_trouble else 0, 300)

    @staticmethod
    def usage():
        """Get help (the usage message) from the installer"""
        rhua = ConMgr.connect()
        launchpad = ConMgr.connect(ConMgr.get_launchpad_hostname())
        registry, _, _, installer_image, _, _, _ = Config.get_registry_data(rhua)
        cmd = f"cd /tmp ; sudo -u {SUDO_USER_NAME} " \
              f"podman run --rm {registry}/{installer_image} rhui-installer --help"
        _, stdout, _ = launchpad.exec_command(cmd)
        output = stdout.read().decode()
        return output
