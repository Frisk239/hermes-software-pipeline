---
status: accepted
---

# Use Hermes Gateway for Feishu actions and poll GitHub in local version 1

The local Pipeline Runtime exposes no public webhook endpoint. Feishu cards use Hermes' existing long-lived Feishu Gateway connection; generic card actions arrive as authenticated synthetic command events and the plugin intercepts and submits them to the Controller before Prod Main runs. GitHub delivery state is reconciled by a least-privilege GitHub App Adapter using conditional polling and explicit refresh commands, so installations behind NAT remain functional. A future optional signed webhook relay may reduce latency but cannot become the sole source of Git or approval facts.
