# contrib/jgi/logging_setup.py
import logging
import sys

def configure_logging(level=logging.INFO) -> None:
    # force=True ensures a clean root handler even under pytest
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )