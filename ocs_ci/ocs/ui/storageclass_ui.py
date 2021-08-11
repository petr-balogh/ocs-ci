import logging
import time
from ocs_ci.ocs.ui.base_ui import PageNavigator
from ocs_ci.ocs.ui.views import locators
from ocs_ci.utility.utils import get_ocp_version
from ocs_ci.helpers.helpers import create_unique_resource_name

logger = logging.getLogger(__name__)


class StorageClassUI(PageNavigator):
    def __init__(self, driver):
        super().__init__(driver)
        ocp_version = get_ocp_version()
        self.sc_loc = locators[ocp_version]["storageclass1"]

    def create_rbd_storage_class(self):
        self.navigate_storageclasses_page()
        sc_name = create_unique_resource_name("test", "storageclass")
        self.do_click(self.sc_loc["create_storageclass1"])
        time.sleep(10)
        logger.info(f"SC Name: {sc_name}")
