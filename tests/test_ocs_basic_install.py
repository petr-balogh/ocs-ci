import logging
import os
import random
import subprocess
import sys
import time

import requests
import yaml
from jinja2 import Environment, FileSystemLoader

from ocs.exceptions import CommandFailed
from utility.aws import AWS


log = logging.getLogger(__name__)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
TOP_DIR = os.path.dirname(THIS_DIR)


def run(**kwargs):
    log.info("Running OCS basic installation")
    config = kwargs.get('config')
    test_data = kwargs.get('test_data')
    cluster_conf = kwargs.get('cluster_conf')

    workers, masters = None, None
    if cluster_conf:
        workers = cluster_conf.get('aws').get('cluster').get('workers')
        masters = cluster_conf.get('aws').get('cluster').get('masters')

    # Generate install-config from template
    log.info("Generating install-config")
    # TODO: determine better place to create cluster directories - (log dir?)
    cluster_dir_parent = "/tmp"
    base_name = test_data.get('cluster-name', 'ocs-ci-cluster')
    cid = random.randint(10000, 99999)
    cluster_name = f'{base_name}-{cid}'

    cluster_path = os.path.join(cluster_dir_parent, cluster_name)
    run_cmd(f"mkdir {cluster_path}")

    pull_secret_path = os.path.join(TOP_DIR, "data", "pull-secret")
    with open(pull_secret_path, "r") as f:
        pull_secret = f.readline()

    data = {"cluster_name": cluster_name,
            "pull_secret": pull_secret}
    if workers:
        data.update({'worker_replicas': workers})
    if masters:
        data.update({'master_replicas': masters})
    template = render_template("install-config.yaml.j2", data)
    log.info(f"Install config: \n{template}")
    install_config = os.path.join(cluster_path, "install-config.yaml")
    with open(install_config, "w") as f:
        f.write(template)

    # Download installer
    installer_filename = "openshift-install"
    if os.path.isfile(installer_filename):
        log.info("Installer exists, skipping download")
    else:
        log.info("Downloading openshift installer")
        ver = config.get('installer-version')
        url = (
            f"https://github.com/openshift/installer/releases/download/{ver}/"
            f"openshift-install-linux-amd64"
        )
        download_file(url, installer_filename)
        run_cmd(f"chmod +x {installer_filename}")

    # Deploy cluster
    log.info("Deploying cluster")
    run_cmd(
        f"./openshift-install create cluster "
        f"--dir {cluster_path} "
        f"--log-level debug"
    )

    # Test cluster access
    log.info("Testing access to cluster")
    os.environ['KUBECONFIG'] = f"{cluster_path}/auth/kubeconfig"
    run_cmd("oc cluster-info")

    # TODO: Create cluster object, add to test_data for other tests to utilize
    # TODO: Add volumes to worker nodes to support OSDs
    # TODO: Use Rook to install ceph on the cluster
    # retrieve rook config from cluster_conf
    rook_data = {}
    if cluster_conf:
        rook_data = cluster_conf.get('rook', {})

    # render templates and create resources
    create_rook_resource('common.yaml', rook_data, cluster_path)
    run_cmd(
        'oc label namespace openshift-storage '
        '"openshift.io/cluster-monitoring=true"'
    )
    run_cmd(
        "oc policy add-role-to-user view "
        "system:serviceaccount:openshift-monitoring:prometheus-k8s "
        "-n openshift-storage"
    )
    create_rook_resource('operator-openshift.yaml', rook_data, cluster_path)
    wait_time = 120
    log.info(f"Waiting {wait_time} seconds...")
    time.sleep(wait_time)
    run_cmd(
        "oc wait --for condition=ready pod "
        "-l app=rook-ceph-operator "
        "-n openshift-storage "
        "--timeout=120s"
    )
    run_cmd(
        "oc wait --for condition=ready pod "
        "-l app=rook-ceph-agent "
        "-n openshift-storage "
        "--timeout=120s"
    )
    run_cmd(
        "oc wait --for condition=ready pod "
        "-l app=rook-discover "
        "-n openshift-storage "
        "--timeout=120s"
    )
    create_rook_resource('cluster.yaml', rook_data, cluster_path)
    create_rook_resource('toolbox.yaml', rook_data, cluster_path)
    # TODO: need to split storage-manifest before passing to create?
    # create_rook_resource('storage-manifest.yaml', rook_data, cluster_path)
    # TODO: create service-monitor from template (need template)
    # create_rook_resource("service-monitor.yaml", rook_data, cluster_path)
    # TODO: create prometheus-rules from template (need template)
    # create_rook_resource("prometheus-rules.yaml", rook_data, cluster_path)

    # Destroy cluster (if configured)
    destroy_cmd = (
        f"./openshift-install destroy cluster "
        f"--dir {cluster_path} "
        f"--log-level debug"
    )
    if config.get("destroy-cluster"):
        log.info("Destroying cluster")
        # run this twice to ensure all resources are destroyed
        run_cmd(destroy_cmd)
        run_cmd(destroy_cmd)
        log.info(f"Removing cluster directory: {cluster_path}")
        os.remove(cluster_path)
        os.remove(installer_filename)
    else:
        log.info(f"Cluster directory is located here: {cluster_path}")
        log.info(
            f"Skipping cluster destroy. "
            f"To manually destroy the cluster execute the following cmd: "
            f"{destroy_cmd}"
        )

    return 0


def run_cmd(cmd, **kwargs):
    """
    Run an arbitrary command locally

    Args:
        cmd: command to run

    """
    log.info(f"Executing command: {cmd}")
    r = subprocess.run(
        cmd.split(),
        stdout=sys.stdout,
        stderr=sys.stderr,
        **kwargs
    )
    if r.returncode != 0:
        raise CommandFailed(
            f"Error during execution of command: {cmd}"
        )


def download_file(url, filename):
    """
    Download a file from a specified url

    Args:
        url: URL of the file to download
        filename: Name of the file to write the download to

    """
    with open(filename, "wb") as f:
        r = requests.get(url)
        f.write(r.content)
    assert r.ok


def to_nice_yaml(a, indent=2, *args, **kw):
    """Make verbose, human readable yaml"""
    # TODO: elaborate more in docstring on what this actually does
    transformed = yaml.dump(
        a,
        Dumper=yaml.Dumper,
        indent=indent,
        allow_unicode=True,
        default_flow_style=False,
        **kw
    )
    return transformed


def render_template(template_path, data):
    """
    Render a template with the given data.

    Args:
        template_path: location of the j2 template
        data: the data to be formatted into the template

    Returns: rendered template

    """
    j2_env = Environment(
        loader=FileSystemLoader(os.path.join(TOP_DIR, 'templates')),
        trim_blocks=True
    )
    j2_env.filters['to_nice_yaml'] = to_nice_yaml
    j2_template = j2_env.get_template(template_path)
    return j2_template.render(**data)


def load_config_data(data_path):
    """
    Loads YAML data from the specified path

    Args:
        data_path: location of the YAML data file

    Returns: loaded YAML data

    """
    with open(data_path, "r") as data_descriptor:
        return yaml.load(data_descriptor, Loader=yaml.FullLoader)


def create_rook_resource(template_name, rook_data, cluster_path):
    """
    Create a rook resource after rendering the specified template with
    the rook data from cluster_conf.

    Args:
        template_name: name of the ocs-deployment config template.
        rook_data: rook specific config from cluster_conf
        cluster_path: path to cluster directory, where files will be written
    """
    base_name = template_name.split('.')[0]
    template_path = os.path.join('ocs-deployment', template_name)
    template = render_template(
        template_path,
        rook_data.get(base_name, {})
    )
    cfg_file = os.path.join(cluster_path, template_name)
    with open(cfg_file, "w") as f:
        f.write(template)
    log.info(f"Creating rook resource from {template_name}")
    # TODO: logging this just for testing purposes, change to run_cmd
    log.info(f"oc create -f {cfg_file}")

def create_eb2_volumes(worker_pattern, size=100):
    """
    Create volumes on workers

    Args:
        worker_pattern (string): worker name pattern e.g.:
            cluster-55jx2-worker*
        size (int): size in GB (default: 100)
    """
    aws = AWS()
    worker_instances = aws.get_instances_by_name_pattern(worker_pattern)
    for worker in worker_instances:
        aws.create_volume_and_attach(
            availability_zone=worker['avz'],
            instance_id=worker['id'],
            name=f"{worker['name']}_extra_volume",
            size=size,
        )
