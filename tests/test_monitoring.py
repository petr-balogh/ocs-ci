import logging
from ocs_ci.ocs.monitoring import create_configmap_cluster_monitoring_pod
import pytest


logger = logging.getLogger(__name__)


@pytest.mark.testing
def test_setup_monitoring():
    logger.info("Setting up monitoring")
    create_configmap_cluster_monitoring_pod(sc_name="ocs-storagecluster-ceph-rbd")
    logger.info("Done")
