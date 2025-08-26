"""Helper Functions for RHUI Test Cases"""

from os.path import basename, join
import time

from stitches.expect import Expect
import nose
import yaml

from rhui5_tests_lib.cfg import Config, LEGACY_CA_DIR, RHUI_ROOT

class Helpers():
    """actions that may be repeated in specific test cases and do not belong in general utils"""
    @staticmethod
    def break_hostname(connection, hostname):
        """override DNS by setting a fake IP address in /etc/hosts"""
        tweak_hosts_cmd = fr"rhua sed -i.bak -c 's/^[^ ]*\(.*{hostname}\)$/256.0.0.0\1/' /etc/hosts"
        Expect.expect_retval(connection, tweak_hosts_cmd)

    @staticmethod
    def unbreak_hostname(connection):
        """undo the changes made by break_hostname"""
        Expect.expect_retval(connection, "rhua cp /etc/hosts.bak /etc/hosts")
        Expect.expect_retval(connection, "rhua rm -f /etc/hosts.bak")

    @staticmethod
    def cds_in_haproxy_cfg(connection, cds):
        """check if the CDS is present in the HAProxy configuration"""
        _, stdout, _ = connection.exec_command("ha cat /etc/haproxy/haproxy.cfg")
        cfg = stdout.read().decode()
        return f"server {cds} {cds}:443 check" in cfg

    @staticmethod
    def check_service(connection, service, container_alias=""):
        """check if the given service is running"""
        cmd = f"{container_alias} " if container_alias else ""
        cmd += f"systemctl is-active {service}"
        return connection.recv_exit_status(cmd) == 0

    @staticmethod
    def check_mountpoint(connection, mountpoint):
        """check if something is mounted in the given directory"""
        return connection.recv_exit_status(f"mountpoint {mountpoint}") == 0

    @staticmethod
    def encode_sos_command(command, plugin="rhui"):
        """replace special characters with safe ones and compose the path in the archive"""
        # spaces become underscores
        # slashes become dots
        command = command.replace(" ", "_")
        command = command.replace("/", ".")
        # the actual file is in the /commands directory in the archive
        return join("/sos_commands", plugin, command)

    @staticmethod
    def is_registered(connection):
        """return True if the remote host is registered with RHSM, or False otherwise"""
        return connection.recv_exit_status("subscription-manager identity") == 0

    @staticmethod
    def restart_rhui_services(connection):
        """restart RHUI services on the remote host (according to the determined type)"""
        services = {
                    "rhua":    [
                                "nginx",
                                "pulpcore-api",
                                "pulpcore-content",
                                "pulpcore-worker@*"
                               ],
                    "cds":     [
                                "nginx",
                                "gunicorn-auth",
                                "gunicorn-content_manager",
                                "gunicorn-mirror"
                               ],
                    "ha": [
                                "haproxy"
                               ]
                   }
        fun = None
        for helper_function in services:
            _, stdout, _ = connection.exec_command(f"{helper_function} -h")
            output = stdout.read().decode().strip()
            if output:
                fun = helper_function
                break
        if not fun:
            raise ValueError("Unknown RHUI node type") from None
        get_pids_cmd = f"{fun} systemctl -p MainPID show %s | awk -F = '/PID/ {{ print $2 }}'"
        # fetch the current PIDs
        _, stdout, _ = connection.exec_command(get_pids_cmd % " ".join(services[fun]))
        oldpids = list(map(int, stdout.read().decode().splitlines()))
        # actually run the restart script, should exit with 0
        Expect.expect_retval(connection, f"{fun} rhui-services-restart", timeout=20)
        # fetch PIDs again
        _, stdout, _ = connection.exec_command(get_pids_cmd % " ".join(services[fun]))
        newpids = list(map(int, stdout.read().decode().splitlines()))
        # 0 in the output means the service is down (or doesn't exist)
        nose.tools.ok_(0 not in oldpids, msg="an inactive (or unknown) service was detected")
        # the number of PIDs should remain the same
        nose.tools.eq_(len(oldpids), len(newpids))
        # none of the new PIDs should be among the old PIDs; that would mean the service
        # wasn't restarted
        for pid in newpids:
            nose.tools.ok_(pid not in oldpids, msg=f"{pid} remained running")

    @staticmethod
    def add_legacy_ca(connection, local_ca_file):
        """configure a CDS to accept a legacy CA"""
        # this method takes the path to the local CA file and configures that CA on a CDS
        ca_basename = basename(local_ca_file)
        connection.sftp.put(local_ca_file, f"/var/lib/rhui/root/{ca_basename}")
        Expect.expect_retval(connection, f"cds mkdir -p {LEGACY_CA_DIR}")
        Expect.expect_retval(connection, f"cds mv /root/{ca_basename} {LEGACY_CA_DIR}")
        Config.set_rhui_tools_conf(connection, "rhui", "log_level", "DEBUG", False)
        Expect.expect_retval(connection, "cds rhui-services-restart")

    @staticmethod
    def del_legacy_ca(connection):
        """unconfigure legacy CA certificates"""
        # this method purges the legacy CA dir on a CDS
        Expect.expect_retval(connection, f"cds rm -rf {LEGACY_CA_DIR}")
        Config.set_rhui_tools_conf(connection, "rhui", "log_level", "INFO", False)
        Expect.expect_retval(connection, "cds yum -y install logrotate")
        Expect.expect_retval(connection, "cds logrotate -f /etc/logrotate.d/nginx")
        Expect.expect_retval(connection, "cds rhui-services-restart")

    @staticmethod
    def get_repos_from_yaml(connection, yaml_file):
        """load the specified YAML file with repo_ids and return them as a list"""
        _, stdout, _ = connection.exec_command(f"rhua cat {yaml_file}")
        import_repo_data = yaml.safe_load(stdout)
        repo_ids = import_repo_data["repo_ids"]
        return repo_ids

    @staticmethod
    def copy_repo_mappings(connection):
        """copy the repo cache from extra files to the cache dir to speed up repo management"""
        # if this method is called right after the cert upload is executed, the cert may not
        # be available yet; let's sleep
        time.sleep(7)
        _, stdout, _ = connection.exec_command("rhua ls /etc/pki/rhui/redhat/")
        cert_files = stdout.read().decode().splitlines()
        if not cert_files:
            raise RuntimeError("No uploaded certificate was found.")
        if len(cert_files) > 1:
            raise RuntimeError("More than one uploaded certificate was found.")
        mapping_file = f"/var/lib/rhui/cache/{cert_files[0]}.mappings"
        Expect.expect_retval(connection,
                             f"cp -a /var/lib/rhui/root/test_files/rhcert.mappings {mapping_file}")

    @staticmethod
    def get_artifacts(connection):
        """return a list of all artifacts"""
        basedir = f"{RHUI_ROOT}/pulp3/artifact/"
        _, stdout, _ = connection.exec_command(f"find {basedir} -type f")
        artifacts_full_paths = stdout.read().decode().splitlines()
        artifacts = [artifact.replace(basedir, "") for artifact in artifacts_full_paths]
        return artifacts

    @staticmethod
    def clear_symlinks(connection):
        """clear the symlinks to artifacts"""
        Expect.expect_retval(connection, f"rm -rf {RHUI_ROOT}/symlinks/pulp")
        time.sleep(7)
