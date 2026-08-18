"""``hermes pipeline`` CLI command tree for the Hermes Shim (slice-00-05).

SPIKE-EXPERIMENTAL marker:
DISPOSITION: ADOPTED_BY_00-07

Registers exactly one top-level ``pipeline`` CLI command with lifecycle
plus ``submit`` / ``read`` via
``ctx.register_cli_command``. Every handler prints one structured bounded
JSON document with a stable exit code (0 success, 1 failure). Handlers
never emit hostnames, usernames, absolute paths, environment values,
tokens, raw exceptions, or database content.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._lifecycle import (
    admin_command,
    deliver_command,
    doctor_command,
    read_pipeline_command,
    setup_command,
    start_command,
    status_command,
    stop_command,
    submit_requirement_command,
)
from ._state import hermes_home

SUBCOMMANDS = (
    "setup",
    "doctor",
    "start",
    "status",
    "stop",
    "submit",
    "read",
    "admin",
    "deliver",
)

SUBCOMMAND_HELP = {
    "setup": "create the lifecycle state-root layout (idempotent)",
    "doctor": "report runtime, protocol, descriptor, and state-root health",
    "start": "provision and start the fake managed runtime (idempotent)",
    "status": "report the runtime descriptor and liveness",
    "stop": "stop the fake managed runtime (no-op when not running)",
    "submit": "confirm a requirement through the running kernel",
    "read": "read one pipeline fixture view",
    "admin": "register a project, admit a member, or bind a stage role",
    "deliver": "record a namespaced PR, or a check/review/queue event",
}


def _plugin_dir() -> Path:
    """The Hermes plugin checkout root (parent of the hermes_shim/ package)."""
    return Path(__file__).resolve().parent.parent


def build_pipeline_parser(parser: argparse.ArgumentParser) -> None:
    """argparse setup_fn: attach lifecycle plus submit/read handlers."""
    subparsers = parser.add_subparsers(dest="pipeline_command")
    for name in SUBCOMMANDS:
        sub = subparsers.add_parser(name, help=SUBCOMMAND_HELP[name])
        if name == "submit":
            sub.add_argument("--text", required=True)
            sub.add_argument("--command-id", required=True)
            sub.add_argument("--workspace-id", default="ws_local")
            sub.add_argument("--project-id", default="prj_local")
            sub.add_argument("--pipeline-id", default="pl_local")
            sub.add_argument("--principal-id", default="operator")
        if name == "read":
            sub.add_argument("--workspace-id", default="ws_local")
            sub.add_argument("--pipeline-id", default="pl_local")
        if name == "admin":
            sub.add_argument("--register", action="store_true")
            sub.add_argument("--admit", action="store_true")
            sub.add_argument("--bind", action="store_true")
            sub.add_argument("--project-id", default="")
            sub.add_argument("--name", default="")
            sub.add_argument("--principal-id", default="")
            sub.add_argument("--member-role", default="")
            sub.add_argument("--role", default="")
            sub.add_argument("--runtime", default="")
            sub.add_argument("--model", default="")
        if name == "deliver":
            sub.add_argument("--sha", default="")
            sub.add_argument("--project-id", default="prj_local")
            sub.add_argument("--pipeline-id", default="pl_local")
            sub.add_argument("--event-id", default="")
            sub.add_argument("--check", default="")
            sub.add_argument("--review", default="")
            sub.add_argument("--queue", default="")
        sub.set_defaults(pipeline_handler=name)
    # The top-level fallback handler prints usage as bounded JSON.
    parser.set_defaults(pipeline_handler="__root__")


def _emit(result: object, exit_code: int) -> int:
    import json

    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return exit_code


def _run_handler(name: str, _args: argparse.Namespace) -> int:
    """Dispatch one subcommand using the resolved HERMES_HOME."""
    home = hermes_home()
    try:
        if name == "setup":
            result = setup_command(home)
        elif name == "doctor":
            result = doctor_command(home, _plugin_dir())
        elif name == "start":
            result = start_command(home, _plugin_dir())
        elif name == "status":
            result = status_command(home)
        elif name == "stop":
            result = stop_command(home)
        elif name == "submit":
            result = submit_requirement_command(
                home,
                text=str(_args.text),
                command_id=str(_args.command_id),
                workspace_id=str(_args.workspace_id),
                project_id=str(_args.project_id),
                pipeline_id=str(_args.pipeline_id),
                principal_id=str(_args.principal_id),
            )
        elif name == "read":
            result = read_pipeline_command(
                home,
                workspace_id=str(_args.workspace_id),
                pipeline_id=str(_args.pipeline_id),
            )
        elif name == "admin":
            result = admin_command(
                home,
                register=bool(_args.register),
                admit=bool(_args.admit),
                bind=bool(_args.bind),
                project_id=str(_args.project_id),
                name=str(_args.name),
                principal_id=str(_args.principal_id),
                member_role=str(_args.member_role),
                role=str(_args.role),
                runtime=str(_args.runtime),
                model=str(_args.model),
            )
        elif name == "deliver":
            result = deliver_command(
                home,
                sha=str(_args.sha),
                project_id=str(_args.project_id),
                pipeline_id=str(_args.pipeline_id),
                event_id=str(_args.event_id),
                check_status=str(_args.check),
                review_status=str(_args.review),
                queue_status=str(_args.queue),
            )
        else:
            result = {"command": "pipeline", "ok": False, "error": "no subcommand"}
            return _emit(result, 2)
    except Exception as exc:  # never leak raw exceptions to the operator
        result = {"command": name, "ok": False, "error": f"{type(exc).__name__}"}
        return _emit(result, 1)
    return _emit(
        result.as_json() if hasattr(result, "as_json") else result, result.exit_code
    )


def pipeline_handler(args: argparse.Namespace) -> int:
    """The default dispatch function bound by set_defaults(func=...)."""
    return _run_handler(str(args.pipeline_handler), args)


def register(ctx: object) -> None:
    """Register the pipeline CLI command tree on a Hermes PluginContext."""
    ctx.register_cli_command(
        name="pipeline",
        help="Hermes Software Pipeline lifecycle commands (spike)",
        setup_fn=build_pipeline_parser,
        handler_fn=pipeline_handler,
        description="Manage the fake managed runtime for the Slice 00-05 spike",
    )


__all__ = ["build_pipeline_parser", "pipeline_handler", "register"]
