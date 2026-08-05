---
status: accepted
---

# Stage and verify source updates

The plugin is installed from a Git source checkout, but production updates must not be an unattended in-place `git pull`. Update detection is automatic, notification is the default policy, and optional automatic application is limited to compatible stable patch releases after signature, CI, quiescence, backup, staging, migration, restart, and health checks; minor, major, and high-risk migration releases require explicit Workspace Administrator approval.
