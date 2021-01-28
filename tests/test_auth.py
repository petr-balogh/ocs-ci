import logging

from ocs_ci.framework import config
from ocs_ci.framework.testlib import tier1


logger = logging.getLogger(__name__)


@tier1
def test_auth():
    ibm_api_key = config.AUTH["ibmcloud"]["api_key"]
    logger.info(f"AUTH IBM CLOUD API KEY: {ibm_api_key}")
