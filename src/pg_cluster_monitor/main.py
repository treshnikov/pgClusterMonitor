import sys
from utils import shell
from utils import logger
from monitor.cluster_monitor import DbClusterMonitor

if __name__ == '__main__':
    logger.init_logging()

    config_loaded = False
    config = {}
    while not config_loaded:
        config_loaded, config = shell.load_config_ini()

    app = DbClusterMonitor(config)
    sys.exit(app.start())
