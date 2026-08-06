"""Contract authoring source and toolchain (slice-00-03).

This package holds the Pydantic v2 authoring types that deterministically
generate the committed Schema registry (``schemas/``), the OpenAPI document
(``contracts/openapi.json``), and the compatibility registry
(``contracts/compatibility-registry.json``) under ADR-0024 and ADR-0026.

The toolchain modules are imported lazily, only after the ``contracts`` CLI
subcommand is parsed; importing this package alone never imports pydantic,
jsonschema, or rfc8785, so the Hermes plugin entry, ``--version``, and the
normal runtime path stay pure standard library.
"""

__all__: list[str] = []
