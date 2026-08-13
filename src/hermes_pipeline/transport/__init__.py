"""transport module (slice-00-05 spike): fake managed runtime entry.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: KEEP_MARKED_EVIDENCE

The fake managed runtime spike and its entry (``python -m
hermes_pipeline.transport``, launched by the Hermes shim with a controlled
argv array): a loopback-only FastAPI/Uvicorn server (authorized only by
accepted ADR-0028), the protected runtime descriptor, spike versioned
protocol constants plus golden JSON fixtures, and a disposable stdlib
``sqlite3`` receipt store. This module deliberately carries no production
business behavior and never becomes production foundation without an
explicit Slice 00-07 adoption.

The Module boundary is fixed by
``docs/architecture/system-and-module-design.md``; the module keeps the
0.1.0 ``hermes-pipeline`` package importable from the isolated
``runtime-env/`` Managed Runtime without ``PYTHONPATH`` manipulation.
"""
