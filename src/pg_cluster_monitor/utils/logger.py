import coloredlogs, logging
import logging.handlers
import os
from utils import shell


def init_logging():
    """Set up settings of logging - level, format, filename, etc."""

    log_fmt = "%(asctime)s %(levelname)s: %(message)s"

    level_styles = coloredlogs.DEFAULT_LEVEL_STYLES
    level_styles['debug']['color'] = ''
    coloredlogs.install(level='DEBUG', fmt=log_fmt, level_styles=level_styles)

    logging.basicConfig(format=log_fmt, level=logging.DEBUG)

    log_filename = os.path.join(shell.get_app_directory(), "log.log")
    print(f"Path to log file = {log_filename}")

    log_handler = logging.handlers.RotatingFileHandler(filename=log_filename, mode="a", maxBytes=104857600, backupCount=10)
    log_handler.setFormatter(logging.Formatter(log_fmt))

    logging.getLogger("logger").addHandler(log_handler)
