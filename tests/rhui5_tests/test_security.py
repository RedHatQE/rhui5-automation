"""Various Security Tests"""

import csv
import logging
from os.path import basename
import subprocess
import time

import nose
import requests
from stitches.expect import Expect
import urllib3

from rhui5_tests_lib.cfg import RHUI_ROOT
from rhui5_tests_lib.conmgr import ConMgr
from rhui5_tests_lib.rhuimanager import RHUIManager
from rhui5_tests_lib.rhuimanager_cmdline_instance import RHUIManagerCLIInstance

logging.basicConfig(level=logging.DEBUG)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOSTNAMES = {"RHUA": ConMgr.get_rhua_hostname(),
             "CDS": ConMgr.get_cds_hostnames()[0],
             "HAProxy": ConMgr.get_lb_hostname()}
PORTS = { "https": 443 }
PROTOCOL_TEST_CMD = "echo | openssl s_client -%s -connect %s:%s"
# these are in fact the s_client options for protocols, just without the dash
PROTOCOLS = {"good": ["tls1_2", "tls1_3"],
             "bad": ["tls1", "tls1_1"]}

# connections to the RHUA and the HAProxy nodes
RHUA = ConMgr.connect()
CDS = ConMgr.connect(HOSTNAMES["CDS"])
HAPROXY = ConMgr.connect(HOSTNAMES["HAProxy"])

SSL_CERT = f"{RHUI_ROOT}/cds-config/ssl/{HOSTNAMES['HAProxy']}.crt"

def _check_protocols(hostname, port):
    """helper method to try various protocols on hostname:port"""
    # check allowed protocols
    for protocol in PROTOCOLS["good"]:
        exitcode = subprocess.call(PROTOCOL_TEST_CMD % (protocol, hostname, port) + " &> /dev/null",
                                   shell=True)
        nose.tools.eq_(exitcode, 0)
    # check disallowed protocols
    for protocol in PROTOCOLS["bad"]:
        exitcode = subprocess.call(PROTOCOL_TEST_CMD % (protocol, hostname, port) + " &> /dev/null",
                                   shell=True)
        nose.tools.eq_(exitcode, 1)

def _get_cn(connection):
    """get the Common Name from the CDS SSL certificate"""
    cmd = f"openssl x509 -noout -subject -in {SSL_CERT}"
    _, stdout, _ = connection.exec_command(cmd)
    subject_data = [item.strip() for item in stdout.read().decode().split(",")]
    cn_raw = [item for item in subject_data if item.startswith("CN")][0]
    cn_data = cn_raw.split("=")
    try:
        return cn_data[1].strip()
    except IndexError:
        return None

def _get_san(connection):
    """get the Subject Alternative Name from the CDS SSL certificate"""
    cmd = f"openssl x509 -noout -ext subjectAltName -in {SSL_CERT}"
    _, stdout, _ = connection.exec_command(cmd)
    san_data = [item.strip() for item in stdout.read().decode().splitlines()[1:]]
    san_raw = [item for item in san_data if item.startswith("DNS")][0]
    san = san_raw.replace("DNS:", "")
    return san

def setup():
    """announce the beginning of the test run"""
    print(f"*** Running {basename(__file__)}: ***")

def test_01_login_add_cds_hap():
    """log in to RHUI, add CDS and HAProxy nodes"""
    RHUIManager.initial_run(RHUA)
    RHUIManagerCLIInstance.add(RHUA, "cds", unsafe=True)
    RHUIManagerCLIInstance.add(RHUA, "haproxy", unsafe=True)

def test_02_https_rhua():
    """check protocols allowed by nginx on the RHUA"""
    # for RHBZ#1637261
    _check_protocols(HOSTNAMES["RHUA"], PORTS["https"])

def test_03_https_cds():
    """check protocols allowed by nginx on the CDS nodes"""
    # for RHBZ#1637261
    _check_protocols(HOSTNAMES["CDS"], PORTS["https"])

def test_04_haproxy_stats():
    """check haproxy stats"""
    # for RHBZ#1718066
    # make sure nc is installed first
    Expect.expect_retval(HAPROXY, "ha yum -y install nc")
    # yet wait a little longer before actually checking the stats
    time.sleep(7)
    cmd = "cd /tmp ; echo 'show stat' | " \
          "sudo -u rhui podman exec -it " \
          "rhui5-haproxy timeout 3 nc -U /var/lib/haproxy/stats | " \
          "tail -n +2"
    _, stdout, _ = HAPROXY.exec_command(cmd)
    stats = list(csv.DictReader(stdout))
    httpsstats = {row["svname"]: row["status"] for row in stats if row["# pxname"] == "https00"}
    # check the stats for the frontend, the CDS nodes, and the backend; https
    nose.tools.eq_(httpsstats["FRONTEND"], "OPEN")
    nose.tools.eq_(httpsstats["BACKEND"], "UP")
    nose.tools.eq_(httpsstats[HOSTNAMES["CDS"]], "UP")

def test_05_hsts():
    """check if HTTP Strict Transport Security is used"""
    response = requests.head(f"https://{HOSTNAMES['HAProxy']}/", timeout=10, verify=False)
    nose.tools.ok_("Strict-Transport-Security" in response.headers,
                   msg=f"Got these headers: {response.headers}")

def test_06_cds_ssl():
    """check the CN and SAN in the CDS SSL certificate"""
    cn = _get_cn(CDS)
    nose.tools.eq_(cn, HOSTNAMES["HAProxy"])

    san = _get_san(CDS)
    nose.tools.eq_(san, HOSTNAMES["HAProxy"])

def test_07_v2_access():
    """check if access to /v2 (container catalog) on the RHUA is denied by default"""
    response = requests.head(f"https://{HOSTNAMES['RHUA']}/v2/", timeout=10, verify=False)
    nose.tools.eq_(response.status_code, 400)

def test_08_rhua_443_access():
    """check if access to private directories on the Pulp web server is denied"""
    paths = ["/pulp/api/v3/", "/auth/login/"]
    for path in paths:
        response = requests.head(f"https://{HOSTNAMES['RHUA']}{path}", timeout=10, verify=False)
        nose.tools.eq_(response.status_code, 403)

def test_99_cleanup():
    """delete CDS and HAProxy nodes"""
    RHUIManagerCLIInstance.delete(RHUA, "haproxy", force=True)
    RHUIManagerCLIInstance.delete(RHUA, "cds", force=True)
    ConMgr.remove_ssh_keys(RHUA)

def teardown():
    """announce the end of the test run"""
    print(f"*** Finished running {basename(__file__)}. ***")
