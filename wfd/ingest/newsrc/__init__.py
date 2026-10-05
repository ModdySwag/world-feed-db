"""wfd.ingest.newsrc — new-source family enumerators (build unit NS).

Each family module exposes a module-level ``ENUMERATOR`` and is runnable
directly::

    py -3.11 -m wfd.ingest.newsrc.<family>

The package runner (``py -3.11 -m wfd.ingest.newsrc <family|all>``) is wired
once the family modules land (registered in this file).
"""
from __future__ import annotations

from . import base  # noqa: F401  (importable ahead of family modules)
