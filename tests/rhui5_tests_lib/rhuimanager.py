""" General rhui-manager methods """

import logging
import re
import time

import nose
from stitches.expect import Expect, ExpectFailed

from rhui5_tests_lib.util import Util

SELECT_PATTERN = re.compile(r'^  (x|-)  (\d+) :')
PROCEED_PATTERN = re.compile(r'.*Proceed\? \(y/n\).*', re.DOTALL)
CONFIRM_PATTERN_STRING = r"Enter value \([\d]+-[\d]+\) to toggle selection, " + \
                         r"'c' to confirm selections, or '\?' for more commands: "

class NotSelectLine(ValueError):
    """
    to be raised when the line isn't actually a selection line
    """

class RHUIManager():
    '''
    Basic functions to manage rhui-manager.
    '''

    @staticmethod
    def selected_line(line):
        """
        return True/False, item list index
        """
        match = SELECT_PATTERN.match(line)
        if match is None:
            raise NotSelectLine(line)
        return match.groups()[0] == 'x', int(match.groups()[1])

    @staticmethod
    def list_lines(connection, prompt='', enter_l=True, timeout=10):
        '''
        list items on screen returning a list of lines seen
        eats prompt!!!
        '''
        if enter_l:
            Expect.enter(connection, "l")
        match = Expect.match(connection, re.compile("(.*)" + prompt, re.DOTALL), timeout=timeout)
        return match[0].splitlines()

    @staticmethod
    def select(connection, value_list):
        '''
        Select list of items (multiple choice)
        '''
        for value in value_list:
            match = Expect.match(connection, re.compile(r".*-\s+([0-9]+)\s*:[^\n]*\s*" +
                                                        re.escape(value) +
                                                        r"\s*\n.*for more commands:.*", re.DOTALL))
            Expect.enter(connection, match[0])
            match = Expect.match(connection, re.compile(r".*x\s+([0-9]+)\s*:[^\n]*\s*" +
                                                        re.escape(value) +
                                                        r"\s*\n.*for more commands:.*", re.DOTALL))
            Expect.enter(connection, "l")
        Expect.enter(connection, "c")

    @staticmethod
    def select_items(connection, itemslist):
        '''
        Select list of items (multiple choice)
        '''
        lines = RHUIManager.list_lines(connection, prompt=CONFIRM_PATTERN_STRING, enter_l=False)
        for item in itemslist:
            for line in lines:
                if item in line:
                    index = list(filter(str.isdigit, str(lines[lines.index(line)-1])))[0]
                    Expect.enter(connection, index)
                    break
        Expect.enter(connection, "c")

    @staticmethod
    def select_one(connection, item):
        '''
        Select one item (single choice)
        '''
        match = Expect.match(connection, re.compile(r".*([0-9]+)\s+-\s+" +
                                                    item +
                                                    r"\s*\n.*to abort:.*",
                                                    re.DOTALL))
        Expect.enter(connection, match[0])

    @staticmethod
    def select_all(connection):
        '''
        Select all items
        '''
        Expect.expect(connection, "Enter value .*:")
        Expect.enter(connection, "a")
        Expect.expect(connection, "Enter value .*:")
        Expect.enter(connection, "c")

    @staticmethod
    def quit(connection, prefix="", timeout=10):
        '''
        Quit from rhui-manager

        Use @param prefix to specify something to expect before exiting
        Use @param timeout to specify the timeout
        '''
        Expect.expect(connection, prefix + r".*rhui \(.*\) =>", timeout)
        Expect.enter(connection, "q")
        time.sleep(5)

    @staticmethod
    def logout(connection):
        '''
        Log out from rhui-manager
        To be run when logged in, and when in the shell (not in rhui-manager).
        '''
        Expect.enter(connection, "rhua rhui-manager")
        Expect.enter(connection, "logout")

    @staticmethod
    def proceed_without_check(connection):
        '''
        Proceed without check (avoid this function when possible!)
        '''
        Expect.expect(connection, r"Proceed\? \(y/n\)")
        Expect.enter(connection, "y")

    @staticmethod
    def proceed_with_check(connection, caption, value_list, skip_list=""):
        '''
        Proceed with prior checking the list of values

        Use @param skip_list to skip meaningless 2nd-level headers
        '''
        selected = Expect.match(connection,
                                re.compile(".*" +
                                           caption +
                                           r"\r\n(.*)\r\nProceed\? \(y/n\).*",
                                           re.DOTALL))[0].splitlines()
        selected_clean = []
        for val in selected:
            val = val.strip()
            val = val.replace("\t", " ")
            val = ' '.join(val.split())
            if val != "" and val not in skip_list:
                selected_clean.append(val)
        if sorted(selected_clean) != sorted(value_list):
            logging.debug("Selected: %s", selected_clean)
            logging.debug("Expected: %s", value_list)
            raise ExpectFailed()
        Expect.enter(connection, "y")

    @staticmethod
    def screen(connection, screen_name):
        '''
        Open specified rhui-manager screen
        '''
        if screen_name in ["repo", "cds", "loadbalancers", "sync", "users"]:
            key = screen_name[:1]
        elif screen_name == "client":
            key = "e"
        elif screen_name == "entitlements":
            key = "n"
        else:
            raise ValueError("Unsupported screen name: " + screen_name)
        if screen_name == "loadbalancers":
            screen_name = "haproxy"
        Expect.enter(connection, "rhua rhui-manager")
        Expect.expect(connection, r"rhui \(home\) =>")
        Expect.enter(connection, key)
        Expect.expect(connection, r"rhui \(" + screen_name + r"\) =>")

    @staticmethod
    def initial_run(connection, username="admin", password=""):
        '''
        Run rhui-manager and make sure we're logged in, then quit it.
        '''
        Expect.enter(connection, "rhua rhui-manager")
        state = Expect.expect_list(connection,
                                   [(re.compile(".*RHUI Username:.*", re.DOTALL), 1),
                                    (re.compile(r".*rhui \(home\) =>.*", re.DOTALL), 2)])
        if state == 2:
        # Already logged in? No need to enter any password, just quit.
            Expect.enter(connection, "q")
            time.sleep(5)
            return
        # Use the supplied password, OR try to get it from the usual place.
        if not password:
            password = Util.get_saved_password(connection)
        Expect.enter(connection, username)
        Expect.expect(connection, "RHUI Password:")
        Expect.enter(connection, password)
        password_state = Expect.expect_list(connection,
                                            [(re.compile(".*Invalid login.*",
                                                         re.DOTALL),
                                              1),
                                             (re.compile(r".*rhui \(home\) =>.*",
                                                         re.DOTALL),
                                              2)])
        if password_state == 2:
            Expect.enter(connection, "q")
            time.sleep(5)
        else:
            obf_password = f"{password[0]}***{password[1]}"
            raise RuntimeError(f"Can't log in to rhui-manager with password {obf_password}.")

    @staticmethod
    def change_user_password(connection, password=""):
        '''
        Change the password of rhui-manager user
        '''
        if not password:
            password = Util.get_saved_password(connection)
        if not password:
            raise RuntimeError("No password specified and the saved one couldn't be read.")
        RHUIManager.screen(connection, "users")
        Expect.enter(connection, "p")
        Expect.expect(connection, "New Password:")
        Expect.enter(connection, password)
        Expect.expect(connection, "Re-enter Password:")
        Expect.enter(connection, password)
        Expect.expect(connection, "Password successfully updated")
        # this action is supposed to log the admin out and thus delete the Pulp cookies
        cookiejar = "/var/lib/rhui/root/.rhui/http-localhost:24817/cookies.txt"
        Expect.expect_retval(connection, "test -f " + cookiejar, 1)

    @staticmethod
    def remove_rh_certs(connection):
        '''
        Remove all RH certificates and cached repo mappings from RHUI
        '''
        Expect.expect_retval(connection, "find /var/lib/rhui/pki/redhat/ -name '*.pem' -delete")
        Expect.expect_retval(connection, "find /var/lib/rhui/cache/ -name '*.mappings' -delete")

    @staticmethod
    def cacert_expiration(connection):
        '''
        check if the CA certificate expiration date is OK
        '''
        _, stdout, _ = connection.exec_command("rhua rhui-manager status")
        lines = stdout.read().decode().splitlines()
        status = "undetected"
        for line in lines:
            if line.startswith("Entitlement CA certificate expiration date"):
                status = Util.uncolorify(line).split()[-1]
                break
        nose.tools.eq_(status, "OK")
