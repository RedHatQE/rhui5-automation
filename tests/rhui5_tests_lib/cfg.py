"""Functions for the RHUI Configuration"""

from configparser import ConfigParser

from stitches.expect import Expect

RHUI_CFG_STATIC = "/etc/rhui-static/rhui-tools-static.conf"
RHUI_CFG_CUSTOM = "/etc/rhui/rhui-tools.conf"
RHUI_CFG_HOST = "/var/lib/rhui/*/*/rhui-tools.conf"
RHUI_CFG_HOST_BAK_DIR = "/var/lib/rhui/root"

RHUI_ROOT = "/var/lib/rhui/remote_share"
CREDS = "/root/test_files/credentials.conf"
LEGACY_CA_DIR = "/etc/pki/rhui/legacy"

OFFICIAL_REGISTRY = "registry.redhat.io"

class Config():
    """reading from and writing to RHUI configuration files"""
    @staticmethod
    def get_credentials(connection, site="rh"):
        """get the user name and password for the given site from the RHUA"""
        creds_cfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"rhua cat {CREDS}")
        creds_cfg.read_file(stdout)
        if not creds_cfg.has_section(site):
            raise RuntimeError(f"section {site} does not exist in {CREDS}")
        if not creds_cfg.has_option(site, "username"):
            raise RuntimeError(f"username does not exist inside {site} in {CREDS}")
        if not creds_cfg.has_option(site, "password"):
            raise RuntimeError(f"password does not exist inside {site} in {CREDS}")
        credentials = [creds_cfg.get(site, "username"), creds_cfg.get(site, "password")]
        return credentials

    @staticmethod
    def get_registry_data(connection):
        """get the RHUI container image registry hostname and credentials"""
        creds_cfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"rhua cat {CREDS}")
        creds_cfg.read_file(stdout)
        if not creds_cfg.has_section("registry"):
            if not creds_cfg.has_section("rh"):
                raise RuntimeError(f"neither a 'registry' nor an 'rh' section exists in {CREDS}")
            section = "rh"
        else:
            section = "registry"
            if not creds_cfg.has_option(section, "hostname"):
                raise RuntimeError(f"hostname does not exist inside 'registry' in {CREDS}")
        if not creds_cfg.has_option(section, "username"):
            raise RuntimeError(f"username does not exist inside '{section}' in {CREDS}")
        if not creds_cfg.has_option(section, "password"):
            raise RuntimeError(f"password does not exist inside '{section}' in {CREDS}")
        credentials = [OFFICIAL_REGISTRY if section == "rh" else creds_cfg.get(section,
                                                                               "hostname"),
                       creds_cfg.get(section, "username"),
                       creds_cfg.get(section, "password"),
                       creds_cfg.get(section,
                                     "installer_image",
                                     fallback="rhui5/installer-rhel9"),
                       creds_cfg.get(section, "rhua_image", fallback=""),
                       creds_cfg.get(section, "cds_image", fallback=""),
                       creds_cfg.get(section, "haproxy_image", fallback="")]
        return credentials

    @staticmethod
    def get_from_rhui_tools_conf(connection, section, option):
        """get the value of the given option from the given section in RHUI configuration"""
        # raises standard configparser exceptions on failures
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"rhua cat {RHUI_CFG_STATIC}")
        rhuicfg.read_file(stdout)
        _, stdout, _ = connection.exec_command(f"rhua cat {RHUI_CFG_CUSTOM}")
        rhuicfg.read_file(stdout)
        return rhuicfg.get(section, option)

    @staticmethod
    def get_registry_url(site, connection=""):
        """get the URL for the given container registry or for the saved one (use "default" then)"""
        if site == "default":
            return Config.get_from_rhui_tools_conf(connection, "container", "registry_url")
        urls = {"rh": f"https://{OFFICIAL_REGISTRY}",
                "quay": "https://quay.io",
                "gitlab": "https://registry.gitlab.com"}
        if site in urls:
            return urls[site]
        return None

    @staticmethod
    def set_registry_credentials(connection, site="rh", data="", backup=True):
        """put container registry credentials into the RHUI configuration file"""
        # if "site" isn't in credentials.conf, then "data" is supposed to be:
        # [username, password, url], or just [url] if no authentication is to be used for "site";
        # first get the RHUI config file
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"rhua cat {RHUI_CFG_CUSTOM}")
        rhuicfg.read_file(stdout)
        # add the relevant config section if it's not there yet
        if not rhuicfg.has_section("container"):
            rhuicfg.add_section("container")
        # then get the credentials
        try:
            credentials = Config.get_credentials(connection, site)
            url = Config.get_registry_url(site)
            rhuicfg.set("container", "registry_url", url)
            rhuicfg.set("container", "registry_auth", "True")
        except RuntimeError:
            # the site isn't defined in the credentials file -> use the data passed to this method
            if len(data) == 3:
                rhuicfg.set("container", "registry_url", data[2])
                rhuicfg.set("container", "registry_auth", "True")
                credentials = data[:-1]
            elif len(data) == 1:
                rhuicfg.set("container", "registry_url", data[0])
                rhuicfg.set("container", "registry_auth", "False")
                credentials = False
            else:
                raise ValueError("the passed data is invalid") from None
        # if credentials are known, add them into the configuration
        if credentials:
            rhuicfg.set("container", "registry_username", credentials[0])
            rhuicfg.set("container", "registry_password", credentials[1])
        # otherwise, make sure the options don't exists in the configuration
        else:
            rhuicfg.remove_option("container", "registry_username")
            rhuicfg.remove_option("container", "registry_password")
        # back up the original config file (unless prevented)
        if backup:
            Config.backup_rhui_tools_conf(connection)
        # save (rewrite) the configuration file with the newly added credentials
        stdin, _, _ = connection.exec_command(f"cat > {RHUI_CFG_HOST}")
        rhuicfg.write(stdin)

    @staticmethod
    def set_rhui_tools_conf(connection, section, option, value, backup=True):
        """set a configuration option in the RHUI tools configuration file"""
        rhuicfg = ConfigParser()
        _, stdout, _ = connection.exec_command(f"cat {RHUI_CFG_HOST}")
        rhuicfg.read_file(stdout)
        if section not in rhuicfg.sections():
            rhuicfg.add_section(section)
        rhuicfg.set(section, option, value)
        # back up the original config file (unless prevented)
        if backup:
            Config.backup_rhui_tools_conf(connection)
        # save (rewrite) the configuration file
        stdin, _, _ = connection.exec_command(f"cat > {RHUI_CFG_HOST}")
        rhuicfg.write(stdin)

    @staticmethod
    def set_sync_policy(connection,
                        default_sync_policy="",
                        immediate_repoid_regex="",
                        on_demand_repoid_regex="",
                        backup=True):
        """set the default sync policy or policy regexes"""
        # validate the input if setting the default policy
        if default_sync_policy:
            types = {"immediate", "on_demand"}
            if default_sync_policy not in types:
                raise ValueError(f"Unsupported type: '{default_sync_policy}'. Use one of: {types}.")
            Config.set_rhui_tools_conf(connection,
                                       "rhui",
                                       "default_sync_policy",
                                       default_sync_policy,
                                       backup=backup)
        elif immediate_repoid_regex:
            Config.set_rhui_tools_conf(connection,
                                       "rhui",
                                       "immediate_repoid_regex",
                                       immediate_repoid_regex,
                                       backup=backup)
        elif on_demand_repoid_regex:
            Config.set_rhui_tools_conf(connection,
                                       "rhui",
                                       "on_demand_repoid_regex",
                                       on_demand_repoid_regex,
                                       backup=backup)
        else:
            raise ValueError("Must set the default policy or a regex.")

    @staticmethod
    def backup_rhui_tools_conf(connection):
        """create a backup copy of the RHUI tools configuration file"""
        Expect.expect_retval(connection,
                             f"cp -a {RHUI_CFG_HOST} {RHUI_CFG_HOST_BAK_DIR}/rhui-tools.bak")

    @staticmethod
    def edit_rhui_tools_conf(connection, opt, val, backup=True):
        """set an option in the RHUI tools configuration file to the given value"""
        cmd = "sed -i"
        if backup:
            cmd += ".bak"
        cmd = f"{cmd} 's/^{opt}.*/{opt}: {val}/' {RHUI_CFG_CUSTOM}"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def restore_rhui_tools_conf(connection):
        """restore the backup copy of the RHUI tools configuration file"""
        Expect.expect_retval(connection,
                             f"mv -f {RHUI_CFG_HOST_BAK_DIR}/rhui-tools.bak {RHUI_CFG_HOST}")
