"""Stage worker process: run OpenCode/Chrome off the HTTP sidecar."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-pipeline-stage-worker")
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--pipeline-id", required=True)
    parser.add_argument("--principal-id", default="operator")
    parser.add_argument("--holder", required=True)
    parser.add_argument("--generation", type=int, required=True)
    args = parser.parse_args(argv)
    root = Path(args.state_root)
    from hermes_pipeline.transport.kernel_bridge import KernelBridge

    class _Inner:
        def process(
            self, command_id: str, payload: dict[str, object]
        ) -> dict[str, object]:
            del command_id, payload
            return {}

    bridge = KernelBridge(root, _Inner(), spawn_worker=False)
    stop = threading.Event()

    def _heartbeat() -> None:
        while not stop.wait(30):
            try:
                bridge.heartbeat_lease(
                    args.workspace_id,
                    args.pipeline_id,
                    args.holder,
                    args.generation,
                    int(time.time()),
                )
            except Exception:
                return

    thread = threading.Thread(target=_heartbeat, daemon=True)
    thread.start()
    try:
        return bridge.run_leased_stages(
            workspace_id=args.workspace_id,
            project_id=args.project_id,
            pipeline_id=args.pipeline_id,
            principal_id=args.principal_id,
        )
    finally:
        stop.set()
        bridge.release_lease(args.workspace_id, args.pipeline_id)


if __name__ == "__main__":
    sys.exit(main())
