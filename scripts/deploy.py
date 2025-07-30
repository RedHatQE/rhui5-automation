#!/usr/bin/python
"""RHUI 5 Automation Deployment Made Easy"""

from os import getlogin, system
from os.path import exists, expanduser, join
import sys

import argparse
from configparser import RawConfigParser

# there can be configuration to complement some options
CFG_FILE = "~/.rhui5-automation.cfg"
R5A_CFG = RawConfigParser()
R5A_CFG.read(expanduser(CFG_FILE))
if R5A_CFG.has_section("main") and R5A_CFG.has_option("main", "basedir"):
    RHUI_DIR = R5A_CFG.get("main", "basedir")
else:
    RHUI_DIR = "~/RHUI"
if R5A_CFG.has_section("main") and R5A_CFG.has_option("main", "unpriv_user"):
    UNPRIV_USER = R5A_CFG.get("main", "unpriv_user")
else:
    UNPRIV_USER = getlogin()

PRS = argparse.ArgumentParser(description="Run the RHUI 5 Automation playbook to deploy RHUI.",
                              formatter_class=argparse.ArgumentDefaultsHelpFormatter)
PRS.add_argument("inventory",
                 help="inventory file; typically hosts_*.cfg created by create-cf-stack.py",
                 nargs="?")
PRS.add_argument("--unpriv-user",
                 help="the unprivileged user name on the RHUA for podman invocations",
                 default=UNPRIV_USER,
                 metavar="user")
PRS.add_argument("--installer-image",
                 help="installer image in the registry",
                 default="rhui5/installer")
PRS.add_argument("--rhua-image",
                 help="RHUA image in the registry",
                 default="rhui5/rhua")
PRS.add_argument("--rhsm",
                 help="register the RHUA with RHSM",
                 action="store_true")
PRS.add_argument("--fips",
                 help="enable FIPS before running the deployment",
                 action="store_true")
PRS.add_argument("--proxy",
                 help="configure RHUI to connect to the CDN via a proxy",
                 action="store_true")
PRS.add_argument("--extra-files",
                 help="ZIP file with extra files",
                 default=join(RHUI_DIR, "extra_files.zip"),
                 metavar="file")
PRS.add_argument("--credentials",
                 help="configuration file with credentials",
                 default=join(RHUI_DIR, "credentials.conf"),
                 metavar="file")
PRS.add_argument("--tests",
                 help="RHUI test to run",
                 metavar="test name or category")
PRS.add_argument("--patch",
                 help="patch to apply to rhui5-automation",
                 metavar="file")
PRS.add_argument("--branch",
                 help="clone and install a particular rhui5-automation branch")
PRS.add_argument("--rhel8b",
                 help="RHEL 8 Beta baseurl or compose",
                 metavar="URL/compose")
PRS.add_argument("--rhel9b",
                 help="RHEL 9 Beta baseurl or compose",
                 metavar="URL/compose")
PRS.add_argument("--rhel10b",
                 help="RHEL 10 Beta baseurl or compose",
                 metavar="URL/compose")
PRS.add_argument("--tags",
                 help="run only tasks tagged this way",
                 metavar="tags")
PRS.add_argument("--skip-tags",
                 help="skip tasks tagged this way",
                 metavar="tags")
PRS.add_argument("--extra-vars",
                 help="supply these variables to Ansible")
PRS.add_argument("--clone",
                 help="clone the original (previously deployed) RHUI 5 RHUA to another host",
                 action="store_true")
PRS.add_argument("--mig",
                 help="migrate from RHUI 4 to 5",
                 action="store_true")
PRS.add_argument("--toanotherrhua",
                 help="make the migration from RHUI 4 to 5 non-in-place (to another RHUA)",
                 action="store_true")
PRS.add_argument("--dry-run",
                 help="only construct and print the ansible-playbook command, do not run it",
                 action="store_true")

ARGS = PRS.parse_args()

if not ARGS.inventory:
    PRS.print_help()
    sys.exit(1)

if not exists(ARGS.inventory):
    print(ARGS.inventory + " does not exist.")
    sys.exit(1)

# start building the command
CMD = f"ansible-playbook -i {ARGS.inventory} deploy/site.yml --extra-vars '"

# start building the extra variables
EVARS = "unpriv_user=" + ARGS.unpriv_user if ARGS.unpriv_user else UNPRIV_USER

EVARS += " installer_image=" + ARGS.installer_image
EVARS += " rhua_image=" + ARGS.rhua_image

if ARGS.rhsm:
    EVARS += " rhsm=True"

if ARGS.fips:
    EVARS += " fips=True"

if ARGS.proxy:
    EVARS += " proxy=True"

if exists(expanduser(ARGS.extra_files)):
    EVARS += " extra_files=" + ARGS.extra_files
else:
    print(ARGS.extra_files + " does not exist, ignoring")

if exists(expanduser(ARGS.credentials)):
    EVARS += " credentials=" + ARGS.credentials
else:
    print(ARGS.credentials + " does not exist, ignoring")

# provided that the RHEL X Beta string is NOT a URL,
# see if the configuration contains templates for RHEL Beta baseurls;
# if so, expand them
# if not, use the arguments verbatim
if ARGS.rhel8b:
    if ":/" not in ARGS.rhel8b and R5A_CFG.has_option("beta", "rhel8_template"):
        try:
            ARGS.rhel8b = R5A_CFG.get("beta", "rhel8_template") % ARGS.rhel8b
        except TypeError:
            print(f"The RHEL 8 Beta URL template is written incorrectly in {CFG_FILE}. " +
                  "It must contain '%s' in one place.")
            sys.exit(1)
    EVARS += " rhel8_beta_baseurl=" + ARGS.rhel8b

if ARGS.rhel9b:
    if ":/" not in ARGS.rhel9b and R5A_CFG.has_option("beta", "rhel9_template"):
        try:
            ARGS.rhel9b = R5A_CFG.get("beta", "rhel9_template") % ARGS.rhel9b
        except TypeError:
            print(f"The RHEL 9 Beta URL template is written incorrectly in {CFG_FILE}. " +
                  "It must contain '%s' in one place.")
            sys.exit(1)
    EVARS += " rhel9_beta_baseurl=" + ARGS.rhel9b

if ARGS.rhel10b:
    if ":/" not in ARGS.rhel10b and R5A_CFG.has_option("beta", "rhel10_template"):
        try:
            ARGS.rhel10b = R5A_CFG.get("beta", "rhel10_template") % ARGS.rhel10b
        except TypeError:
            print(f"The RHEL 10 Beta URL template is written incorrectly in {CFG_FILE}. " +
                  "It must contain '%s' in one place.")
            sys.exit(1)
    EVARS += " rhel10_beta_baseurl=" + ARGS.rhel10b

if ARGS.tests:
    EVARS += " tests=" + ARGS.tests

if ARGS.patch:
    if exists(expanduser(ARGS.patch)):
        EVARS += " patch=" + ARGS.patch
    else:
        print(f"--patch was specified but {ARGS.patch} does not exist, exiting.")
        sys.exit(1)

if ARGS.branch:
    EVARS += " branch=" + ARGS.branch

if ARGS.clone:
    # set related options accordingly; note that migrating and cloning are mutually exclusive tasks
    ARGS.mig = False
    ARGS.toanotherrhua = True
    EVARS += " clone=True"

if ARGS.mig:
    EVARS += " mig=True"

if ARGS.toanotherrhua:
    EVARS += " toanotherrhua=True"

if ARGS.extra_vars:
    EVARS += " " + ARGS.extra_vars

# join the command and the extra variables
CMD += EVARS + "'"

# use/skip specific tags if requested
if ARGS.tags:
    CMD += " --tags " + ARGS.tags

if ARGS.skip_tags:
    CMD += " --skip-tags " + ARGS.skip_tags

# the command is now built; print it and then run it (unless in the dry-run mode)
if ARGS.dry_run:
    print("DRY RUN: would have run: " + CMD)
else:
    print("Running: " + CMD)
    system(CMD)
