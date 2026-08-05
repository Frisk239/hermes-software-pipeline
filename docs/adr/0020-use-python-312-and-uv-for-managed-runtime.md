---
status: accepted
---

# Use Python 3.12 and uv for the managed runtime

The managed Pipeline Runtime targets Python `>=3.12,<3.13` and uses `uv`, `pyproject.toml`, and a committed cross-platform `uv.lock`. Runtime environments are installed outside the mutable plugin checkout and are versioned with the plugin release, allowing Windows and Linux to reproduce exact dependencies without coupling them to the Python interpreter or packages used by Hermes.
