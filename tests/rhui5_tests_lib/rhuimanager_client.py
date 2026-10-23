""" RHUIManager Client functions """

import re
import time

from stitches.expect import Expect

from rhui5_tests_lib.rhuimanager import RHUIManager

PROMPT = r"rhui \(client\) => "

class ContainerSupportDisabledError(Exception):
    '''
    To be raised if container support is disabled in RHUI configuration.
    '''

class RHUIManagerClient():
    '''
    Represents -= Client Entitlement Management =- RHUI screen
    '''
    @staticmethod
    def generate_ent_cert(connection, repolist, certname, dirname, validity_days=""):
        '''
        generate an entitlement certificate
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "e")
        RHUIManager.select(connection, repolist)
        Expect.expect(connection, "Name of the certificate.*contained with it:")
        Expect.enter(connection, certname)
        Expect.expect(connection, "Local directory in which to save the generated certificate.*:")
        Expect.enter(connection, dirname)
        Expect.expect(connection, "Number of days the certificate should be valid.*:")
        Expect.enter(connection, str(validity_days))
        RHUIManager.proceed_without_check(connection)
        RHUIManager.quit(connection, timeout=60)

    @staticmethod
    def create_conf_rpm(connection, dirname, certpath, certkey, rpmname, rpmversion="",
                        rpmrelease="", unprotected_repos=None, proxy=""):
        '''
        create a client configuration RPM from an entitlement certificate
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "c")
        Expect.expect(connection, "Full path to local directory.*:")
        Expect.enter(connection, dirname)
        Expect.expect(connection, "Name of the RPM:")
        Expect.enter(connection, rpmname)
        Expect.expect(connection, "Version of the configuration RPM.*:")
        Expect.enter(connection, rpmversion)
        Expect.expect(connection, "Release of the configuration RPM.*:")
        Expect.enter(connection, rpmrelease)
        Expect.expect(connection, "Full path to the entitlement certificate.*:")
        Expect.enter(connection, certpath)
        Expect.expect(connection,
                      "Full path to the private key for the above entitlement certificate:")
        Expect.enter(connection, certkey)
        if unprotected_repos:
            RHUIManager.select(connection, unprotected_repos)
        if not rpmversion:
            rpmversion = "2.0"
        if not rpmrelease:
            rpmrelease = "1"
        Expect.expect(connection, "Optional proxy.*:")
        Expect.enter(connection, proxy)
        Expect.expect(connection,
                      f"Location: {dirname}/{rpmname}-{rpmversion}/build/RPMS/noarch/" +
                      f"{rpmname}-{rpmversion}-{rpmrelease}.noarch.rpm")
        Expect.enter(connection, "q")

    @staticmethod
    def create_container_conf_rpm(connection, dirname, rpmname, rpmversion="", rpmrelease="",
                                  days=""):
        '''
        create a container client configuration RPM
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "d")
        state = Expect.expect_list(connection,
                                   [(re.compile(".*Full path to local directory.*:",
                                                re.DOTALL),
                                     1),
                                    (re.compile(".*Container support is not currently enabled.*",
                                                re.DOTALL),
                                     2)])
        if state == 2:
            Expect.enter(connection, "q")
            raise ContainerSupportDisabledError()

        Expect.enter(connection, dirname)
        Expect.expect(connection, "Name of the RPM:")
        Expect.enter(connection, rpmname)
        Expect.expect(connection, "Version of the configuration RPM.*:")
        Expect.enter(connection, rpmversion)
        Expect.expect(connection, "Release of the configuration RPM.*:")
        Expect.enter(connection, rpmrelease)
        Expect.expect(connection, "Number of days.*:")
        Expect.enter(connection, days)
        if not rpmversion:
            rpmversion = "2.0"
        if not rpmrelease:
            rpmrelease = "1"
        Expect.expect(connection,
                      f"Location: {dirname}/{rpmname}-{rpmversion}/build/RPMS/noarch/" +
                      f"{rpmname}-{rpmversion}-{rpmrelease}.noarch.rpm")
        Expect.enter(connection, "q")

    @staticmethod
    def revoke(connection, cert=None, serial=None, comment=None):
        '''
        revoke an entitlement certificate by its path or serial number
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "r")
        Expect.expect(connection, "Enter the path.*:")
        if cert:
            Expect.enter(connection, cert)
        else:
            Expect.enter(connection, "")
            Expect.expect(connection, "Certificate serial number.*:")
            Expect.enter(connection, str(serial))
            Expect.expect(connection, "Warning.*:")
            Expect.enter(connection, "y")
        Expect.expect(connection, "Optional comment.*:")
        Expect.enter(connection, comment or "")
        RHUIManager.quit(connection, "Denylist updated")

    @staticmethod
    def unrevoke(connection, seriallist):
        '''
        unrevoke one or more entitlement certificates by their serial numbers
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "u")
        # the serial list may be a list of integers but we absolutely need a list of strings
        strseriallist = list(map(str, seriallist))
        RHUIManager.select(connection, strseriallist)
        RHUIManager.proceed_with_check(connection,
                                       "The following serials will be unrevoked:",
                                       strseriallist)
        RHUIManager.quit(connection)

    @staticmethod
    def revoked(connection):
        '''
        list revoked certificates; returns a nested list
        '''
        RHUIManager.screen(connection, "client")
        Expect.enter(connection, "l")
        output = Expect.match(connection, re.compile("(.*)" + PROMPT, re.DOTALL))[0]
        Expect.enter(connection, "q")
        time.sleep(5)
        lines = [line for line in output.splitlines() if re.match(r"\d", line)]
        return [line.split(maxsplit=2) for line in lines]
