"""Host-side GitHub publish via the ``gh`` CLI. No token, no pipeline import.

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def gh_available(runner: Any = None) -> bool:
    if runner is None and shutil.which("gh") is None:
        return False
    run = runner or _run
    code, _out, _err = run(["gh", "auth", "status"])
    return code == 0


def publish_with_gh(
    *,
    repo: str,
    project_id: str,
    pipeline_id: str,
    sha: str,
    files: dict[str, str],
    base: str = "main",
    runner: Any = None,
) -> dict[str, str]:
    if repo.count("/") != 1 or not files or not gh_available(runner):
        return {}
    branch = f"hermes/{project_id}/{pipeline_id}"

    def api(method: str, path: str, body: dict[str, object]) -> tuple[int, object]:
        return _gh_api(method, path, body, runner)

    head = _push_files(api, repo, branch, files, sha, base)
    if not head:
        return {}
    number, url = _open_pr(api, repo, branch, base, pipeline_id)
    if number <= 0:
        return {}
    return {
        "pr_number": str(number),
        "pr_url": url,
        "branch": branch,
        "head_sha": head,
    }


def worktree_files(root: Path, pipeline_id: str) -> dict[str, str]:
    folder = root / "worktrees" / pipeline_id
    if not folder.is_dir():
        return {}
    files: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            rel = path.relative_to(folder).as_posix()
            files[rel] = path.read_text(encoding="utf-8")
    return files


def _push_files(
    api: Any,
    repo: str,
    branch: str,
    files: dict[str, str],
    message: str,
    base: str,
) -> str:
    status, ref = api("GET", f"/repos/{repo}/git/ref/heads/{base}", {})
    if status >= 300 or not isinstance(ref, dict):
        return ""
    obj = ref.get("object")
    if not isinstance(obj, dict):
        return ""
    parent = str(obj.get("sha", ""))
    status, commit = api("GET", f"/repos/{repo}/git/commits/{parent}", {})
    if status >= 300 or not isinstance(commit, dict):
        return ""
    tree_obj = commit.get("tree")
    if not isinstance(tree_obj, dict):
        return ""
    base_tree = str(tree_obj.get("sha", ""))
    entries: list[dict[str, str]] = []
    for rel, text in files.items():
        status, blob = api(
            "POST",
            f"/repos/{repo}/git/blobs",
            {"content": text, "encoding": "utf-8"},
        )
        if status >= 300 or not isinstance(blob, dict):
            return ""
        entries.append(
            {
                "path": rel,
                "mode": "100644",
                "type": "blob",
                "sha": str(blob.get("sha", "")),
            }
        )
    status, tree = api(
        "POST",
        f"/repos/{repo}/git/trees",
        {"base_tree": base_tree, "tree": entries},
    )
    if status >= 300 or not isinstance(tree, dict):
        return ""
    status, created = api(
        "POST",
        f"/repos/{repo}/git/commits",
        {
            "message": f"hermes {message[:12]}",
            "tree": str(tree.get("sha", "")),
            "parents": [parent],
        },
    )
    if status >= 300 or not isinstance(created, dict):
        return ""
    head = str(created.get("sha", ""))
    status, _ref = api(
        "POST",
        f"/repos/{repo}/git/refs",
        {"ref": f"refs/heads/{branch}", "sha": head},
    )
    if status == 422:
        status, _ref = api(
            "PATCH",
            f"/repos/{repo}/git/refs/heads/{branch}",
            {"sha": head, "force": False},
        )
    if status >= 300:
        return ""
    return head


def _open_pr(
    api: Any, repo: str, branch: str, base: str, pipeline_id: str
) -> tuple[int, str]:
    status, payload = api(
        "POST",
        f"/repos/{repo}/pulls",
        {
            "title": f"hermes {pipeline_id}",
            "head": branch,
            "base": base,
        },
    )
    if status == 422:
        owner = repo.split("/", 1)[0]
        status, payload = api(
            "GET",
            f"/repos/{repo}/pulls?head={owner}:{branch}&state=open",
            {},
        )
        if isinstance(payload, list) and payload:
            payload = payload[0]
    if status >= 300 or not isinstance(payload, dict):
        return 0, ""
    return int(payload.get("number", 0) or 0), str(payload.get("html_url", ""))


def _gh_api(
    method: str, path: str, body: dict[str, object], runner: Any
) -> tuple[int, object]:
    run = runner or _run
    argv = ["gh", "api", "-X", method, path.lstrip("/")]
    payload = ""
    if body:
        argv.extend(["--input", "-"])
        payload = json.dumps(body, separators=(",", ":"))
    code, out, _err = run(argv, payload)
    parsed: object
    try:
        parsed = json.loads(out) if out else {}
    except ValueError:
        parsed = {}
    if code == 0:
        return 201 if method == "POST" else 200, parsed
    message = ""
    if isinstance(parsed, dict):
        message = str(parsed.get("message", ""))
    if "already exists" in message.lower() or "Validation Failed" in message:
        return 422, parsed
    return 400, parsed


def _run(argv: list[str], stdin: str = "") -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, "", ""
    return proc.returncode, proc.stdout, proc.stderr


__all__ = ["gh_available", "publish_with_gh", "worktree_files"]
