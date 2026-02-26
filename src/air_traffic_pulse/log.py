"""Centralised logging configuration for Air Traffic Pulse."""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with a consistent format.

    Calling this function multiple times with the same *name* is safe —
    handlers are only attached once, preventing duplicate log lines.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — return as-is to avoid duplicate handlers.
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    # Don't propagate to root logger so we control formatting entirely.
    logger.propagate = False

    return logger
