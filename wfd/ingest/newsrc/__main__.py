"""CLI entry point: ``py -3.11 -m wfd.ingest.newsrc <family|all|list>``."""
from . import main

if __name__ == "__main__":
    raise SystemExit(main())
