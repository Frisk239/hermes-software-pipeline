"""Shared spike constants for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07

Versioned spike constants shared by the Hermes-loaded shim and the fake
managed runtime. The runtime entry under ``src/hermes_pipeline/transport/``
mirrors these exact values as its own versioned constants; the committed
golden JSON fixtures under ``tests/fixtures/transport/`` bind both sides to
one descriptor/protocol shape (the contract-toolchain path is out of scope
for this Slice).
"""

from __future__ import annotations

# Protocol version negotiated over the authenticated loopback Control
# Interface (ADR-0022). Fixed by the Slice contract (X-Hermes-Pipeline-
# Protocol: 1).
PROTOCOL_VERSION = 1

# Runtime descriptor schema version (spike versioned constant).
DESCRIPTOR_VERSION = 1

# The plugin/runtime release identity recorded in the descriptor and in
# /v1/version. The runtime version must match the installed distribution
# metadata (hermes-pipeline 0.1.0).
RUNTIME_VERSION = "0.1.0"
RELEASE = "hermes-pipeline-0.1.0-slice-00-05-spike"

# Contract-schema range reported by /v1/version: the committed
# engineering-schema range supported by this spike (bounding values only;
# the spike does not use the contract toolchain).
CONTRACT_SCHEMA_RANGE = (
    "https://schemas.hermes-pipeline.dev/engineering/slice-contract/v1:1"
)

# Loopback protocol fixed values (Slice contract must-scope).
BODY_LIMIT_BYTES = 64 * 1024  # 64 KiB on /v1/commands
RATE_WINDOW_SECONDS = 60
RATE_MAX_REQUESTS = 60
CLIENT_CONNECT_TIMEOUT_SECONDS = 5
CLIENT_READ_TIMEOUT_SECONDS = 5
REQUEST_BUDGET_SECONDS = 10

# Port collision bound: at most 3 consecutive attempts, each binding a
# fresh random loopback port; then DEPENDENCY_UNAVAILABLE.
MAX_PORT_ATTEMPTS = 3

# Token and start-identity sizes (token generated per runtime start only).
TOKEN_HEX_CHARS = 64  # 256-bit bearer token
START_IDENTITY_HEX_CHARS = 32  # 128-bit start identity

# State-root child layout (fixed decision D5):
# <HERMES_HOME>/software-pipeline/{descriptor,runtimes,logs}.
STATE_ROOT_NAME = "software-pipeline"
STATE_ROOT_CHILDREN = ("descriptor", "runtimes", "logs")
DESCRIPTOR_DIRNAME = "descriptor"
RUNTIMES_DIRNAME = "runtimes"
LOGS_DIRNAME = "logs"
DESCRIPTOR_FILENAME = "runtime.json"
LOCK_FILENAME = "runtime.lock"
OWNERSHIP_MARKER_FILENAME = "OWNERSHIP"

# The fake-probe namespace intercepted by pre_gateway_dispatch. Any event
# whose text belongs to this namespace is skipped unconditionally (even when
# the runtime is unreachable or the event is oversized) so a probe event can
# never fall through to Prod Main. The trailing space is the separator: a
# lookalike identifier such as ``hermes_pipeline_fake_probe_evil`` does not
# match the namespace. No other /card or plain event is intercepted.
PROBE_NAMESPACE_PREFIX = "/card hermes_pipeline_fake_probe "
INTAKE_NAMESPACE_PREFIX = "/card hermes_pipeline "

# Stable typed error codes (data-and-api-contracts.md).
CODE_VALIDATION_ERROR = "VALIDATION_ERROR"
CODE_AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
CODE_NOT_FOUND = "NOT_FOUND"
CODE_POLICY_REJECTED = "POLICY_REJECTED"
CODE_RATE_LIMITED = "RATE_LIMITED"
CODE_DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"

# Fixed protocol error message (Slice contract).
UNSUPPORTED_PROTOCOL_MESSAGE = "unsupported protocol version"
