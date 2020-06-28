#!/usr/bin/env python
import sys
import time

import rssant_common.django_setup  # noqa:F401
from rssant_config import CONFIG
from rssant_common.logger import configure_logging

##
if __name__ == '__main__':
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    configure_logging(level=CONFIG.log_level)
    while True:
        try:
            execute_from_command_line(sys.argv)
        except Exception as ex:
            print(f'* {type(ex).__name__}: {ex}')
            time.sleep(3)
        else:
            break
##