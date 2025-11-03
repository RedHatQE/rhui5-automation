''' Methods to manage other RHUI nodes '''

from rhui5_tests_lib.cfg import Config
from rhui5_tests_lib.conmgr import ConMgr, SUDO_USER_NAME, SUDO_USER_KEY
from rhui5_tests_lib.helpers import Helpers

def _validate_node_type(text):
    '''
    Check if the given text is a valid RHUI node type.
    '''
    ok_types = ["cds", "haproxy"]
    if text not in ok_types:
        raise ValueError(f"Unsupported node type: '{text}'. Use one of: {ok_types}.")

class RHUIManagerCLIInstance():
    '''
    The rhui-manager command-line interface to control CDS and HAProxy nodes.
    '''
    @staticmethod
    def list(connection, node_type):
        '''
        Return a list of CDS or HAProxy nodes (hostnames).
        '''
        _validate_node_type(node_type)
        _, stdout, _ = connection.exec_command(f"rhua rhui-manager {node_type} list")
        lines = stdout.read().decode()
        nodes = [line.split(":")[1].strip() for line in lines.splitlines() if "Hostname:" in line]
        return nodes

    @staticmethod
    def add(connection, node_type,
            hostname="",
            image="",
            ssl_crt="", ssl_key="",
            haproxy_config_file="",
            force=False, unsafe=False):
        '''
        Add a CDS or HAProxy node.
        If hostname is empty, ConMgr will be used to determine the default one for the node type
        Return True if the command exited with 0, and False otherwise.
        Note to the caller: Trust no one! Check for yourself if the node has really been added.
        '''
        _validate_node_type(node_type)
        if node_type == "haproxy" and (ssl_crt or ssl_key):
            raise ValueError("SSL cert and/or key is meaningless when adding an HAproxy node")
        if not hostname:
            if node_type == "cds":
                hostname = ConMgr.get_cds_hostnames()[0]
            elif node_type == "haproxy":
                hostname = ConMgr.get_lb_hostname()
        # check if the auth file exists
        auth_exists = Helpers.auth_exists(connection)
        cmd = f"rhua rhui-manager {node_type} add " + \
              f"--hostname {hostname} --ssh_user {SUDO_USER_NAME} --keyfile_path {SUDO_USER_KEY}"

        registry_data = Config.get_registry_data(connection)
        registry, username, password = registry_data[:3]
        default_cds_image = registry_data[5]
        default_haproxy_image = registry_data[6]
        default_image = default_cds_image if node_type == "cds" else default_haproxy_image

        cmd += f" --container_registry {registry}"
        if not auth_exists:
            cmd += f" --registry_username {username}"
            cmd += f" --registry_password {password}"
        if image:
            cmd += f" --container_image {image}"
        elif default_image:
            cmd += f" --container_image {default_image}"
        if ssl_crt:
            cmd += f" --user_supplied_ssl_crt {ssl_crt}"
        if ssl_key:
            cmd += f" --user_supplied_ssl_key {ssl_key}"
        if haproxy_config_file:
            cmd += f" --config {haproxy_config_file}"
        if force:
            cmd += " --force"
        if unsafe:
            cmd += " --unsafe"
        return connection.recv_exit_status(cmd, timeout=600) == 0

    @staticmethod
    def reinstall(connection, node_type, hostname="", all_nodes=False):
        '''
        Reinstall a CDS or HAProxy node. One hostname or all tracked nodes.
        Return True if the command exited with 0, and False otherwise.
        '''
        _validate_node_type(node_type)
        if all_nodes:
            cmd = f"rhua rhui-manager {node_type} reinstall --all"
        elif hostname:
            cmd = f"rhua rhui-manager {node_type} reinstall --hostname {hostname}"
        else:
            raise ValueError("Either a hostname or '--all' must be used.")
        return connection.recv_exit_status(cmd, timeout=540) == 0

    @staticmethod
    def delete(connection, node_type, hostnames="", force=False):
        '''
        Reinstall one or more CDS or HAProxy nodes.
        Return True if the command exited with 0, and False otherwise.
        Note to the caller: Trust no one! Check for yourself if the nodes have really been deleted.
        '''
        _validate_node_type(node_type)
        if not hostnames:
            if node_type == "cds":
                hostnames = ConMgr.get_cds_hostnames()
            elif node_type == "haproxy":
                hostnames = [ConMgr.get_lb_hostname()]
        cmd = f"rhua rhui-manager {node_type} delete --hostnames {','.join(hostnames)}"
        if force:
            cmd += " --force"
        return connection.recv_exit_status(cmd, timeout=180) == 0
