from __future__ import annotations

import ast
from pathlib import Path

from hermes_pipeline.delivery import DeliveryPort, DeliveryRequest, GitHubDelivery

GITHUB_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "hermes_pipeline"
    / "delivery"
    / "github.py"
)
FORBIDDEN = frozenset({"git", "subprocess", "github"})


def test_github_delivery_is_a_port() -> None:
    def _transport(
        method: str, path: str, headers: dict[str, str], body: dict[str, object]
    ) -> tuple[int, object]:
        del method, path, headers, body
        return 201, {"number": 7, "html_url": "https://github.com/o/r/pull/7"}

    fake = GitHubDelivery("o/r", "tok_secret", _transport)
    assert isinstance(fake, DeliveryPort)
    assert not hasattr(fake, "approve")
    assert not hasattr(fake, "merge")


def test_publish_opens_one_pr_and_hides_token() -> None:
    seen: list[str] = []

    def _transport(
        method: str, path: str, headers: dict[str, str], body: dict[str, object]
    ) -> tuple[int, object]:
        del path, body
        seen.append(method)
        assert headers["Authorization"] == "Bearer tok_secret"
        return 201, {
            "number": 7,
            "html_url": "https://github.com/o/r/pull/7",
        }

    delivery = GitHubDelivery("o/r", "tok_secret", _transport)
    request = DeliveryRequest(name="a" * 64, project_id="prj_a", pipeline_id="pl_a")
    first = delivery.publish(request)
    again = delivery.publish(request)
    assert first.ok is True
    assert first.pr_number == 7
    assert first.branch == "hermes/prj_a/pl_a"
    assert first.pr_url == "https://github.com/o/r/pull/7"
    assert "tok_secret" not in first.pr_url
    assert again == first
    assert seen == ["POST"]


def test_missing_token_fails_closed() -> None:
    def _transport(
        method: str, path: str, headers: dict[str, str], body: dict[str, object]
    ) -> tuple[int, object]:
        del method, path, headers, body
        raise AssertionError("must not call GitHub")

    missed = GitHubDelivery("o/r", "", _transport).publish(
        DeliveryRequest(name="a" * 64, pipeline_id="pl_a")
    )
    assert missed.ok is False


def test_github_adapter_never_imports_git() -> None:
    tree = ast.parse(GITHUB_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(FORBIDDEN)
