Requirements
---------------
* Ansible
* Have enough machines ready - check the rest of Read Me for details on various RHUI setups.
* Red Hat credentials and also credentials for the registry hosting RHUI contaner images.

Usage
--------

* Run the [stack creation script](../scripts/README.md) to launch VMs and get an inventory file with information about the VMs.
* Run the [deployment script](../scripts/deploy.py) to deploy RHUI on the VMs.

Note that if you use `--rhelXb`, all RHEL X systems will get rebooted after the update
to the given compose. This will allow a new kernel to boot, apps to load with a new glibc, etc.

Create credentials.conf in the parent directory of this clone as follows:

```
[rh]
username=YOUR_RH_USERNAME
password=YOUR_RH_PASSWORD

[registry]
hostname=THE_RHUI_REGISTRY
username=YOUR_REGISTRY_USERNAME
password=YOUR_REGISTRY_PASSWORD
insecure=1
````

The deployment script can also read your test environment data and templates for RHEL 8, 9, or 10 Beta URLs
from `~/.rhui5-automation.cfg`; the expected format is as follows:

```
[main]
basedir=~/your directory with RHUI files (e.g. the extra files ZIP)
unpriv_user=the unprivileged user that logs in to the nodes
[beta]
rhel8_template=http://host/path/%s/path/
rhel9_template=http://host/path/%s/path/
rhel10_template=http://host/path/%s/path/
```

Read the usage message from the deployment script to become familiar with it:

```
./scripts/deploy.py --help
```

Migration from RHUI 4 to 5
--------------------------
The `deploy.py` script can also be used to migrate RHUI 4 to 5: either in-place, or to another RHUA.
You need a previously installed RHUI 4 stack and its inventory file, plus a new VM serving as the
launchpad for RHUI 5, and in the case of a migration to another RHUA also such an extra VM.
Note that rhui4-automation now has the ability to create the stack with a VM reserved as a future
launchpad and another RHUA (see its `scripts/README.md` file), so you can install RHUI 4 with such
prepared extra VMs, or you can launch a VM (or two) like one of the RHUI 4 nodes and add one
hostname to the existing RHUI 4 inventory file under `[LAUNCHPAD]` (and another one under
`[ANOTHERRHUA]`).

If installing a new RHUI 4 stack, be sure to use the new PostgreSQL version, which is requirement
for a successful migration; to do so, use the `--new-psql` argument of the RHUI 4 `deploy.py`
script. If RHUI 4 is already installed with the default PostgreSQL version, you will have to rerun
the RHUI 4 installer with `--postgresql-version 15` first.

To start an in-place migration, run the RHUI 5 dwployment script with the enriched RHUI 4 inventory
file with the launchpad hostname and with the `--mig` argument.
To start a migration to another RHUA, use the further enriched RHUI 4 inventory file with both the
launchpad and the other RHUA hostnames, and with the `--mig --toanotherrhua` arguments.

> [!IMPORTANT]
> Because RHUI 4 runs on RHEL 8, you need to run the RHUI 5 `deploy.py` script from a system with
> Ansible not later than 2.16, ie. e.g. from Fedora 41. Newer Ansible versions cannot control
> RHEL 8 systems.

> [!NOTE]
> In-place migrations can not be repeated.
> Therefore, the deployment script can only be run like this once.

> [!IMPORTANT]
> Although a stack with a test node can be migrated to RHUI 5 including a new setup of the test
> node for RHUI 5 testing, non-in-place migrations still use the "rhua.example.com" hostname for
> the abandoned RHUI 4 RHUA. Conseqently, tests will communicate with the abandoned RHUA by
> default. To make them communicate with the new RHUA instead, edit `/etc/hosts` on the test node
> to use the IP address of `anotherrhua.example.com` for `rhua.example.com`. In-place migrations
> are not affected.

Managed roles
-------------
- RHUA
- CDSes
- HAProxy (load balancer)
- NFS server
- Clients (optional)
- [Tests](../tests/README.md) (optional)

Supported configurations
------------------------
The rule of thumb is multiple roles can be applied to a single node.
This allows various deployment configurations, just to outline the minimal one:
- Rhua+Nfs, n\*Cds, m\*HAProxy

Please, bare in mind that role application sets node `hostname` such as hap01.example.com, nfs.example.com overriding any hostname previously set (by other role application).
Although all the role hostnames are properly resolvable (through /etc/hosts and optionaly the name server), the last applied hostname will stick to the node.

Configuration Samples
---------------------
Edit your copy of the `hosts.cfg` to meet your preferences:
* example:
```ini
# Rhua+Nfs, 2*Cds, 2*HAProxy
[NFS]
ec2-10.0.0.2.eu-west-1.compute.amazonaws.com

[RHUA]
ec2-10.0.0.2.eu-west-1.compute.amazonaws.com

[CDS]
ec2-10.0.0.3.eu-west-1.compute.amazonaws.com
ec2-10.0.0.4.eu-west-1.compute.amazonaws.com

[HAPROXY]
ec2-10.0.0.5.eu-west-1.compute.amazonaws.com

[CLI]
ec2-10.0.0.6.eu-west-1.compute.amazonaws.com

#[TEST]
#ec2-10.0.0.8.eu-west-1.compute.amazonaws.com
```

Check the [hosts.cfg](../hosts.cfg) file for more combinations.


Configuration Limitations
-------------------------
Even though one can apply multiple roles to a single node, some combinations are restricted or make no sense:
- singleton roles --- only one instance per site: Rhua, Nfs, Proxy, Test
- mutually exclusive roles --- can't be applied to the same node: Rhua, Cds, HAProxy, Proxy (all listen on port 443)
- optional roles --- may be absent in one's site: HAProxy, Proxy, Cli, Test
- multi-roles --- usually multiple instances per site: CDS, HAProxy, Cli

Network Ports:
---------------------------------------

* RHUA to cdn.redhat.com 443/TCP
* RHUA to CDSes 22/TCP for initial SSH configuration
* RHUA to HAProxy 22/TCP for initial SSH configuration
* clients to HAProxy 443/TCP
* HAProxy to CDSes 443/TCP
* NFS port 2049/TCP on the NFS server
