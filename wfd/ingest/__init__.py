"""wfd.ingest — per-family enumerators + dataset ingesters.

Each module produces normalized CameraRows (see wfd.schema) wrapped in an
IngestResult (see wfd.ingest.base). Ingestion is storage-agnostic: callers
decide whether to write JSONL, the SQLite registry (wfd.db), or both.

Modules:
- base      — contracts + polite HTTP (implemented)
- exposure  — insecam-class dataset ingesters (build task B)
- les       — Live-Environment-Streams corpus ingester (build task C)
- gov/      — government enumerator scaffold + exemplars (build task C)
"""
