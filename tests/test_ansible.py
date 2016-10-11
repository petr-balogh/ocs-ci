import yaml
import os
import logging
import sys
import requests
import time
import json

from ceph.utils import keep_alive
from ceph.utils import setup_repos, generate_repo_file, create_ceph_conf

logger = logging.getLogger(__name__)
log = logger


def run(**kw):
    log.info("Running test")
    ceph_nodes = kw.get('ceph_nodes')
    log.info("Running ceph ansible test")
    config = kw.get('config')
    if config.get('base_url'):
        base_url = config.get('base_url')
    else:
        base_url = base_url = 'http://download-node-02.eng.bos.redhat.com/rcm-guest/ceph-drops/auto/ceph-2-rhel-7-compose/latest-RHCEPH-2-RHEL-7/'
    installer_url=None
    if config.get('installer_url'):
        installer_url = config.get('installer_url')
    if config.get('skip_setup') is True:
        log.info("Skipping setup of ceph cluster")
        return 0
    for node in ceph_nodes:
        if node.role == 'mon':
            ceph_installer = node
            break
    ceph1 = ceph_nodes[0]
    out, _ = ceph1.exec_command(cmd='uuidgen')
    uuid = out.read().strip()
    ceph_mon_nodes = []
    mon_names = ''
    all_nodes = ''
    for ceph in ceph_nodes:
        if ceph.role == 'mon':
            ceph_mon_nodes.append(ceph)
            mon_names = mon_names + ceph.shortname + ' '
        all_nodes = all_nodes + ceph.shortname + ' '
    ceph_conf = create_ceph_conf(fsid=uuid, mon_hosts=ceph_mon_nodes)
    keys = ''
    hosts = ''
    hostkeycheck = 'Host *\n\tStrictHostKeyChecking no\n\tServerAliveInterval 2400\n'

    for ceph in ceph_nodes:
        ceph.generate_id_rsa()
        keys = keys + ceph.id_rsa_pub
        hosts = hosts + ceph.ip_address + "\t" + ceph.hostname \
            + "\t" + ceph.shortname + "\n"
        
    # check to see for any additional repo (test mode)
    if config.get('add-repo'):
        repo = config['add-repo']
        for ceph in ceph_nodes:
            if ceph.pkg_type == 'rpm':
                log.info("Additing addition repo {repo} to {sn}".format(repo=repo,sn=ceph.shortname))
                ceph.exec_command(sudo=True,
                                  cmd='wget -O /etc/yum.repos.d/rh_add_repo.repo {repo}'.format(repo=repo))
                ceph.exec_command(cmd='sudo yum update metadata')

    for ceph in ceph_nodes:
        keys_file = ceph.write_file(
            file_name='.ssh/authorized_keys', file_mode='w')
        hosts_file = ceph.write_file(
            sudo=True, file_name='/etc/hosts', file_mode='a')
        ceph.exec_command(cmd='[ -f ~/.ssh/config ] && chmod 700 ~/.ssh/config')
        ssh_config = ceph.write_file(file_name='.ssh/config', file_mode='a')
        keys_file.write(keys)
        hosts_file.write(hosts)
        ssh_config.write(hostkeycheck)
        keys_file.flush()
        hosts_file.flush()
        ssh_config.flush()
        ceph.exec_command(cmd='chmod 600 ~/.ssh/authorized_keys')
        ceph.exec_command(cmd='chmod 400 ~/.ssh/config')

    for ceph in ceph_nodes:
        if config.get('use_cdn') is False:
            setup_repos(ceph, base_url, installer_url)
        else:
            log.info("Using the cdn repo for the test")
        log.info("Updating metadata")
        ceph.exec_command(sudo=True, cmd='yum update metadata')
    ceph_installer.exec_command(
        sudo=True, cmd='cd cd; yum install -y ceph-ansible ; sleep 4')
    ceph_installer.exec_command(cmd='cp -R /usr/share/ceph-ansible ~/ ; sleep 2')
    mon_hosts = []
    osd_hosts = []
    rgw_hosts = []
    mds_hosts = []
    for node in ceph_nodes:
        node.set_eth_interface()
        mon_interface = ' monitor_interface=' + node.eth_interface + ' '
        if node.role == 'mon':
            mon_host = node.shortname + ' monitor_interface=' + node.eth_interface
            mon_hosts.append(mon_host)
        elif node.role == 'osd':
            devices = node.no_of_volumes
            devchar = 98
            devs = []
            for vol in range(0, devices):
                dev = '/dev/vd' + chr(devchar)
                devs.append(dev)
                devchar += 1
            osd_host = node.shortname + mon_interface + " devices='" + json.dumps(devs) + "'"
            osd_hosts.append(osd_host)
        elif node.role == 'mds':
            mds_host = node.shortname + ' monitor_interface=' + node.eth_interface
            mds_hosts.append(mds_host)
        elif node.role == 'rgw':
            rgw_host = node.shortname + ' monitor_interface=' + node.eth_interface
            rgw_hosts.append(rgw_host)

    hosts_file = ''
    for hosts in mon_hosts:
        mon = '[mons]\n' + '\n'.join(mon_hosts)
        hosts_file += mon + '\n'
        break
    for hosts in osd_hosts:
        osd = '[osds]\n' + '\n'.join(osd_hosts)
        hosts_file += osd + '\n'
        break
    for hosts in mds_hosts:
        mds = '[mdss]\n' + '\n'.join(mds_hosts)
        hosts_file += mds + '\n'
        break
    for hosts in rgw_hosts:
        rgw = '[rgws]\n' + '\n'.join(rgw_hosts)
        hosts_file += rgw + '\n'
        break

    host_file = ceph_installer.write_file(
        file_name='ceph-ansible/hosts', file_mode='w')
    host_file.write(hosts_file)
    host_file.flush()

    ansible_cfg="""
---
- become: true
  hosts: mons
  roles: [ceph-mon]
- become: true
  hosts: osds
  roles: [ceph-osd]
- become: true
  hosts: mdss
  roles: [ceph-mds]
- become: true
  hosts: rgws
  roles: [ceph-rgw]
- become: true
  hosts: client
  roles: [ceph-common]
"""

    site_file = ceph_installer.write_file(
        file_name='ceph-ansible/site.yml', file_mode='w')
    site_file.write(ansible_cfg)
    site_file.flush()

    gvar = yaml.dump(config.get('ansi_config'), default_flow_style=False)
    gvars_file = ceph_installer.write_file(
        file_name='ceph-ansible/group_vars/all', file_mode='w')
    gvars_file.write(gvar)
    gvars_file.flush()

    out, rc = ceph_installer.exec_command(
        cmd='cd ceph-ansible ; ansible-playbook -i hosts site.yml', long_running=True)
    
    #Add all clients
    for node in ceph_nodes:
        if node.role == 'client':
            if node.pkg_type == 'rpm':
                node.exec_command(cmd='sudo yum install -y ceph-common')
                out, err = ceph_installer.exec_command(sudo=True, cmd='cat /etc/ceph/ceph.conf')
                ceph_conf = out.read()
                out, err = ceph_installer.exec_command(sudo=True, cmd='cat /etc/ceph/ceph.client.admin.keyring')
                ceph_keyring = out.read()
                conf_file = node.write_file(sudo=True, file_name='/etc/ceph/ceph.conf', file_mode='w')
                key_file = node.write_file(sudo=True, file_name='/etc/ceph/ceph.keyring', file_mode='w')
                conf_file.write(ceph_conf)
                key_file.write(ceph_keyring)
                conf_file.flush()
                key_file.flush()
                node.exec_command(cmd='sudo chown ceph:ceph /etc/ceph/ceph*')
                node.exec_command(cmd='sudo chmod u+rw /etc/ceph/ceph.keyring')
                node.exec_command(cmd='sudo chmod ugo+rw /etc/ceph/ceph.conf')
    return rc