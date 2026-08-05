---
status: accepted
---

# Use an authenticated loopback HTTP Control Interface

The Hermes shim and local operator commands communicate with the managed Pipeline Runtime through a FastAPI/Uvicorn HTTP Interface bound only to an operating-system-assigned loopback port. A per-installation opaque credential, strict origin and host validation, request-size limits, timeouts, protocol-version negotiation, and rotation on recovery protect the channel; the port and credential are discovered through a permission-restricted runtime descriptor. Network exposure beyond loopback is unsupported in version 1.
