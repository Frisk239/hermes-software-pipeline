---
status: accepted
---

# Separate the LLM operator from Pipeline authority

Prod Main is the sole LLM-facing conversational operator but is treated as an untrusted client for authorization purposes. Only the deterministic Pipeline Controller may evaluate gates or change Pipeline state, so prompt injection, misunderstood intent, or malformed tool arguments cannot grant Prod Main the ability to skip stages, approve results, or force transitions.
