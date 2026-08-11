"""Versioned spike constants for the fake managed runtime (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: DELETE_UNLESS_ADOPTED_BY_00-07

Mirror of the shim-side spike constants; both sides are bound together by
the committed golden JSON fixtures under ``tests/fixtures/transport/``.
Descriptor and protocol versioning is fixed as these spike versioned
constants plus golden fixtures; the contract-toolchain path
(``src/hermes_pipeline/contracts/``, ``schemas/``) is out of scope.
"""

from __future__ import annotations

# Protocol version negotiated over the authenticated loopback Control
# Interface (ADR-0022). Fixed by the Slice contract.
PROTOCOL_VERSION = 1

# Runtime descriptor schema version (spike versioned constant).
DESCRIPTOR_VERSION = 1

# Runtime version and release identity (must match distribution metadata).
RUNTIME_VERSION = "0.1.0"
RELEASE = "hermes-pipeline-0.1.0-slice-00-05-spike"

# Contract-schema range reported by /v1/version.
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

# Port collision bound.
MAX_PORT_ATTEMPTS = 3

# Token and start-identity sizes (token generated per runtime start only).
TOKEN_HEX_CHARS = 64  # 256-bit bearer token
START_IDENTITY_HEX_CHARS = 32  # 128-bit start identity

# State-root child layout (fixed decision D5).
STATE_ROOT_NAME = "software-pipeline"
DESCRIPTOR_DIRNAME = "descriptor"
RUNTIMES_DIRNAME = "runtimes"
LOGS_DIRNAME = "logs"
DESCRIPTOR_FILENAME = "runtime.json"
LOCK_FILENAME = "runtime.lock"

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

# Protocol header name/value.
PROTOCOL_HEADER = "X-Hermes-Pipeline-Protocol"
