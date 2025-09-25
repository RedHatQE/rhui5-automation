#!/usr/bin/python3
""" Create CloudFormation stack """
# pylint: disable=C0301,C0103,W0718

import os
import socket
import argparse
import time
import logging
import sys
import random
import string
import json
import re

import boto3
import yaml

instance_types = {"arm64": "t4g.large", "x86_64": "m5.large"}

argparser = argparse.ArgumentParser(description='Create CloudFormation stack for RHUI 5',
                                    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
argparser.add_argument('--name', help='common name for stack members', default='rhui5')
argparser.add_argument('--cli7', help='number of RHEL7 clients', type=int, default=0)
argparser.add_argument('--cli7-arch', help='RHEL 7 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli8', help='number of RHEL8 clients', type=int, default=0)
argparser.add_argument('--cli8-arch', help='RHEL 8 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli9', help='number of RHEL9 clients', type=int, default=0)
argparser.add_argument('--cli9-arch', help='RHEL 9 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli10', help='number of RHEL10 clients', type=int, default=0)
argparser.add_argument('--cli10-arch', help='RHEL 10 clients\' architectures (comma-separated list)', default='x86_64', metavar='ARCH')
argparser.add_argument('--cli-all', help='launch one client per RHEL version and available architecture, RHEL 7+ by default; numbers can still be overridden)', action='store_const', const=True, default=False)
argparser.add_argument('--cli-only', help='launch only client machines', action='store_const', const=True, default=False)
argparser.add_argument('--rhua-os', help='RHEL version for the RHUA', type=int, default=9)
argparser.add_argument('--cds', help='number of CDSes instances', type=int, default=1)
argparser.add_argument('--cds-os', help='RHEL version for the CDSes', type=int, default=9)
argparser.add_argument('--haproxy', help='number of HAProxies', type=int, default=1)
argparser.add_argument('--haproxy-os', help='RHEL version for the HAProxies', type=int, default=9)
argparser.add_argument('--boxed', help='RHUI-in-a-box', action='store_const', const=True, default=False)
argparser.add_argument('--launchpad-os', help='RHEL version for the launchpad. Practically only 8+.', type=int, default=9)
argparser.add_argument('--launchpad-ami', help='AMI ID for the launchpad, to test an arbitrary OS. Must be in the given region, and x86_64.')
argparser.add_argument('--launchpad-user', help='user (login) name for the launchpad as some OS AMIs might use a name different than RHEL AMIs do.')
argparser.add_argument('--nfs', help='NFS', action='store_const', const=True, default=False)
argparser.add_argument('--test', help='test machine', action='store_const', const=True, default=False)
argparser.add_argument('--clone', help='add another RHUA for a future clone or save&restore test', action='store_const', const=True, default=False)
argparser.add_argument('--input-conf', default="/etc/rhui_ec2.yaml", help='use supplied yaml config file')
argparser.add_argument('--output-conf', help='output file')
argparser.add_argument('--region', default="eu-west-1", help='use specified region')
argparser.add_argument('--debug', action='store_const', const=True,
                       default=False, help='debug mode')
argparser.add_argument('--dry-run', action='store_const', const=True,
                       default=False, help='only validate the data and print what would be used')
argparser.add_argument('--timeout', type=int,
                       default=10, help='stack creation timeout (in minutes)')

argparser.add_argument('--vpcid', help='VPCid (overrides the configuration for the region)')
argparser.add_argument('--subnetid', help='Subnet id (for VPC) (overrides the configuration for the region)')
argparser.add_argument('--novpc', help='do not use VPC, use EC2 Classic', action='store_const', const=True, default=False)

argparser.add_argument('--ami-7-override', help='RHEL 7 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-override', help='RHEL 8 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-override', help='RHEL 9 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-10-override', help='RHEL 10 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-8-arm64-override', help='RHEL 8 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-9-arm64-override', help='RHEL 9 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ami-10-arm64-override', help='RHEL 10 ARM64 AMI ID to override the mapping', metavar='ID')
argparser.add_argument('--ansible-ssh-extra-args', help='Extra arguments for SSH connections established by Ansible', metavar='ARGS')
argparser.add_argument('--key-pair-name', help='the name of the key pair in the given AWS region, if your local user name differs and SSH configuraion is undefined in the yaml config file')

args = argparser.parse_args()


fs_type = "rhua"

if args.debug:
    loglevel = logging.DEBUG
else:
    loglevel = logging.INFO

REGION = args.region

logging.basicConfig(level=loglevel, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

if args.cli_all:
    args.cli7 = args.cli7 or -1
    args.cli8 = args.cli8 or -1
    args.cli9 = args.cli9 or -1
    args.cli10 = args.cli10 or -1

if args.cli_only:
    args.launchpad_os = args.cds = args.haproxy = 0
    fs_type = ""

if args.boxed:
    args.cds = args.haproxy = 0

if (args.vpcid and not args.subnetid) or (args.subnetid and not args.vpcid):
    logging.error("vpcid and subnetid parameters should be set together!")
    sys.exit(1)
if args.novpc:
    instance_types["x86_64"] = "m3.large"

try:
    with open(args.input_conf, encoding="utf-8") as confd:
        valid_config = yaml.safe_load(confd)

    if "ssh" in valid_config.keys() and REGION in valid_config["ssh"].keys():
        (ssh_key_name, ssh_key) = valid_config["ssh"][REGION]
    else:
        ssh_key = ""
        ssh_key_name = args.key_pair_name or os.getlogin()
    ec2_name = re.search("[a-zA-Z]+", ssh_key_name).group(0)
    if args.key_pair_name:
        ssh_key = "~/.ssh/id_rsa_" + ec2_name
    if not args.novpc:
        (vpcid, subnetid) = (args.vpcid, args.subnetid) if args.vpcid else valid_config["vpc"][REGION]
except FileNotFoundError:
    sys.stderr.write("Missing configuration file")
    sys.exit(1)
except yaml.parser.ParserError:
    sys.stderr.write("Bad YAML")
    sys.exit(1)

json_dict = {}

json_dict['AWSTemplateFormatVersion'] = '2010-09-09'

if args.nfs:
    fs_type = "nfs"

if args.cli7 == -1:
    args.cli7 = len(instance_types)
    args.cli7_arch = ",".join(instance_types.keys())
if args.cli8 == -1:
    args.cli8 = len(instance_types)
    args.cli8_arch = ",".join(instance_types.keys())
if args.cli9 == -1:
    args.cli9 = len(instance_types)
    args.cli9_arch = ",".join(instance_types.keys())
if args.cli10 == -1:
    args.cli10 = len(instance_types)
    args.cli10_arch = ",".join(instance_types.keys())

json_dict['Description'] = "Client-only stack" if args.cli_only else "RHUI-in-a-box" if args.boxed else f"RHUI with {args.cds} CDS and {args.haproxy} HAProxy nodes"
if args.cli7 > 0:
    json_dict['Description'] += f", {args.cli7} RHEL7 client" + ("s" if args.cli7 > 1 else "")
if args.cli8 > 0:
    json_dict['Description'] += f", {args.cli8} RHEL8 client" + ("s" if args.cli8 > 1 else "")
if args.cli9 > 0:
    json_dict['Description'] += f", {args.cli9} RHEL9 client" + ("s" if args.cli9 > 1 else "")
if args.cli10 > 0:
    json_dict['Description'] += f", {args.cli10} RHEL10 client" + ("s" if args.cli10 > 1 else "")
if args.test:
    json_dict['Description'] += ", TEST machine"
if args.nfs:
    json_dict['Description'] += ", NFS"
if args.clone:
    json_dict['Description'] += ", another RHUA (for cloning or saving&restoring)"


fs_type_f = fs_type

if fs_type_f == "rhua":
    fs_type_f = "nfs"

cli_os_versions = (7, 8, 9, 10)

json_dict['Mappings'] = {f"RHEL{i}": {args.region: {}} for i in cli_os_versions}

try:
    for i in cli_os_versions:
        if override := getattr(args, f"ami_{i}_override"):
            json_dict["Mappings"][f"RHEL{i}"][args.region]["AMI"] = override
        else:
            with open(f"RHEL{i}mapping.json", encoding="utf-8") as mjson:
                mapping = json.load(mjson)
                json_dict["Mappings"][f"RHEL{i}"] = mapping
except FileNotFoundError:
    sys.stderr.write("Missing mapping file")
    sys.exit(1)
except json.JSONDecodeError:
    sys.stderr.write("Bad JSON")
    sys.exit(1)
except Exception as e:
    sys.stderr.write(f"Got '{e}' error")
    sys.exit(1)

def concat_name(node='', cfgfile=False):
    """concatenate several properties to give a name to the inventory file"""
    return '_'.join(filter(None,
                           ['hosts' if cfgfile else ec2_name,
                            fs_type_f,
                            args.name,
                            node])
                    ) + ('.cfg' if cfgfile else '')

json_dict['Parameters'] = \
{"KeyName": {"Description": "Name of an existing EC2 KeyPair to enable SSH access to the instances",
              "Type": "String"}}

ports = [22, 443, 2049, 3128]
if args.boxed:
    ports.append(8443)

sgingress = [{"CidrIp": "0.0.0.0/0",
              "FromPort": port,
              "ToPort": port,
              "IpProtocol": "tcp"} for port in ports]
json_dict["Resources"] = \
{"RHUIsecuritygroup": {"Properties": {"GroupDescription": "RHUI security group",
                                      "SecurityGroupIngress": sgingress},
                       "Type": "AWS::EC2::SecurityGroup"}}

# launchpad
if not args.cli_only:
    image_id = args.launchpad_ami or \
               {"Fn::FindInMap": [f"RHEL{args.launchpad_os}", {"Ref": "AWS::Region"}, "AMI"]}
    json_dict['Resources']["launchpad"] = \
     {"Properties": {"ImageId": image_id,
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name("launchpad")},
                                         {"Key": "Role", "Value": "LAUNCHPAD"},
                                         ]},
               "Type": "AWS::EC2::Instance"}

# nfs == rhua
# add a 100 GB volume for RHUI repos if using NFS
if fs_type == "rhua":
    json_dict['Resources']["rhua"] = \
     {"Properties": {"ImageId": {"Fn::FindInMap": [f"RHEL{args.rhua_os}", {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                                 "BlockDeviceMappings" : [
                                            {
                                              "DeviceName" : "/dev/sdb",
                                              "Ebs" : {"VolumeSize" : "100"}
                                            }
                                 ],
                               "Tags": [{"Key": "Name", "Value": concat_name("rhua")},
                                         {"Key": "Role", "Value": "RHUA"},
                                         ]},
               "Type": "AWS::EC2::Instance"}

elif fs_type:
    json_dict['Resources']["rhua"] = \
     {"Properties": {"ImageId": {"Fn::FindInMap": [f"RHEL{args.rhua_os}", {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name("rhua")},
                                         {"Key": "Role", "Value": "RHUA"},
                                         ]},
               "Type": "AWS::EC2::Instance"}


# cdses
for i in range(1, args.cds + 1):
    json_dict['Resources'][f"cds{i}"] = \
        {"Properties": {"ImageId": {"Fn::FindInMap": [f"RHEL{args.cds_os}", {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name(f"cds{i}")},
                                         {"Key": "Role", "Value": "CDS"},
                                         ]},
               "Type": "AWS::EC2::Instance"}

# clients
for i in cli_os_versions:
    if num_cli_ver := getattr(args, f"cli{i}"):
        os = f"RHEL{i}"
        for j in range(1, num_cli_ver + 1):
            try:
                cli_arch = getattr(args, f"cli{i}_arch").split(",")[j-1] or "x86_64"
            except (AttributeError, IndexError):
                cli_arch = "x86_64"
            try:
                instance_type = instance_types[cli_arch] if i >= 7 else 'm3.large' if args.novpc else 'i3.large'
            except KeyError:
                logging.error("Unknown architecture: %s", cli_arch)
                sys.exit(1)
            if cli_arch == "x86_64":
                image_id = {"Fn::FindInMap": [os, {"Ref": "AWS::Region"}, "AMI"]}
            else:
                if args.novpc:
                    logging.error("EC2 Classic can only be used with x86_64 instances.")
                    logging.error("Stack creation would fail. Quitting.")
                    sys.exit(1)
                if i == 8 and args.ami_8_arm64_override:
                    image_id = args.ami_8_arm64_override
                elif i == 9 and args.ami_9_arm64_override:
                    image_id = args.ami_9_arm64_override
                elif i == 10 and args.ami_10_arm64_override:
                    image_id = args.ami_10_arm64_override
                else:
                    with open(f"RHEL{i}mapping_{cli_arch}.json", encoding="utf-8") as mjson:
                        image_ids =  json.load(mjson)
                        image_id = image_ids[args.region]["AMI"]
            json_dict['Resources'][f"cli{i}nr{j}"] = \
                {"Properties": {"ImageId": image_id,
                                   "InstanceType": instance_type,
                                   "KeyName": {"Ref": "KeyName"},
                                   "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                                   "Tags": [{"Key": "Name", "Value": concat_name(f"cli{i}_{j}")},
                                             {"Key": "Role", "Value": "CLI"},
                                             {"Key": "OS", "Value": os}]},
                   "Type": "AWS::EC2::Instance"}

# nfs
if fs_type == "nfs":
    json_dict['Resources']["nfs"] = \
     {"Properties": {"ImageId": {"Fn::FindInMap": [f"RHEL{args.rhua_os}", {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                                 "BlockDeviceMappings" : [
                                            {
                                              "DeviceName" : "/dev/sdb",
                                              "Ebs" : {"VolumeSize" : "100"}
                                            },
                                 ],
                               "Tags": [{"Key": "Name", "Value": concat_name("nfs")},
                                         {"Key": "Role", "Value": "NFS"},
                                         ]},
               "Type": "AWS::EC2::Instance"}

# test
if args.test:
    os = "RHEL9"
    json_dict['Resources']["test"] = \
     {"Properties": {"ImageId": {"Fn::FindInMap": [os, {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name("test")},
                                         {"Key": "Role", "Value": "TEST"},
                                         ]},
               "Type": "AWS::EC2::Instance"}

# HAProxy
for i in range(1, args.haproxy + 1):
    json_dict['Resources'][f"haproxy{i}"] = \
        {"Properties": {"ImageId": {"Fn::FindInMap": [f"RHEL{args.haproxy_os}", {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name(f"haproxy{i}")},
                                         {"Key": "Role", "Value": "HAProxy"},
                                         ]},
                   "Type": "AWS::EC2::Instance"}

# clone
if args.clone:
    os = "RHEL9"
    json_dict['Resources']["anotherrhua"] = \
     {"Properties": {"ImageId": {"Fn::FindInMap": [os, {"Ref": "AWS::Region"}, "AMI"]},
                               "InstanceType": instance_types["x86_64"],
                               "KeyName": {"Ref": "KeyName"},
                               "SecurityGroups": [{"Ref": "RHUIsecuritygroup"}],
                               "Tags": [{"Key": "Name", "Value": concat_name("anotherrhua")},
                                         {"Key": "Role", "Value": "ANOTHERRHUA"},
                                         ]},
               "Type": "AWS::EC2::Instance"}


if not args.novpc:
    # Setting VpcId and SubnetId
    json_dict['Outputs'] = {}
    for key in list(json_dict['Resources']):
        # We'll be changing dictionary so retyping to a list is required to ensure compatibility with Python 3.7+.
        if json_dict['Resources'][key]['Type'] == 'AWS::EC2::SecurityGroup':
            json_dict['Resources'][key]['Properties']['VpcId'] = vpcid
        elif json_dict['Resources'][key]['Type'] == 'AWS::EC2::Instance':
            json_dict['Resources'][key]['Properties']['SubnetId'] = subnetid
            json_dict['Resources'][key]['Properties']['SecurityGroupIds'] = json_dict['Resources'][key]['Properties'].pop('SecurityGroups')
            json_dict['Resources'][f"{key}EIP"] = \
            {
                "Type" : "AWS::EC2::EIP",
                "Properties" : {"Domain" : "vpc",
                                "InstanceId" : {"Ref" : key}
                               }
            }


json_dict['Outputs'] = {}

json_body = json.dumps(json_dict, indent=4)

STACK_ID = f"STACK-{ec2_name}-{args.name}-{''.join(random.choice(string.ascii_lowercase) for x in range(10))}"
logging.info("Creating stack with ID %s", STACK_ID)

parameters = [{"ParameterKey": "KeyName", "ParameterValue": ssh_key_name}]

if args.dry_run:
    print("Dry run.")
    print("This would be the template:")
    print(json_body)
    print("This would be the parameters:")
    print(parameters)
    sys.exit(0)

cf_client = boto3.client("cloudformation", region_name=args.region)
cf_client.create_stack(StackName=STACK_ID,
                       TemplateBody=json_body,
                       Parameters=parameters,
                       TimeoutInMinutes=args.timeout)

is_complete = False
success = False
while not is_complete:
    time.sleep(10)
    response = cf_client.describe_stacks(StackName=STACK_ID)
    status = response["Stacks"][0]["StackStatus"]
    if status == "CREATE_IN_PROGRESS":
        continue
    if status == "CREATE_COMPLETE":
        logging.info("Stack creation completed")
        is_complete = True
        success = True
    elif status in ("ROLLBACK_IN_PROGRESS", "ROLLBACK_COMPLETE"):
        logging.info("Stack creation failed: %s", status)
        is_complete = True
    else:
        logging.error("Unexpected stack status: %s", status)
        break

if not success:
    print("Review the stack in the CloudFormation console and diagnose the reason.")
    print("Be sure to delete the stack. Even stacks that were rolled back still consume resources!")
    sys.exit(1)

# obtain information about the stack
resources = cf_client.describe_stack_resources(StackName=STACK_ID)
# create a dict with items such as haproxy1EIP: 50:60:70:80
ip_addresses = {resource["LogicalResourceId"]: resource["PhysicalResourceId"] \
                for resource in resources['StackResources'] \
                if resource["ResourceType"] == "AWS::EC2::EIP"}
# create another, more useful dict with roles: hostnames
hostnames = {lri.replace("EIP", ""): socket.getfqdn(ip) \
             for lri, ip in ip_addresses.items()}
# also create a list of instance IDs to print in the end
instance_ids = [resource["PhysicalResourceId"] \
                for resource in resources['StackResources'] \
                if resource["ResourceType"] == "AWS::EC2::Instance"]

# output file
if args.output_conf:
    outfile = args.output_conf
else:
    outfile = concat_name(cfgfile=True)

try:
    with open(outfile, "w", encoding="utf-8") as f:
        # launchpad
        f.write('[LAUNCHPAD]\n')
        for role, hostname in hostnames.items():
            if role == "launchpad":
                f.write(hostname)
                if args.launchpad_user:
                    f.write(" ansible_ssh_user=" + args.launchpad_user)
                if ssh_key:
                    f.write(" ansible_ssh_private_key_file=" + ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                f.write('\n')
        # rhua
        f.write('\n[RHUA]\n')
        for role, hostname in hostnames.items():
            if role == "rhua":
                f.write(hostname)
                if ssh_key:
                    f.write(" ansible_ssh_private_key_file=" + ssh_key)
                if args.ansible_ssh_extra_args:
                    f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                f.write('\n')
        # rhua as nfs
        if fs_type == "rhua":
            f.write('\n[NFS]\n')
            for role, hostname in hostnames.items():
                if role == "rhua":
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # nfs
        elif fs_type == "nfs":
            f.write('\n[NFS]\n')
            for role, hostname in hostnames.items():
                if role == "nfs":
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # cdses
        if args.cds:
            f.write('\n[CDS]\n')
            for role, hostname in hostnames.items():
                if role.startswith("cds"):
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # haproxy
        if args.haproxy:
            f.write('\n[HAPROXY]\n')
            for role, hostname in hostnames.items():
                if role.startswith("haproxy"):
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # cli
        if args.cli7 or args.cli8 or args.cli9 or args.cli10:
            f.write('\n[CLI]\n')
            for role, hostname in hostnames.items():
                if role.startswith("cli"):
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # test
        if args.test:
            f.write('\n[TEST]\n')
            for role, hostname in hostnames.items():
                if role == "test":
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')
        # another RHUA
        if args.clone:
            f.write('\n[ANOTHERRHUA]\n')
            for role, hostname in hostnames.items():
                if role == "anotherrhua":
                    f.write(hostname)
                    if ssh_key:
                        f.write(" ansible_ssh_private_key_file=" + ssh_key)
                    if args.ansible_ssh_extra_args:
                        f.write(f" ansible_ssh_extra_args=\"{args.ansible_ssh_extra_args}\"")
                    f.write('\n')

except Exception as e:
    logging.error("got '%s' error processing: %s", e, args.output_conf)
    sys.exit(1)

print("Instance IDs:")
print(" ".join(instance_ids))
print(f"Inventory file contents ({outfile}):")
with open(outfile, encoding="utf-8") as outfile_fd:
    print(outfile_fd.read())
