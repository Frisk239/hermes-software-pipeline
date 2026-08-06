"""Contract registry: the locked 14-Schema identity set and its projections.

The identity lock is unchanged from the Slice 00-01 bootstrap gate
(``scripts/check_schemas.py``): exactly these 14 ``$id`` values exist, each
mapping one-to-one to a committed Schema file, an authoring model, and a
fixed OpenAPI component key (AC-07).
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from .definitions import DEFINITIONS_ID
from .engineering import ENGINEERING_MODELS
from .runtime import RUNTIME_MODELS

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

# Locked bootstrap identity set (BOOT-02); any addition, removal, or rename
# fails ``contracts check`` and the bootstrap gate.
EXPECTED_SCHEMA_IDS = frozenset(
    {
        DEFINITIONS_ID,
        "https://schemas.hermes-pipeline.dev/engineering/closeout/v1",
        "https://schemas.hermes-pipeline.dev/engineering/context-manifest/v1",
        "https://schemas.hermes-pipeline.dev/engineering/contract-change-request/v1",
        "https://schemas.hermes-pipeline.dev/engineering/execution-report/v1",
        "https://schemas.hermes-pipeline.dev/engineering/phase-plan/v1",
        "https://schemas.hermes-pipeline.dev/engineering/review-verdict/v1",
        "https://schemas.hermes-pipeline.dev/engineering/slice-contract/v1",
        "https://schemas.hermes-pipeline.dev/runtime/artifact-manifest/v1",
        "https://schemas.hermes-pipeline.dev/runtime/capability-profile/v1",
        "https://schemas.hermes-pipeline.dev/runtime/command-receipt/v1",
        "https://schemas.hermes-pipeline.dev/runtime/controller-command/v1",
        "https://schemas.hermes-pipeline.dev/runtime/evidence-bundle/v1",
        "https://schemas.hermes-pipeline.dev/runtime/pipeline-event/v1",
    }
)


@dataclass(frozen=True)
class ContractDef:
    """One registry contract: identity, committed path, and authoring model."""

    schema_id: str
    relative_path: str  # path under the repository schemas/ directory
    model: type[BaseModel] | None  # None for the common/definitions library

    @property
    def namespace(self) -> str:
        return self.schema_id.removeprefix(
            "https://schemas.hermes-pipeline.dev/"
        ).split("/")[0]

    @property
    def resource(self) -> str:
        return self.schema_id.removeprefix(
            "https://schemas.hermes-pipeline.dev/"
        ).split("/")[1]

    @property
    def version(self) -> int:
        return int(self.schema_id.rsplit("/", 1)[1].removeprefix("v"))

    @property
    def component_key(self) -> str:
        """PascalCase(namespace) + PascalCase(resource) + V + version (AC-07)."""
        return _pascal(self.namespace) + _pascal(self.resource) + f"V{self.version}"


def _pascal(part: str) -> str:
    return "".join(word.capitalize() for word in part.split("-"))


def _contracts() -> list[ContractDef]:
    """The 14 registry contracts in committed order."""
    entries: list[ContractDef] = [
        ContractDef(
            DEFINITIONS_ID,
            "schemas/common/definitions.schema.json",
            None,
        )
    ]
    for resource, model in ENGINEERING_MODELS.items():
        entries.append(
            ContractDef(
                f"https://schemas.hermes-pipeline.dev/{resource}/v1",
                f"schemas/{resource}.schema.json",
                model,
            )
        )
    for resource, model in RUNTIME_MODELS.items():
        entries.append(
            ContractDef(
                f"https://schemas.hermes-pipeline.dev/{resource}/v1",
                f"schemas/{resource}.schema.json",
                model,
            )
        )
    return entries


CONTRACTS = _contracts()

# The 14 fixed OpenAPI component keys enumerated in AC-07, in registry order.
COMPONENT_KEYS = tuple(contract.component_key for contract in CONTRACTS)


def contract_by_id(schema_id: str) -> ContractDef | None:
    """Look up one contract by its exact ``$id``."""
    for contract in CONTRACTS:
        if contract.schema_id == schema_id:
            return contract
    return None
