"""CLI entry point: ``py -3.11 -m wfd.ingest.gov <caltrans|deldot|nsw|all>``.

Required because ``python -m`` on a package executes ``<pkg>.__main__``; the
``if __name__ == "__main__"`` hook in ``__init__.py`` alone cannot serve it.
"""
from . import main

if __name__ == "__main__":
    raise SystemExit(main())
