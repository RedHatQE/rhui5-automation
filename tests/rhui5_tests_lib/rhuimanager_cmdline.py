""" RHUIManagerCLI functions """

import time

import nose

from stitches.expect import Expect

from rhui5_tests_lib.helpers import Helpers
from rhui5_tests_lib.util import Util

DEFAULT_ENT_CERT = "/root/test_files/rhcert.pem"

def _get_repo_statuses_json(connection):
    '''
    get the statuses of all Red Hat repositories (using the repo json data)
    '''
    # just a list of all the statuses, undefined order, no id<>status mappings
    cmd = "rhua rhui-manager status --repo_json /root/status && " \
          "jq -r '.[] | select(.group == \"redhat\").last_sync_result' /var/lib/rhui/root/status"
    _, stdout, _ = connection.exec_command(cmd)
    return stdout.read().decode().splitlines()

def _get_repo_status_json(connection, repo_id):
    '''
    get the status of the given repository ID using the repo json data
    '''
    cmd = "rhua rhui-manager status --repo_json /root/status && " \
          f"jq -r '.[] | select(.id == \"{repo_id}\").last_sync_result' /var/lib/rhui/root/status"
    _, stdout, _ = connection.exec_command(cmd)
    status = stdout.read().decode().strip()
    if status:
        return status
    raise RuntimeError("Reponse payload was empty.")

def _get_repo_status(connection, repo_name):
    '''
    get the status of the given repository name by parsing the complete RHUI status report
    '''
    _, stdout, _ = connection.exec_command("rhua rhui-manager status")
    lines = stdout.read().decode().splitlines()
    status = None
    for line in lines:
        if line.startswith(repo_name):
            status = Util.uncolorify(line).split()[-1]
            break
    if status:
        return status
    raise RuntimeError("Invalid repository name.")

def _wait_till_repo_synced(connection, repo_id, expect_success=True, use_json=True):
    '''
    wait until the specified repo ID is synchronized or the expected status occurs
    '''
    if use_json:
        repo_status = _get_repo_status_json(connection, repo_id)
        while repo_status in ["null", "running"]:
            time.sleep(10)
            repo_status = _get_repo_status_json(connection, repo_id)
        nose.tools.assert_equal(repo_status, "completed" if expect_success else "failed")
    else:
        repo_name = RHUIManagerCLI.repo_info(connection, repo_id)["name"]
        repo_status = _get_repo_status(connection, repo_name)
        while repo_status in ["Never", "SCHEDULED", "RUNNING"]:
            time.sleep(10)
            repo_status = _get_repo_status(connection, repo_name)
        nose.tools.assert_equal(repo_status, "SUCCESS" if expect_success else "ERROR")

def _wait_till_all_repos_synced(connection):
    '''
    wait until all Red Hat repos are synchronized
    '''
    statuses = _get_repo_statuses_json(connection)
    while not all(s == "completed" for s in statuses):
        if "failed" in statuses:
            raise RuntimeError("A repo failed to sync")
        time.sleep(10)
        statuses = _get_repo_statuses_json(connection)

def _ent_list(stdout):
    '''
    return a list of entitlements based on the given output (produced by cert upload/info)
    '''
    response = stdout.read().decode()
    lines = list(map(str.lstrip, str(response).splitlines()))
    # there should be a header in the output, with status
    try:
        status = Util.uncolorify(lines[2])
    except IndexError:
        raise RuntimeError(f"Unexpected output: {response}") from None
    if status == "Valid":
        # only pay attention to lines containing products
        # (which are non-empty lines below the header, without expriration and file name info)
        entitlements = [line for line in lines[3:] if line and not line.startswith("Expiration")]
        return entitlements
    if status in ("Expired", "No Red Hat entitlements found."):
        # return an empty list
        return []
    # if we're here, there's another problem with the entitlements/output
    raise RuntimeError(f"An error occurred: {response}")

class CustomRepoAlreadyExists(Exception):
    '''
    Raised if a custom repo with this ID already exists
    '''

class CustomRepoGpgKeyNotFound(Exception):
    '''
    Raised if the GPG key path to use with a custom repo is invalid
    '''

class NoValidEntitlementsProvided(Exception):
    '''
    Raised if the specified repositories do not exist in this RHUI
    '''

class RHUIManagerCLI():
    '''
    The RHUI manager command-line interface (shell commands to control the RHUA).
    '''
    @staticmethod
    def cert_upload(connection, cert=DEFAULT_ENT_CERT):
        '''
        upload a new or updated Red Hat content certificate and return a list of valid entitlements
        '''
        # get the complete output and split it into (left-stripped) lines
        _, stdout, _ = connection.exec_command(f"rhua rhui-manager cert upload --cert {cert}")
        if cert == DEFAULT_ENT_CERT:
            Helpers.copy_repo_mappings(connection)
        return _ent_list(stdout)

    @staticmethod
    def cert_info(connection):
        '''
        return a list of valid entitlements (if any)
        '''
        _, stdout, _ = connection.exec_command("rhua rhui-manager cert info")
        return _ent_list(stdout)

    @staticmethod
    def repo_unused(connection, by_repo_id=False):
        '''
        return a list of repos that are entitled but not added to RHUI
        '''
        # beware: if using by_repo_id, products will be followed by one or more repo IDs
        # on separate lines that start with two spaces
        cmd = "rhua rhui-manager repo unused"
        if by_repo_id:
            cmd += " --by_repo_id"
        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode().splitlines()
        # return everything but the first four lines, which contain headers
        return response[4:]

    @staticmethod
    def repo_add(connection, repo):
        '''
        add a repo specified by its product name
        '''
        Expect.expect_retval(connection,
                             f"rhua rhui-manager repo add --product_name \"{repo}\"")

    @staticmethod
    def repo_add_by_repo(connection, repo_ids, sync_now=False, unknown=False, already_added=False):
        '''
        add a list of repos specified by their IDs
        '''
        cmd = "rhua rhui-manager repo add_by_repo --repo_ids " + ",".join(repo_ids)
        if sync_now:
            cmd += " --sync_now"
        if unknown:
            if already_added:
                ecode = 243
            else:
                ecode = 246
        elif already_added:
            ecode = 245
        else:
            ecode = 0
        Expect.expect_retval(connection,
                             cmd,
                             ecode,
                             timeout=600)
        if sync_now:
            time.sleep(10)
            for repo_id in repo_ids:
                _wait_till_repo_synced(connection, repo_id)

    @staticmethod
    def repo_add_by_file(connection, repo_file, sync_now=False, trouble=None):
        '''
        add a list of repos specified in an input file
        '''
        cmd = "rhua rhui-manager repo add_by_file --file " + repo_file
        if sync_now:
            cmd += " --sync_now"
        troubles = {
                    "already_added": 245,
                    "bad_id": 255,
                    "bad_name": 240,
                    "no_name": 249,
                    "no_id": 249,
                    "wrong_id": 246,
                    "not_a_file": 240,
                    "invalid_yaml": 240
                   }
        ecode = troubles[trouble] if trouble in troubles else 0
        Expect.expect_retval(connection,
                             cmd,
                             ecode,
                             timeout=600)
        if sync_now:
            repo_ids = Helpers.get_repos_from_yaml(connection, repo_file)
            time.sleep(10)
            for repo_id in repo_ids:
                _wait_till_repo_synced(connection, repo_id)

    @staticmethod
    def repo_list(connection, ids_only=False, redhat_only=False, delimiter=""):
        '''
        show repos; can show IDs only, RH repos only, and accepts a delimiter
        '''
        cmd = "rhua rhui-manager repo list"
        if ids_only:
            cmd += " --ids_only"
        if redhat_only:
            cmd += " --redhat_only"
        if delimiter:
            cmd += " --delimiter " + delimiter
        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode().strip()
        return response

    @staticmethod
    def repo_sync(connection, repo_id, expect_success=True, is_valid=True, use_json=True):
        '''
        sync a repo
        '''
        cmd = f"rhua rhui-manager repo sync --repo_id {repo_id}; echo $?"
        _, stdout, _ = connection.exec_command(cmd)
        output = stdout.read().decode()
        ecode = int(output.splitlines()[-1])
        if is_valid:
            nose.tools.ok_("successfully scheduled" in output,
                           msg=f"unexpected output: {output}")
            nose.tools.eq_(ecode, 0)
            time.sleep(10)
            _wait_till_repo_synced(connection, repo_id, expect_success, use_json)
        else:
            nose.tools.ok_(f"Repo {repo_id} doesn't exist" in output,
                           msg=f"unexpected output: {output}")
            nose.tools.eq_(ecode, 241)
            # also check the RHUI log, which shouldn't contain a traceback for this scenario
            _, stdout, _ = connection.exec_command("rhua tail -1 /root/.rhui/rhui.log")
            output = stdout.read().decode()
            nose.tools.ok_("Successfully connected" in output and "RhuiException" not in output,
                           msg=f"unexpected log entry: {output}")

    @staticmethod
    def repo_sync_all(connection):
        '''
        sync all repos
        '''
        cmd = "rhua rhui-manager repo sync_all"
        Expect.expect_retval(connection, cmd)
        time.sleep(10)
        _wait_till_all_repos_synced(connection)

    @staticmethod
    def repo_info(connection, repo_id):
        '''
        return a dictionary containing information about the given repo
        '''
        _, stdout, _ = connection.exec_command(f"rhua rhui-manager repo info --repo_id {repo_id}")
        all_lines = stdout.read().decode().splitlines()
        if all_lines[0] == f"repository {repo_id} was not found":
            raise RuntimeError("Invalid repository ID.")
        return Util.lines_to_dict(all_lines)

    @staticmethod
    def repo_create_custom(connection,
                           repo_id,
                           path="",
                           display_name="",
                           redhat_content=False,
                           protected=False,
                           gpg_public_keys=""):
        '''
        create a custom repo
        '''
        # compose the command
        cmd = f"rhua rhui-manager repo create_custom --repo_id {repo_id}"
        if path:
            cmd += f" --path {path}"
        if display_name:
            cmd += f" --display_name '{display_name}'"
        if redhat_content:
            cmd += " --redhat_content"
        if protected:
            cmd += " --protected"
        if gpg_public_keys:
            cmd += f" --gpg_public_keys {gpg_public_keys}"
        # get a list of invalid GPG key files (will be implicitly empty if that option isn't used)
        key_list = gpg_public_keys.split(",")
        bad_keys = [key for key in key_list if connection.recv_exit_status(f"test -f {key}")]
        # possible output (more or less specific):
        out = {"missing_options": "Usage:",
               "invalid_id": "valid in a repository ID",
               "repo_exists": "already exists",
               "bad_gpg": "The following files are unreadable:\n\n" + "\n".join(bad_keys),
               "success": f"Successfully created repository \"{display_name or repo_id}\""}
        # run the command and see what happens
        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode()
        if out['missing_options'] in response or out['invalid_id'] in response:
            raise ValueError("the given repo ID is unusable")
        if out['repo_exists'] in response:
            raise CustomRepoAlreadyExists()
        if out['bad_gpg'] in response:
            raise CustomRepoGpgKeyNotFound()
        if out['success'] in response:
            return
        raise RuntimeError("Execution failed" + response)

    @staticmethod
    def repo_delete(connection, repo_id, is_valid=True):
        '''
        delete the given repo
        '''
        ecode = 0 if is_valid else 239
        Expect.expect_retval(connection,
                             f"rhua rhui-manager repo delete --repo_id {repo_id}",
                             ecode)

    @staticmethod
    def repo_add_errata(connection, repo_id, updateinfo):
        '''
        associate errata metadata with a repo
        '''
        Expect.expect_retval(connection,
                             "rhua rhui-manager repo add_errata " +
                             f"--repo_id {repo_id} --updateinfo '{updateinfo}'",
                             timeout=120)

    @staticmethod
    def repo_add_comps(connection, repo_id, comps):
        '''
        associate comps metadata with a repo
        '''
        Expect.expect_retval(connection,
                             "rhua rhui-manager repo add_comps " +
                             f"--repo_id {repo_id} --comps {comps}",
                             timeout=120)
        # better export the repo in case a previously added comps file for this repo is diferent
        RHUIManagerCLI.repo_export(connection, repo_id)

    @staticmethod
    def repo_export(connection, repo_id):
        '''
        export a repository to the filesystem
        '''
        Expect.expect_retval(connection, f"rhua rhui-manager repo export --repo_id {repo_id}")

    @staticmethod
    def repo_set_retain_versions(connection, versions, all_repos=False, repo_id=""):
        '''
        change the number of repo versions to keep, deleting any older versions
        '''
        opts = f"--versions {versions}"
        if all_repos:
            opts += " --all"
        elif repo_id:
            opts += f" --repo_id {repo_id}"
        Expect.expect_retval(connection, f"rhua rhui-manager repo set_retain_versions {opts}")

    @staticmethod
    def repo_orphan_cleanup(connection):
        '''
        schedule a task to clean up orphaned artifacts
        '''
        Expect.expect_retval(connection, "rhua rhui-manager repo orphan_cleanup")

    @staticmethod
    def packages_list(connection, repo_id):
        '''
        return a list of packages present in the repo
        '''
        cmd = f"rhua rhui-manager packages list --repo_id {repo_id}"
        _, stdout, _ = connection.exec_command(cmd)
        return stdout.read().decode().splitlines()

    @staticmethod
    def packages_remote(connection, repo_id, url):
        '''
        upload packages from a remote URL to a custom repository
        '''
        cmd = f"rhua rhui-manager packages remote --repo_id {repo_id} --url {url}"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def packages_remove(connection, repo_id, package_name, package_vr="", force=False):
        '''
        remove a package from a custom repo; an RPM name must used, and optionally version-release
        '''
        cmd = f"rhua rhui-manager packages remove --repo_id {repo_id} --package {package_name}"
        if package_vr:
            cmd += f" --vr {package_vr}"
        if force:
            cmd += " --force"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def packages_upload(connection, repo_id, path):
        '''
        upload a package or a directory with packages to the custom repo
        '''
        cmd = f"rhua rhui-manager packages upload --repo_id {repo_id} --packages '{path}'"
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def client_labels(connection):
        '''
        view repo labels in the RHUA; returns a list of the labels
        '''
        _, stdout, _ = connection.exec_command("rhua rhui-manager client labels")
        labels = stdout.read().decode().splitlines()
        return labels

    @staticmethod
    def client_cert(connection, repo_labels, name, days, directory):
        '''
        generate an entitlement certificate
        '''
        Expect.expect_retval(connection,
                             f"rhua rhui-manager client cert --repo_label {','.join(repo_labels)}" +
                             f" --name {name} --days {days} --dir {directory}",
                             timeout=60)

    @staticmethod
    def client_rpm(connection, certdata, rpmdata, directory, unprotected_repos=None, proxy=""):
        '''
        generate a client configuration RPM
        The certdata argument must be a list, and two kinds of data are supported:
          * key path and cert path (full paths, starting with "/"), or
          * one or more repo labels and optionally an integer denoting the number of days the cert
            will be valid for; if unspecified, rhui-manager will use 365. In this case,
            a certificate will be generated on the fly.
        The rpmdata argument must be a list with one, two or three strings:
          * package name: the name for the RPM
          * package version: string denoting the version; if unspecified, rhui-manager will use 2.0
          * package release: string denoting the release; if unspecified, rhui-manager will use 1
        '''
        cmd = "rhua rhui-manager client rpm"
        if certdata[0].startswith("/"):
            cmd += f" --private_key {certdata[0]} --entitlement_cert {certdata[1]}"
        else:
            cmd += " --cert"
            if isinstance(certdata[-1], int):
                cmd += f" --days {certdata.pop()}"
            cmd += " --repo_label " + ','.join(certdata)
        cmd += f" --rpm_name {rpmdata[0]}"
        if len(rpmdata) > 1:
            cmd += f" --rpm_version {rpmdata[1]}"
            if len(rpmdata) > 2:
                cmd += f" --rpm_release {rpmdata[2]}"
            else:
                rpmdata.append("1")
        else:
            rpmdata.append("2.0")
            rpmdata.append("1")
        cmd += f" --dir {directory}"
        if unprotected_repos:
            cmd += " --unprotected_repos " + ",".join(unprotected_repos)
        if proxy:
            cmd += " --proxy " + proxy
        Expect.expect_retval(connection, cmd, timeout=60)

    @staticmethod
    def client_content_source(connection, certdata, rpmdata, directory):
        '''
        generate an alternate source config rpm
        (very similar to client_rpm() -- see the usage described there)
        '''
        cmd = "rhua rhui-manager client content_source"
        if certdata[0].startswith("/"):
            cmd += f" --private_key {certdata[0]} --entitlement_cert {certdata[1]}"
        else:
            cmd += " --cert"
            if isinstance(certdata[-1], int):
                cmd += f" --days {certdata.pop()}"
            cmd += " --repo_label " + ",".join(certdata)
        cmd += " --rpm_name " + rpmdata[0]
        if len(rpmdata) > 1:
            cmd += " --rpm_version " + rpmdata[1]
        else:
            rpmdata.append("2.0")
        cmd += " --dir " + directory
        Expect.expect_retval(connection, cmd)

    @staticmethod
    def client_acs_config(connection, certdata, directory, ssl_ca_cert=""):
        '''
        generate an alternate source config configuration JSON
        (also similar to client_rpm() -- see the usage described there)
        '''
        cmd = "rhua rhui-manager client acs_config"
        if certdata[0].startswith("/"):
            cmd += f" --private_key {certdata[0]} --entitlement_cert {certdata[1]}"
        else:
            cmd += " --cert"
            if isinstance(certdata[-1], int):
                cmd += f" --days {certdata.pop()}"
            cmd += " --repo_label " + ",".join(certdata)
        cmd += " --dir " + directory
        if ssl_ca_cert:
            cmd += " --ssl_ca_cert " + ssl_ca_cert

        _, stdout, _ = connection.exec_command(cmd)
        response = stdout.read().decode()
        if f"Location: {directory}/acs-configuration.json" in response:
            return
        if "no valid entitlements provided" in response:
            raise NoValidEntitlementsProvided()
        raise RuntimeError("Execution failed" + response)

    @staticmethod
    def logout(connection):
        '''
        log out from rhui-manager
        '''
        Expect.enter(connection, "rhua rhui-manager --logout")
