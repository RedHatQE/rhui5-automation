"""RHUI API calls"""

import json
import os
import subprocess
import urllib.parse

from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.util import Util

RHUA_HOSTNAME = ConMgr.get_rhua_hostname()

RHUI_CA_CERT = "/root/ca.crt"
COOKIE_JAR = "/root/cookie.jar"
JSON_HEADER = "-H 'Content-Type: application/json'"
BASE_COMMAND = f"curl --no-progress-meter --cacert {RHUI_CA_CERT} -b {COOKIE_JAR} {JSON_HEADER}"
BASE_URL = f"https://{RHUA_HOSTNAME}/rhui/api/v1/"
BASE = f"{BASE_COMMAND} {BASE_URL}"

class RHUIAPI():
    """The RHUI manager API"""
    ### IMPORTANT
    ### Before you start calling the API methods, make sure you've run the first two
    ### get_* methods.
    ###
    @staticmethod
    def get_ca_cert(connection):
        """get the RHUI CA cert so that future API calls can use secure connections"""
        remote_ca_cert = "/var/lib/rhui/pki/certs/ca.crt"
        Util.fetch(connection, remote_ca_cert, RHUI_CA_CERT)

    @staticmethod
    def get_cookie(connection):
        """fetch a rhuiSessionId cookie"""
        # first, get the RHUI admin password
        password = Util.get_saved_password(connection)
        # use -b to actually save the cookie file rather than load it
        data = {}
        data["username"] = "admin"
        data["password"] = password
        cmd = f"{BASE_COMMAND.replace(' -b ', ' -c ')} -d '{json.dumps(data)}' {BASE_URL}login"
        return subprocess.getoutput(cmd)

    @staticmethod
    def del_cookie():
        """delete the fetched rhuiSessionId cookie"""
        os.remove(COOKIE_JAR)

    @staticmethod
    def repo_unused():
        """return a list of repos that are entitled but not added to RHUI"""
        return subprocess.getoutput(f"{BASE}repo/unused")

    @staticmethod
    def repo_add(repo_ids="", product_names="", sync_now=False):
        """add repo specified either by product names or by IDs"""
        data = {}
        if repo_ids:
            data["repo_ids"] = repo_ids
        elif product_names:
            data["product_names"] = product_names
        if sync_now:
            data["sync_now"] = True
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}repo/add"
        return subprocess.getoutput(cmd)

    @staticmethod
    def repo_list(sync_details=False):
        """list repos"""
        query = "?sync_details=True" if sync_details else ""
        return subprocess.getoutput(f"{BASE}repo/list{query}")

    @staticmethod
    def repo_info(repo_id, sync_details=False):
        """get information about a repo"""
        query = "?sync_details=True" if sync_details else ""
        return subprocess.getoutput(f"{BASE}repo/info/{repo_id}{query}")

    @staticmethod
    def repo_sync(repo_ids="", sync_all=False, cron=False):
        """sync repos, specified or all"""
        data = {}
        if repo_ids:
            data["repo_ids"] = repo_ids
        elif sync_all:
            data["all"] = True
        if cron:
            data["cron"] = True
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}repo/sync"
        return subprocess.getoutput(cmd)

    @staticmethod
    def repo_delete(repo_ids=""):
        """delete repos"""
        data = {}
        data["repo_ids"] = repo_ids
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}repo/delete"
        return subprocess.getoutput(cmd)

    @staticmethod
    def repo_create_custom(repo_id,
                           display_name="",
                           path="",
                           protected=False,
                           gpg_public_keys="",
                           redhat_content=False):
        """create a custom repo"""
        data = {}
        data["repo_id"] = repo_id
        if display_name:
            data["display_name"] = display_name
        if path:
            data["path"] = path
        if protected:
            data["protected"] = True
        if gpg_public_keys:
            data["gpg_public_keys"] = gpg_public_keys
        if redhat_content:
            data["redhat_content"] = True
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}repo/create_custom"
        return subprocess.getoutput(cmd)

    @staticmethod
    def packages_list(repo_id, field="", name="", namepart="", version="", release=""):
        """list packages in the repo"""
        query_parts = []
        # 'field' should be a list of fields
        for f in field:
            query_parts.append(f"field={f}")
        if name:
            query_parts.append(f"name={urllib.parse.quote(name)}")
        if namepart:
            query_parts.append(f"namepart={urllib.parse.quote(namepart)}")
        if version:
            query_parts.append(f"version={urllib.parse.quote(version)}")
        if release:
            query_parts.append(f"release={urllib.parse.quote(release)}")
        query = "?" + r"\&".join(query_parts) if query_parts else ""
        return subprocess.getoutput(f"{BASE}packages/list/{repo_id}{query}")

    @staticmethod
    def packages_upload(repo_id, packages):
        """upload a package or a directory with packages to the custom repo"""
        data = {}
        data["repo_id"] = repo_id
        data["packages"] = packages
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}packages/upload"
        return subprocess.getoutput(cmd)

    @staticmethod
    def packages_remove(repo_id, package, vr=""):
        """remove a package from a custom repo; a name must used, and optionally version-release"""
        data = {}
        data["repo_id"] = repo_id
        data["package"] = package
        if vr:
            data["vr"] = vr
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}packages/remove"
        return subprocess.getoutput(cmd)

    @staticmethod
    def cds_k8s(ssl_cert_secret_name):
        """generate K8s YAML"""
        data = {}
        data["ssl_cert_secret_name"] = ssl_cert_secret_name
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}cds/k8s"
        return subprocess.getoutput(cmd)

    @staticmethod
    def tasks_running():
        """list running tasks"""
        return subprocess.getoutput(f"{BASE}tasks/running")

    @staticmethod
    def tasks_waiting():
        """list waiting tasks"""
        return subprocess.getoutput(f"{BASE}tasks/waiting")

    @staticmethod
    def client_labels():
        """list repo labels"""
        return subprocess.getoutput(f"{BASE}client/labels")

    @staticmethod
    def client_cert(repo_labels, name, days, directory):
        """generate a client entitlement certificate"""
        data = {}
        data["repo_labels"] = repo_labels
        data["name"] = name
        data["days"] = days
        data["dir"] = directory
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}client/cert"
        return subprocess.getoutput(cmd)

    @staticmethod
    def client_rpm(directory,
                   rpm_name,
                   repo_labels="",
                   unprotected_repos="",
                   entitlement_certfile="",
                   entitlement_cert_keyfile="",
                   rpm_release="",
                   rpm_version="",
                   days=0,
                   proxy="",
                   ca_cert="",
                   omit_repo_sslcacert=False):
        """generate a client configuration RPM"""
        data = {}
        data["dir"] = directory
        data["rpm_name"] = rpm_name
        if repo_labels:
            data["repo_labels"] = repo_labels
        if unprotected_repos:
            data["unprotected_repos"] = unprotected_repos
        if entitlement_certfile:
            data["entitlement_certfile"] = entitlement_certfile
        if entitlement_cert_keyfile:
            data["entitlement_cert_keyfile"] = entitlement_cert_keyfile
        if rpm_release:
            data["rpm_release"] = rpm_release
        if rpm_version:
            data["rpm_version"] = rpm_version
        if days:
            data["days"] = days
        if proxy:
            data["proxy"] = proxy
        if ca_cert:
            data["ca_cert"] = ca_cert
        if omit_repo_sslcacert:
            data["omit_repo_sslcacert"] = True
        cmd = f"{BASE_COMMAND} -d '{json.dumps(data)}' {BASE_URL}client/rpm"
        return subprocess.getoutput(cmd)
