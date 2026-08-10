# Slice 00-05: Hermes Shim and Managed Runtime Spike — Research Report

- Status: evidence supporting READY planning (slice-00-05, exit criteria `EC-00-07` and `EC-00-11`); **revision 5 (READY rebind, 2026-08-10)** records accepted ADR-0028 after human D1 approval, binds the integrated Slice 00-04 Base, and preserves the executable runtime topology, state-root evidence, child-environment authority, and event-derived Candidate identity.
- Snapshot date: 2026-08-10
- Scope: real Hermes plugin contract (manifest, `register(ctx)`, lifecycle hooks, tool/CLI registration, source install/upgrade/uninstall boundaries), synthetic Feishu `/card` interception at `pre_gateway_dispatch`, the managed-runtime loopback boundary, dependency and isolation options, and parallel-implementation intersections with Slice 00-04
- Source policy: primary evidence is the **real local Hermes installation** `v0.20.0` (2026.8.3) at install-directory Git HEAD `be54f28b16906f4153f618eeb4369495667af7ce` (2026-08-10), cross-checked against the upstream release `v2026.8.3` (commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`, 2026-08-03) and the official plugin authoring guide shipped inside that installation. Every claim below carries its evidence path and line number. The local `reference/` clones in this repository cover Codex/OpenCode/LangGraph only and are **not** used as authority for Hermes behavior.
- Legend: ✅ verified fact (source cited) · ⚠️ assumption or risk (must be probed by the Slice) · ❓ open question

## 1. Real Hermes plugin contract

### 1.1 Installation identity and version evidence

| Fact | Value | Evidence |
| --- | --- | --- |
| Hermes CLI version | `v0.20.0` (2026.8.3) | `hermes --version` on 2026-08-10 (read-only) |
| Install directory | `C:\Users\a2691\AppData\Local\hermes\hermes-agent` | same command output |
| Host Python | `3.11.15` | same command output |
| Install-directory Git HEAD | `be54f28b16906f4153f618eeb4369495667af7ce` | `git -C …/hermes-agent rev-parse HEAD`; remote `https://github.com/NousResearch/hermes-agent.git` |
| Upstream release | tag `v2026.8.3`, title "Hermes Agent v0.20.0 (2026.8.3)", dated 2026-08-03, commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` | GitHub release page, verified 2026-08-10 |
| Upstream main reference (2026-08-05 snapshot) | commit `aec331899e4748739927fddf02a54327e64419a0` | `docs/development/compatibility-targets.md` |

The local installation tracks upstream `main` (HEAD `be54f28`), which is **newer than the release commit** `3c27eb6` and newer than the 2026-08-05 snapshot `aec3318`. Behavior verified here was verified against `main`-as-of-2026-08-10; the Slice contract must pin the **release commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` (tag `v2026.8.3`)** for reproducible CI installation and record any behavior drift. ⚠️ Upstream `main` moves; a release-gated pin is the only reproducible baseline.

Fact note (rework #1, refreshed as **historical snapshot** in rework #2): on 2026-08-10, local `main` was `4a13cfd`, ahead of `origin/main` `e238ecf` by two **unpushed planning-revision commits** (`52562b5` revision-7 contract update, `4a13cfd` digest fix), and the 00-04 execution worktree sat on `feature/slice-00-04-domain-and-persistence-spikes` at `1e1b7ad`. Those values are a **2026-08-10 observation, not current state**: 00-04's completion and the then-current `origin/main` are confirmed from Git Custodian/integration evidence **at READY time**, when the Base, manifest summaries, and the path-independence proof are re-bound. `4a13cfd`/`1e1b7ad` are not Candidates and are never used as evidence of current state.

READY rebind (2026-08-10): Slice 00-04 integrated at `46798d86a2e48551a3a634e93d1e4dfe5cbf8786` through PR #9. Git Custodian verified the exact remote-main Base, refreshed the planning inputs, and created clean detached ready-planning and execution worktrees. The former e238ecf/4a13cfd/1e1b7ad observations remain historical only.

### 1.2 Plugin sources and discovery

✅ The plugin manager discovers four sources, later sources overriding earlier on name collision (`hermes_cli/plugins.py:12-26`):

1. **Bundled** — `<hermes-agent>/plugins/<name>/` (shipped; `memory/` and `context_engine/` excluded, they have their own discovery);
2. **User** — `<HERMES_HOME>/plugins/<name>/` (`hermes_cli/plugins_cmd.py:76-82`; default home is platform-native: `%LOCALAPPDATA%\hermes` on Windows, `~/.hermes` on POSIX — `hermes_constants.py:78-91`);
3. **Project** — `./.hermes/plugins/<name>/`, opt-in via `HERMES_ENABLE_PROJECT_PLUGINS`;
4. **Pip** — packages exposing the `hermes_agent.plugins` entry-point group (`plugins.py:242-243`).

✅ `HERMES_HOME` environment variable fully redirects the home directory (context-local override → env var → platform default; `hermes_constants.py:114-140`). This is the isolation seam for CI: point `HERMES_HOME` at a temporary root and the user-plugin directory, `config.yaml`, `.env`, and state all move with it.

✅ Directory scan layouts: flat (`<root>/<plugin-name>/plugin.yaml`) and category (`<root>/<category>/<plugin-name>/plugin.yaml`); depth capped at two segments (`plugins.py:1507-1526`, `_scan_directory_level`). Registry `key` is path-derived: flat plugin key = directory name; category key = `category/name` (`plugins.py:1602-1603`).

### 1.3 Manifest (`plugin.yaml`)

✅ `PluginManifest` fields (`plugins.py:282-310`): `name` (defaults to directory name at parse time, `plugins.py:1601`), `version`, `description`, `author`, `requires_env` (list of plain strings **or** rich dicts with `name`/`description`/`url`/`secret`), `provides_tools`, `provides_hooks`, `source`, `path`, `kind`, `key`.

✅ `kind` is one of `standalone` (default), `backend`, `exclusive`, `platform`, `model-provider`; an unknown kind degrades to `standalone` with a warning; a standalone plugin whose `__init__.py` names `register_memory_provider`/`MemoryProvider` or `register_provider`+`ProviderProfile` is auto-coerced to `exclusive`/`model-provider` (`plugins.py:1608-1651`). A minimal shim must declare `kind: standalone` (or omit it) and must **not** contain those coercion markers.

✅ `manifest_version` is validated at install time as an integer ≤ `_SUPPORTED_MANIFEST_VERSION = 1`; a higher value rejects the install with "requires manifest_version … but this installer only supports up to 1" (`plugins_cmd.py:73`, `plugins_cmd.py:515-531`). A minimal manifest should either omit `manifest_version` or set `1`.

✅ Both `plugin.yaml` and `plugin.yml` are accepted (`plugins_cmd.py:533-540`, `plugins.py` scan checks `plugin.yaml`; install warns when neither manifest nor `__init__.py` exists).

✅ `optional_env` appears in shipped manifests (e.g. the Feishu platform plugin) but is **not** modeled by the general `PluginManifest` dataclass — the general loader parses only `requires_env` (`plugins.py:1659`). The shim should declare no `requires_env` at all so install and load are non-interactive (✅ `_missing_requires_env_names`/`_prompt_plugin_env_vars` iterate the declared list only — an empty list means no prompt, `plugins_cmd.py:300-357`).

### 1.4 Loading and `register(ctx)`

✅ Each directory plugin must contain `__init__.py`; it is imported as a module under the synthetic namespace `hermes_plugins.<slug>` (slug = key with `/`→`__`, `-`→`_`) via `importlib.util.spec_from_file_location(..., submodule_search_locations=[plugin_dir])` (`plugins.py:1868-1890`). Consequences:

- the plugin directory is on its own module path, so `__init__.py` may import siblings with relative imports;
- the plugin loads **inside the Hermes process** and shares its interpreter — this is why the shim must stay standard-library/Hermes-guaranteed (ADR-0019, `docs/design/technology-stack.md` "Decisive Hermes constraint");
- the module is registered in `sys.modules` as `hermes_plugins.<slug>`, so `import hermes_plugins.<slug>` from Hermes code would resolve to the loaded plugin (useful for in-process probes).

✅ `register(ctx)` is called exactly once after import with a fresh `PluginContext(manifest, manager)`; registration is attributed by registry-state diff so only what this plugin added counts (`plugins.py:1814-1842`).

✅ Failure semantics are fail-safe: a missing `register` yields `loaded.error = "no register() function"`; an exception inside `register()` is caught, `loaded.error` is set, the plugin is recorded as not enabled, and Hermes continues (`plugins.py:1844-1863`). The official guide states: "If this function crashes, the plugin is disabled but Hermes continues fine" (`website/docs/developer-guide/plugins/index.md`, Step 5).

✅ `PluginContext` surface (`plugins.py:352-…`): `manifest`; host-owned `llm` facade (fail-closed override gating via `plugins.entries.<id>.llm.*`, `plugins.py:379-398`); `subagent_lifecycle`; `profile_name` (derived from `HERMES_HOME`; returns `"default"`, the profile id, or `"custom"`); and registration methods:

- `register_tool(name, toolset, schema, handler, check_fn=None, requires_env=None, is_async=False, description="", emoji="", override=False)` — delegates to `tools.registry.register()`; built-in overrides need operator opt-in `plugins.entries.<plugin_id>.allow_tool_override` (`plugins.py:410-434`); ✅ the minimal shim registers high-level Prod Main tools as declared schemas, no override;
- `register_cli_command(name, help, setup_fn, handler_fn=None, description="")` — creates `hermes <name> …` in the **root** argparse tree (`plugins.py:523-543`); ✅ `hermes pipeline …` is this mechanism;
- `register_command(name, handler, description, args_hint)` — in-session slash commands (`/…`), sync or async handlers (`plugins.py:548-…`);
- `register_hook(hook_name, callback)` — unknown hook names warn but are stored for forward compatibility (`plugins.py:1177-1191`); ✅ a shim may safely register `pre_gateway_dispatch`;
- `register_middleware`, `register_skill`, `register_platform`, `register_auxiliary_task`, `register_secret_source`, `dispatch_tool`, plus provider registrations (`register_*_provider`).

✅ `VALID_HOOKS` (full set, `plugins.py:127-212`): `pre_tool_call`, `post_tool_call`, `transform_terminal_output`, `transform_tool_result`, `transform_llm_output`, `pre_llm_call`, `post_llm_call`, `pre_verify`, `pre_api_request`, `post_api_request`, `api_request_error`, `on_session_start`, `on_session_end`, `on_session_finalize`, `on_session_reset`, `subagent_start`, `subagent_stop`, `pre_gateway_dispatch`, `pre_approval_request`, `post_approval_response`, `kanban_task_claimed`, `kanban_task_completed`, `kanban_task_blocked`.

### 1.5 Enablement and gating

✅ Plugins are opt-in: only names in `config.yaml` → `plugins.enabled` are loaded; a missing/malformed key means "nothing enabled yet"; `plugins.disabled` is an explicit deny-list that always wins (`plugins.py:222-279`, `plugins.py:1400-1408`). User-installed standalone plugins not in the allow-list are recorded with `error = "not enabled in config (run hermes plugins enable …)"` and never imported (`plugins.py:1477-1492`). ✅ Both the path-derived key and the legacy bare `name` are accepted (`plugins.py:1470-1476`).

✅ Missing `requires_env` variables disable the plugin with a clear message instead of crashing ("Plugin weather disabled (missing: …)", official guide "Gate on environment variables"); install prompts for missing variables and saves values to `.env` (`plugins_cmd.py:300-357`, `website/docs/developer-guide/plugins/index.md`).

✅ `HERMES_SAFE_MODE=1` skips plugin discovery entirely (`plugins.py:1306-1310`).

### 1.6 Lifecycle hooks and `pre_gateway_dispatch`

✅ The hook fires once per incoming `MessageEvent`, **only for user-originated messages** (`event.internal` falsy), **before** auth/pairing/session setup, after the ignored-channel guard and the startup-restore guard (`gateway/run.py:14238-14280`, fire site `gateway/run.py:14277-14299`). Kwargs: `event` (MessageEvent), `gateway` (GatewayRunner), `session_store` (may be `None`).

✅ Callback results are a list of action dicts; first action wins (`gateway/run.py:14300-14318`):

- `{"action": "skip", "reason": …}` → drop the message, no reply, no agent dispatch (`return None`);
- `{"action": "rewrite", "text": …}` → replace `event.text` and continue dispatch;
- `{"action": "allow"}` or `None` → normal dispatch.

✅ An exception raised by the hook invocation is caught and logged ("pre_gateway_dispatch invocation failed: …"), `_hook_results = []`, and **dispatch continues** (`gateway/run.py:14292-14299`). ⚠️ Consequence for the shim: the `pre_gateway_dispatch` hook must **never raise** and, for any event that belongs to the shim's fake-probe namespace, must return `{"action": "skip"}` unconditionally (including when the runtime is unreachable) so a probe event can never fall through to Prod Main. Non-probe events must return `None`/`allow` untouched.

✅ Hermes' own tests drive the real dispatch path in-process: `GatewayRunner._handle_message` with a real `MessageEvent` and a stubbed `invoke_hook` (`tests/gateway/test_pre_gateway_dispatch.py:37-110`). ✅ This is the verified offline injection seam for the spike: load the real plugin into a real Hermes process, construct a Feishu-style synthetic `/card` `MessageEvent`, and drive `_handle_message`; the hook fires before auth, so the probe does not need any provider credential. ⚠️ The exact `GatewayRunner` attributes required for a full run (`session_store`, `pairing_store`, `adapters`, `_running_agents`, …) must be probed by the Slice; the bare-runner pattern (`object.__new__`) used by Hermes' own tests is the reference.

### 1.7 Feishu synthetic `/card` events

✅ Feishu is a **bundled platform plugin** (`plugins/platforms/feishu/plugin.yaml`, `kind: platform`, `requires_env: FEISHU_APP_ID`, `FEISHU_APP_SECRET`) using the `lark-oapi` SDK over WebSocket or webhook (`plugins/platforms/feishu/adapter.py:1411`, `:1693`). Bundled platform plugins auto-register lazily (deferred loader) so the gateway menu sees them without importing heavy SDKs (`plugins.py:1458-1468`).

✅ Interactive card button clicks become **synthetic COMMAND events**: `synthetic_text = f"/card {action_tag}"` plus `json.dumps(action_value)` when non-empty, `message_type=MessageType.COMMAND`, wrapped in a `MessageEvent` with a resolved sender/chat source, `message_id = token or uuid4`, and routed through `_handle_message_with_guards` → `handle_message` → the same dispatch path where `pre_gateway_dispatch` fires (`plugins/platforms/feishu/adapter.py:3042-3095`). Duplicate card-action tokens are dropped within a 15-minute window (`adapter.py:244`, `:2695-2727`).

✅ Conclusion for the spike: a genuine Feishu card callback requires a real Feishu app and the public Feishu connection — **forbidden in required CI**. The interception capability is instead proven by constructing the identical synthetic `MessageEvent` (`/card <tag> <json>`, `MessageType.COMMAND`) and driving the real gateway dispatch path with the shim loaded, asserting `{"action": "skip"}` and a loopback command submission with **no** Prod Main invocation. This is fixture-based evaluation as required by `AGENTS.md` ("Agent workflow changes include fixture-based evaluation").

### 1.8 Source install, upgrade, uninstall

✅ `hermes plugins install <identifier> [--enable|--no-enable]` (`plugins_cmd.py:cmd_install`):

1. identifier resolution: `owner/repo` shorthand → `https://github.com/owner/repo.git`; full `https://`, `git@`, `ssh://` URLs; URL+subdir with a `.git/` boundary; `file://` and `http://` accepted with an "insecure/local URL scheme" warning (`plugins_cmd.py:155-219`, `:564-567`) — ✅ this is the offline CI path: install from a local `file://` clone;
2. `git clone --depth 1` (60 s timeout, noninteractive env) into a temp dir (`plugins_cmd.py:450-492`);
3. subdir resolution rejects path traversal outside the clone (`plugins_cmd.py:221-234`);
4. manifest read, `manifest_version` gate (≤ 1), sanitized target name, `shutil.move` into `<HERMES_HOME>/plugins/<name>/` (force reinstall removes the existing target first) (`plugins_cmd.py:494-537`);
5. `requires_env` prompt for missing variables (skipped when none declared), then "Enable now? [y/N]" unless `--enable`/`--no-enable` given, updating `plugins.enabled`/`plugins.disabled`; prints `hermes gateway restart` advice (`plugins_cmd.py:571-635`).

✅ `hermes plugins update <name>` performs an **in-place `git pull`** from the checkout's own `.git`; refuses when the plugin was not installed from Git (`plugins_cmd.py:cmd_update`, `:652-655`). ✅ `hermes plugins uninstall <name>` removes the checkout directory (`shutil.rmtree`, `plugins_cmd.py:2039`). Durable Pipeline state lives **outside** the checkout under `<HERMES_HOME>/software-pipeline/` by design (`docs/design/source-installation-and-update.md`) and is not touched by update/uninstall. ⚠️ Note: the real plugin repository (`Frisk239/hermes-software-pipeline`) will contain the shim at the repository root (`plugin.yaml` + `__init__.py` per `source-installation-and-update.md`); a `--depth 1` clone of the default branch is what `hermes plugins install` will consume, so `main` must always stay installable — the default branch is the "source-install surface" of this repository.

### 1.9 CLI and gateway integration

✅ Plugin CLI commands register into the **root** parser: `hermes <name> …`; discovery is lazy — `_plugin_cli_discovery_needed()` skips when the first positional is a known built-in (`hermes_cli/main.py:11600-11652`); the memory plugin and general `_cli_commands` both feed the same subparser tree.

✅ `hermes gateway run|start|stop|restart|status|install|uninstall|setup` exists (`hermes_cli/gateway.py:4`); gateway startup paths call `discover_plugins()` (`hermes_cli/gateway.py:5391-5393`, `hermes_cli/main.py:10057-10059`).

✅ `hermes --version` runs offline without any account or network (verified 2026-08-10). ⚠️ Full gateway startup without provider credentials must be probed (expected: works with no platforms enabled; the `GatewayRunner` still needs a writable `HERMES_HOME`).

### 1.10 Load and registration evidence: the PluginManager probe

✅ `hermes plugins list` proves **manifest presence and activation state only** — the underlying listing returns "the user-facing activation state for a plugin name or key" (`hermes_cli/plugins_cmd.py:1112-1134`) and never proves that the module was imported or that `register(ctx)` succeeded. Load evidence must come from the plugin manager itself.

✅ Verified load-evidence surface (`hermes_cli/plugins.py`):

- `LoadedPlugin` records `tools_registered`, `hooks_registered`, `middleware_registered`, `commands_registered`, `enabled`, and `error` (`plugins.py:314-331`);
- `_load_plugin` snapshots the registries before `register(ctx)` and attributes only what this plugin added (`plugins.py:1814-1842`); a missing `register` or an exception inside it sets `loaded.error` and leaves `enabled=False` (`plugins.py:1844-1863`);
- `PluginManager` keeps the loaded map at `_plugins[key]` and registers CLI commands into `_cli_commands` (`plugins.py:1276`, `plugins.py:536-543`); `get_plugin_manager()` is importable from the Hermes environment.

✅ Therefore the executable probe is: **a subprocess running the Hermes environment's Python** that sets an isolated `HERMES_HOME`, installs/enables the plugin, calls `get_plugin_manager().discover_and_load()`, and asserts `loaded.enabled is True`, `loaded.error is None`, exactly one tool, exactly one `pre_gateway_dispatch` hook, exactly one top-level `pipeline` CLI command in `_cli_commands`, and exactly five `pipeline` subcommands (`setup`, `doctor`, `start`, `status`, `stop`). The same probe re-run with a deliberately broken plugin asserts `loaded.error` is set and Hermes keeps running (fail-safe load). This is the evidence basis for AC-01 in the contract; `hermes plugins list` output remains only a secondary manifest/enable check.

### 1.11 Facts vs risks/assumptions (Hermes side)

| # | Claim | Status |
| --- | --- | --- |
| H1 | Manifest/`register(ctx)`/hooks/CLI surface as above | ✅ verified (installed v0.20.0 source + shipped docs + upstream release) |
| H2 | `pre_gateway_dispatch` fires pre-auth for user-originated events; skip/rewrite/allow semantics | ✅ verified (`gateway/run.py:14277-14318`, Hermes' own tests) |
| H3 | Feishu card clicks become synthetic `/card` COMMAND events | ✅ verified (`plugins/platforms/feishu/adapter.py:3042-3095`) |
| H4 | `hermes plugins install file://… --enable` works offline and non-interactively for a zero-`requires_env` plugin | ✅ mechanism verified; end-to-end install of **this** plugin is an execution-time probe |
| H5 | A real gateway run with the shim loaded can be driven offline via `GatewayRunner._handle_message` with a synthetic event | ⚠️ seam verified in Hermes' own tests; full attribute surface of `GatewayRunner` must be probed by the Slice |
| H6 | Hermes CI installation at pinned commit `3c27eb6` reproduces on Windows and Linux runners | ⚠️ must be proven; install cost/disk/time bounded; the contract must pin the release commit and record `hermes --version` + install Git HEAD as evidence |
| H7 | `hermes pipeline …` CLI commands work in CLI-only sessions without the gateway | ✅ CLI registration path verified; end-to-end probe required |
| H8 | Hook invocation failure is fail-open for non-probe events | ✅ verified — contract must demand never-raise hooks and unconditional skip for probe events |
| H9 | Load/registration proof requires a PluginManager probe in an isolated Hermes Python subprocess; `hermes plugins list` is manifest/enable evidence only | ✅ verified (`plugins.py:314-331`, `:1814-1863`, `plugins_cmd.py:1112-1134`) — fixed as AC-01 evidence |

## 2. Managed runtime boundary

### 2.1 Shim constraints and code placement (binding design)

✅ ADR-0019: the Hermes-loaded `plugin.yaml` + root `__init__.py` are a **standard-library and Hermes-guaranteed** shim that registers high-level tools and operator commands; a separately bootstrapped and supervised local runtime owns LangGraph, persistence, Agents, artifacts, and durable state; the shim fails closed when the runtime is unavailable and never falls back to executing Pipeline logic inside Hermes.

✅ `docs/development/ci-and-testing.md` "Runtime dependency rule": the Hermes-loaded plugin entry depends only on the Python standard library and dependencies already guaranteed by the supported Hermes version; any future runtime dependency requires an explicit installation and isolation design.

✅ **Code placement (fixed in rework #1)**: a controlled root directory `hermes_shim/` (stdlib-only) holds the Hermes-loaded logic; the root `__init__.py` imports **only** `hermes_shim` and never imports `src/hermes_pipeline` (the src layout is not importable from the plugin directory without ambient `sys.path` mutation — verified load path, `plugins.py:1868-1890`). `src/hermes_pipeline/cli/` is **not** a 00-05 writable path. The managed-runtime entry lives **only** under `src/hermes_pipeline/transport/` and is launched by the shim as an independent interpreter with a **controlled argv array** (never a shell string), e.g. `[<managed-python>, "-m", "hermes_pipeline.transport", "--state-root", …]`. The shim needs only stdlib: `urllib.request`, `json`, `pathlib`/`os`, `subprocess`, `sys`, `platform`. It must contain no Controller logic, no Agent executor, no Git, no database, no network beyond loopback, and no runtime-dependency import.

### 2.2 Runtime lifecycle (design facts + open items)

✅ Accepted surface (`docs/architecture/system-and-module-design.md`): one Managed Pipeline Runtime per Hermes profile/Workspace; startup acquires an OS file lock plus a database lease; two runtimes may not claim the same state directory; startup order 1-10 and shutdown order 1-7 are fixed (`system-and-module-design.md` "Startup"/"Shutdown"; `docs/operations/configuration-and-lifecycle.md` "Startup sequence"/"Shutdown").

✅ Health surface: `/livez` (process liveness, deliberately unversioned), `/readyz` (storage/migrations/singleton/descriptor/config valid, unversioned), `/v1/version` (runtime, protocol, contract, compatibility metadata) (`system-and-module-design.md` Control Interface table; `data-and-api-contracts.md`; `observability-recovery-and-runbooks.md`).

✅ The runtime descriptor contains protocol version, PID, start identity, port, certificate/token generation, active release, and state-directory identity; written atomically with owner-only permissions (`system-and-module-design.md` "Control Interface").

✅ **Fixed spike semantics (rework #1 — contract-pinned values, not open items)**:

- **Start identity and stale-descriptor algorithm (cross-platform)**: every runtime start generates a fresh `start_identity` (random 128-bit hex) and records `pid` plus the process **creation time** in the descriptor. Verification of an existing descriptor before use or cleanup: (1) `os.kill(pid, 0)` — a `ProcessLookupError`/`OSError` means the process is gone → descriptor is stale and removable; (2) if the process exists, compare creation time: Linux reads `/proc/<pid>/stat` field 22 (starttime in clock ticks); Windows reads creation time via `ctypes` `kernel32.OpenProcess`/`GetProcessTimes` — a mismatch (PID reuse by an unrelated process) means stale → removable; (3) matching process and matching creation time → live, **never** removed. The creation-time source per platform is pinned in the contract; `os.kill(pid, 0)` alone is never sufficient proof of identity. Residual limit recorded: a PID-reuse window smaller than the creation-time granularity cannot be detected (documented, threat-model boundary "accidental cross-user access").
- **Port collision**: at most 3 consecutive attempts, each binding a **fresh random loopback port**; after 3 failures the runtime exits with the stable `DEPENDENCY_UNAVAILABLE` result and leaves no descriptor behind.
- **Token rotation**: a new random token is generated **only when the runtime process starts** (start, restart, or crash recovery). A Hermes-process restart merely **re-reads the existing descriptor and token** — it never rotates and never rewrites the descriptor.
- **Crash points (three, not two)**: (A) crash **before persistence** — no receipt row, command never acknowledged; retry with the same `command_id` processes the command afresh and yields exactly one receipt and one effect; (B) crash **after the receipt is persisted but before the response** — the receipt row exists, the shim saw no acknowledgement; retry with the same `command_id` returns the original receipt (dedup) with no second effect; (C) crash **after the response** — the shim holds the receipt; the shim does not resend; if a transport-level retry still occurs, dedup returns the original receipt with no second effect. A "forged" receipt (result not matching the persisted row) is rejected.
- **Bounded recovery timing**: a stale descriptor is removed and the new runtime starts within a fixed 30-second budget from `start` invocation; `status`/`doctor` never block on a dead runtime beyond the client timeout.

### 2.3 Loopback protocol (binding design)

✅ ADR-0022: authenticated loopback HTTP Control Interface — FastAPI/Uvicorn (accepted stack), OS-assigned loopback port, per-installation opaque credential, strict origin and host validation, request-size limits, timeouts, protocol-version negotiation, rotation on recovery; the port and credential are discovered through a permission-restricted runtime descriptor; network exposure beyond loopback is unsupported in v1.

✅ `data-and-api-contracts.md` "Control Interface rules": JSON only + body-size limits; bearer auth + protocol-version headers; no role/authorization claims from bodies; `202` + Command Receipt for async operations; idempotency by command identity; unversioned `/livez`/`/readyz` + `/v1/version` without Project content; no arbitrary file paths, shell commands, SQL, Git arguments, or Agent tool calls.

✅ Error contract (`data-and-api-contracts.md`): stable codes — `VALIDATION_ERROR`, `AUTHENTICATION_FAILED`, `AUTHORIZATION_DENIED`, `NOT_FOUND`, `CONFLICT`, `POLICY_REJECTED`, `LEASE_STALE`, `DEPENDENCY_UNAVAILABLE`, `RATE_LIMITED`, `INTERNAL_ERROR`.

✅ **Fixed protocol values (rework #1 — contract-pinned, both platforms)**:

| Element | Fixed value |
| --- | --- |
| Bind | loopback only: `127.0.0.1` and `::1`; never wildcard |
| Host header | must equal `127.0.0.1:<port>` or `[::1]:<port>` with the descriptor port; anything else → `400` + `POLICY_REJECTED` |
| Origin header | absent, or exactly `http://127.0.0.1:<port>` / `http://[::1]:<port>`; anything else → `403` + `POLICY_REJECTED` |
| Protocol header | `X-Hermes-Pipeline-Protocol: 1` required; missing or unsupported value → `400` + `VALIDATION_ERROR` (fixed message `unsupported protocol version`) |
| Auth | `Authorization: Bearer <descriptor token>`; bad/missing token → `401` + `AUTHENTICATION_FAILED` |
| Body limit | 64 KiB (65 536 bytes) on `/v1/commands`; exceeded → `413` + `VALIDATION_ERROR` |
| Rate limit | one client window of 60 seconds, 60 requests max, fixed window; exceeded → `429` + `RATE_LIMITED` |
| Timeouts | shim client connect/read timeout 5 s; runtime request-handling budget 10 s; `status`/`doctor` never exceed the client timeout |
| Unknown path | `404` + `NOT_FOUND` |
| Stale/absent descriptor at client side | `DEPENDENCY_UNAVAILABLE` (shim reports runtime unavailable, fails closed) |
| Version negotiation | `/v1/version` returns runtime version, protocol version `1`, contract-schema range, release, and state-root identity; mismatch is the `400` + `VALIDATION_ERROR` path above |

✅ Windows/Linux loopback binding: `127.0.0.1` and `::1` only, never wildcard (`threat-model-and-trust-boundaries.md` "Loopback Interface defenses").

### 2.4 Descriptor security

✅ Descriptor requirements: atomic write (temp + rename), owner-only mode/ACL, PID/start-time metadata, rotation on restart, safe removal of stale descriptors (`threat-model-and-trust-boundaries.md`).

✅ **Windows ACL — fixed mechanism and exact ACE set (rework #2, replaces the conflicting "only current user but also SYSTEM/Administrators" wording)**: `os.chmod(…, 0o600)` on Windows only toggles the read-only bit and is not an ACL mechanism. The pinned mechanism applies and verifies an **explicit DACL** with `icacls` (a Windows system tool, invoked as a controlled argv subprocess — never a shell string):

- **The exact ACE set is: exactly one grant ACE for the current user (resolved user SID) with `(F)` full control; nothing else.** Application: `icacls <path> /inheritance:r /grant:r <user-sid>:(F)`; the `(F)` grant is the only ACE the operation creates, and `/inheritance:r` removes all inherited ACEs;
- **Verification**: `icacls <path>` output is parsed and must show **only** the current-user SID with `(F)`; any other subject — including `Everyone` (`*S-1-1-0`), `BUILTIN\Users` (`*S-1-5-32-545`), `SYSTEM` (`*S-1-5-18`), or `BUILTIN\Administrators` (`*S-1-5-32-544`) — appearing in the descriptor's DACL fails verification. There is **no** "allowed extra SYSTEM/Administrators ACE" in the descriptor DACL;
- **Residual limit (host-admin boundary, documented)**: verification covers the descriptor DACL only. A local administrator or SYSTEM can still access the file through host-admin mechanisms outside the DACL (take-ownership, backup semantics, direct storage access); the threat model's v1 boundary is "prevent accidental cross-user access" and explicitly does not defend against a malicious host administrator (`threat-model-and-trust-boundaries.md`). This is stated as a boundary outside the DACL, not as permitted ACEs inside it;
- **Negative test**: fixtures with an `Everyone:(R)` ACE or a `SYSTEM:(F)` ACE are rejected by the verifier.

### 2.5 Fake command exactly-once and restart matrix

✅ Requirement (`slices/README.md` 00-05 demonstration): "a real local Hermes Gateway delivers one authenticated fake command exactly once; killing/restarting either process does not forge or lose an acknowledged result."

✅ **Receipt store — fixed (rework #1, decision D4)**: stdlib `sqlite3` in a disposable state-root file; it survives restart (required by the crash matrix), requires no new dependency, and carries an explicit retain-or-delete disposition. JSON atomic-file and in-memory stores are rejected (the latter fails the restart matrix).

✅ **Dual-process restart matrix — fixed (rework #1, three crash points)**: (A) crash before persistence → no receipt row, no ack; retry with the same `command_id` processes afresh with exactly one receipt and one effect; (B) crash after persistence but before the response → retry returns the original receipt (dedup), no second effect; (C) crash after the response → shim holds the receipt and does not resend; any transport retry still dedups to the original receipt. Hermes restart alone: the shim re-reads the existing descriptor and token (no rotation, no rewrite). Stale-descriptor cleanup follows the start-identity algorithm in §2.2; a forged receipt (not matching the persisted row) is rejected.

## 3. Dependency and isolation decisions

### 3.1 The binding rule

✅ `[project].dependencies` is empty (Base `pyproject.toml`); all current dependencies are dev/CI-only under ADR-0026 (contract toolchain) and ADR-0027 (00-04 spike deps). The runtime dependency rule in `docs/development/ci-and-testing.md` requires an explicit installation-and-isolation design before any runtime dependency; ADR-0027 explicitly defers "any future path that moves these dependencies into an isolated managed runtime" to "a later, separately human-approved ADR and Slice".

### 3.2 Accepted authorization and boundary

ADR-0022 and `docs/design/technology-stack.md` already **accept** FastAPI + Uvicorn as the v1 loopback stack. Accepting a design is not the same as authorizing a dependency: the runtime dependency rule in `ci-and-testing.md` requires an explicit installation-and-isolation design before any runtime dependency, and ADR-0026/0027 kept every new package dev-only while explicitly reserving runtime adoption for a later ADR. Therefore **FastAPI/Uvicorn is the only sanctioned loopback server choice, and it may run only inside the isolated Managed Runtime**. A stdlib `http.server` spike is **not** an equivalent default option and must not be used to bypass ADR-0022.

**D1 ? accepted human authorization.** The human accepted the exact ADR-0028 decision. The READY planning package records `docs/adr/0028-authorize-fastapi-uvicorn-in-managed-runtime.md` with frontmatter `status: accepted`, includes `ADR-0028` in the Slice Contract binding set, and verifies both before Executor dispatch. FastAPI/Uvicorn and the declared local `hermes-pipeline==0.1.0` package remain confined to the independent Managed Runtime; root `[project].dependencies` stays empty, Hermes never imports those dependencies, and the Executor never edits ADRs.

### 3.3 Accepted ADR-0028

ADR-0028 is the accepted record of the D1 decision: FastAPI/Uvicorn and the declared local `hermes-pipeline==0.1.0` package are authorized only through the dedicated `runtime-env/` project and its committed lock, materialized beneath `<state-root>/runtimes/<version>/`. The Hermes-loaded Shim remains standard-library/Hermes-guaranteed and never imports those packages; the root dependency set and root lock remain unchanged. Provisioning uses a controlled argv and a fixture-built child environment, while later probes run offline. The authoritative text is `docs/adr/0028-authorize-fastapi-uvicorn-in-managed-runtime.md`; this research report does not duplicate a mutable ADR.

### 3.4 Isolation mechanism and runtime locking topology (fixed — executable design)

- (b1) **Fixed**: a dedicated runtime project at repository root `runtime-env/` with its own `pyproject.toml` and committed `runtime-env/uv.lock` (the **lock source** for FastAPI/Uvicorn, `hermes-pipeline==0.1.0`, and all transitive packages). The explicit root package dependency is resolved by `[tool.uv.sources] hermes-pipeline = { path = "..", editable = false }`. A cross-platform harness uses controlled argv `[uv, "sync", "--frozen", "--project", "<repo>/runtime-env"]` and a fixture-built `UV_PROJECT_ENVIRONMENT=<fresh-state-root>/runtimes/<version>`; it proves interpreter and `sys.prefix` are the target, never `runtime-env/.venv`. The root project `[project].dependencies` stays empty; the root `uv.lock` is untouched. Implementation of these runtime-project paths is authorized by accepted ADR-0028.
- (b2) `pip install --target` directory + `PYTHONPATH` isolation — rejected (no lockfile, weak reproducibility).
- (b3) system interpreter + global packages — rejected (violates ADR-0020).
- Clean-checkout acceptance commands (bound as verification commands): `runtime-provision`, `runtime-provision-offline`, and `runtime-selfcheck` invoke the harness under `tests/spike/runtime/test_runtime_provision.py`; it owns the exact controlled `uv sync` child argv, target environment, state-root interpreter proof, and secret-canary absence. All three are required acceptance commands under accepted ADR-0028.

### 3.5 Reproducible Hermes provision for CI (rework #1 — contract-pinned)

- **Source**: `https://github.com/NousResearch/hermes-agent`, checked out at the exact release commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb` (tag `v2026.8.3`); the checkout SHA is recorded as evidence (never a branch name).
- **Hermes' own frozen lock**: the Hermes repository carries its own `uv.lock` (verified present in the install checkout); the provision step runs `uv sync --frozen` **inside the Hermes checkout** into an **independent Hermes test environment** (a directory outside this repository's `.venv`, e.g. `<runner>/hermes-env/`). The project's own dev environment never contains Hermes.
- **Network cutoff point**: network is allowed only through (1) checkout of this repository, (2) clone of the pinned Hermes commit, (3) the Hermes environment build, and (4) first frozen `runtime-env/` materialization into a fixture-owned fresh state root. After that bootstrap stage, every probe and the second runtime materialization runs offline.
- **Child-environment authority**: every provision, runtime, and Hermes-probe child begins with `{}`, never a copy of `os.environ`. The fixture supplies only resolved executable/system essentials (`PATH`, platform-required `SystemRoot`/`ComSpec` or `HOME`, test-owned temp/cache), `PYTHONDONTWRITEBYTECODE=1`, and its role-specific state-root, `UV_PROJECT_ENVIRONMENT`, `HERMES_HOME`, `HERMES_PIPELINE_PROBE_HERMES`, and `HERMES_PIPELINE_CANDIDATE_SHA` values. An unknown secret canary is absent from every child and bounded report.
- **Offline probe invocation**: probes locate the Hermes environment through an explicit environment variable (e.g. `HERMES_PIPELINE_PROBE_HERMES=<path>`); all subprocess invocations use controlled argv arrays (`[<hermes-python>, "-m", "hermes_cli", …]`), never shell strings. `uv run --offline pytest` does **not** assume Hermes exists in the project dev environment: the probe suites skip with a clear reason when `HERMES_PIPELINE_PROBE_HERMES` is absent, and fail (not skip) when the variable is set but the environment is broken. In required CI the variable is always set.
- **Workflow governance (fixed technical scope of this Slice, not a separate human decision)**: the existing `--check-workflows` checker covers exactly two workflows (`documentation-contracts.yml` and `python-quality.yml` — verified in `scripts/check_documentation.py:604-752`) and therefore does **not** cover a new `hermes-integration.yml`; that gap is acknowledged, not papered over. The READY revision extends `scripts/check_documentation.py` with a `check_hermes_integration_workflow` rule set — strict YAML-subset parse; `on:` exactly push/pull_request; `permissions: {contents: read}`; no `secrets:` context; job matrix covers `ubuntu-latest` and `windows-latest`; pinned action versions; the exact offline probe command inventory of the probe job; a network-cutoff boundary comment marker — plus positive and negative workflow fixtures under `scripts/fixtures/workflows/`, and two new verification commands (`workflow-policy-hermes` positive, `workflow-policy-hermes-negative` fixtures). The two existing workflows and their checkers are **not** modified. This is in-Slice fixed scope: the READY permitted paths include `scripts/check_documentation.py` and `scripts/fixtures/workflows/`.

### 3.6 Candidate-identity binding for the source install (fixed — rework #2)

`hermes plugins install file://<fixture> --enable` clones the **default HEAD** of the fixture (a `--depth 1` clone; `plugins_cmd.py:450-492`), so the fixture's default branch must be pinned to the exact workflow Candidate SHA. The integration workflow derives `HERMES_PIPELINE_CANDIDATE_SHA` as `github.sha` for `push` and `github.event.pull_request.head.sha` for `pull_request`, then checks out that exact SHA before the fixture begins. Fixed CI steps (all Git argv controlled, writes confined to the temporary fixture directory, the repository's own Git state untouched):

1. `git clone --no-checkout <repo-path> <fixture>` (read-only source access);
2. assert repository `git rev-parse HEAD` equals `HERMES_PIPELINE_CANDIDATE_SHA`, then `git -C <fixture> checkout -B main <HERMES_PIPELINE_CANDIDATE_SHA>` — the fixture's `main` branch and default HEAD are explicitly moved to the Candidate SHA;
3. assertions before install: `git -C <fixture> rev-parse HEAD` equals `HERMES_PIPELINE_CANDIDATE_SHA` and `git -C <fixture> symbolic-ref HEAD` equals `refs/heads/main` (branch names are never evidence; the SHA assertion is);
4. `hermes plugins install file://<fixture> --enable` into the isolated `HERMES_HOME`;
5. assertion after install: `git -C <HERMES_HOME>/plugins/hermes-software-pipeline rev-parse HEAD` equals `HERMES_PIPELINE_CANDIDATE_SHA` (the installed depth-1 clone retains its `.git`), and `HEAD^{tree}` equals the checked-out Candidate tree.

Negative fixture: a fixture whose `main` points at a non-Candidate SHA (for example the planning Base) must fail the post-install HEAD assertion, proving the install binds to the fixture default HEAD and not to any other repository state. The same fixture steps apply on both platforms.

## 4. Parallel implementation analysis vs Slice 00-04

### 4.1 Facts at planning time (historical snapshot, 2026-08-10)

✅ `origin/main` = `e238ecf1a5b4d091fb2b5c1c0497a41ea250b5de` (observed 2026-08-10). Local `main` (`4a13cfd`) was ahead by two **unpushed planning-revision commits** (`52562b5`, `4a13cfd`) — **not** a Candidate — and the 00-04 execution worktree was on `feature/slice-00-04-domain-and-persistence-spikes` at `1e1b7ad` (observation only). **Machine prerequisite (rework #2)**: `slice-00-04` is a predecessor in the machine contract; READY requires Git Custodian/integration evidence that 00-04 is complete, then re-binds the Base, manifest summaries, and the path-independence proof to the then-current `origin/main`. The old baseline never satisfies this condition by itself.

### 4.2 Path ownership

| Path group | 00-04 (execution state, non-binding reference) | 00-05 (planned) | Parallel? |
| --- | --- | --- | --- |
| root `pyproject.toml` / root `uv.lock` | owns (dev group additions) | always untouched; Accepted ADR-0028 permits the separate `runtime-env/pyproject.toml` and `runtime-env/uv.lock` | ✅ no root-file overlap |
| `.python-version` | owns (rev-7 pin) | untouched | ✅ no overlap |
| `.github/workflows/python-quality.yml` | owns (rev-7 pin) | untouched; 00-05 adds a **new** `hermes-integration.yml` workflow under fixed in-Slice governance | ✅ file-disjoint (but shared CI trigger surface) |
| `scripts/check_documentation.py` | owns (rev-7 constants) | READY fixed scope extends only `check_hermes_integration_workflow` plus its fixtures; existing checker behavior remains unchanged | ✅ after 00-04 integration; no separate approval |
| `tests/` incl. `tests/conftest.py`, fixtures | owns (spike suites under `tests/`) | needs new suites + shared fixtures | ❌ same directory, shared fixture surface |
| `src/hermes_pipeline/domain\|controller\|persistence\|stage_executor` | owns | untouched | ✅ |
| `src/hermes_pipeline/transport/` | closed (00-04 contract forbids) | owns (fake runtime spike incl. the `python -m hermes_pipeline.transport` entry) | ✅ |
| `src/hermes_pipeline/cli/` | closed (00-04 forbids) | **not writable by 00-05** (rework #1) | ✅ |
| `hermes_shim/` (new root dir) + root `plugin.yaml` / `__init__.py` | does not exist at Base; 00-04 forbids | owns (shim; root `__init__.py` imports only `hermes_shim`) | ✅ |
| `docs/development/compatibility-targets.md` | owns | needs entries | ❌ both write it |
| `docs/roadmap/…/slices/README.md` | 00-04 planning already updated it | this planning change updates it | ✅ (planning-only) |

### 4.3 Verdict

**READY serial-execution verdict.** Slice 00-04 is integrated at `46798d86a2e48551a3a634e93d1e4dfe5cbf8786` (PR #9), so its predecessor gate and the former planning-time rebind condition are satisfied. Slice 00-05 still executes serially for the shared `tests/` and `docs/development/compatibility-targets.md` paths. The READY contract and manifest bind the exact Base; any later target drift requires re-verification and a refreshed path-independence proof.

## 5. Decision table (D1 accepted; remaining decisions fixed)

| ID | Decision | Status | Fixed value / options |
| --- | --- | --- | --- |
| D1 | Authorize FastAPI/Uvicorn and declared local `hermes-pipeline==0.1.0` only inside the independent Managed Runtime | **ACCEPTED** | ADR-0028 is recorded as accepted, is binding in the READY contract, confines dependencies to `runtime-env/`, keeps root dependencies/lock unchanged, and requires no second human approval |
| D2 | Runtime installation/isolation mechanism | Fixed (Codex clarification, executable) | Dedicated runtime project `runtime-env/` with its own `pyproject.toml` + `uv.lock`, explicit `fastapi`/`uvicorn`/`hermes-pipeline==0.1.0` dependencies, and path source; the cross-platform harness runs exact sync argv with a fresh state-root target and proves target interpreter/sys.prefix; root `[project].dependencies` stays empty (§3.4) |
| D3 | Windows descriptor ACL | Fixed (rework #2) | Exact ACE set = exactly one grant ACE for the current user SID with (F); `/inheritance:r`; verification rejects any other subject incl. SYSTEM/Administrators/Everyone/Users in the descriptor DACL; residual host-admin boundary documented outside the DACL (§2.4) |
| D4 | Fake receipt store | Fixed | stdlib `sqlite3` in the disposable state root; JSON/memory rejected |
| D5 | Lifecycle state root | Fixed | Derived from `HERMES_HOME` (`<HERMES_HOME>/software-pipeline/`); test isolation via `HERMES_HOME` itself |
| D6 | Hermes CI provision | Fixed | Release tag `v2026.8.3` = commit `3c27eb6`; Hermes' own `uv.lock`; independent `hermes-env`; first runtime materialization completes dependency bootstrap, then cutoff; closed child environment allow-list; `HERMES_PIPELINE_PROBE_HERMES`; evidence = `hermes --version`, Candidate checkout, target interpreter, and canary absence (§3.5) |
| D7 | Interception probe topology | Fixed | Real Hermes process + real plugin load + synthetic `MessageEvent` through `GatewayRunner._handle_message` (fixture-based, offline), plus the PluginManager load/registration probe (§1.10); real Feishu connection rejected |
| — | Descriptor/protocol versioning | Fixed (rework #2, not a human option) | Versioned constants + golden JSON fixtures inside the spike; committed JSON Schema toolchain path is out of scope for this Slice |
| — | Workflow governance for `hermes-integration.yml` | Fixed technical scope (rework #2, not a separate human decision) | READY extends `scripts/check_documentation.py` with `check_hermes_integration_workflow` plus `scripts/fixtures/workflows/` positive/negative fixtures and the `workflow-policy-hermes` / `workflow-policy-hermes-negative` verification commands; existing two workflows and their checkers unchanged; no checker-coverage claim before implementation (§3.5) |

## 6. Risks, assumptions, and open items

| ID | Item | Status |
| --- | --- | --- |
| R1 | `pre_gateway_dispatch` hook exceptions are fail-open; a probe event must be skipped unconditionally, never forwarded to Prod Main | ⚠️ design must guarantee no-raise + unconditional skip for the probe namespace; negative tests required |
| R2 | Real Hermes CI installation at the pinned commit may be heavy (Hermes ships JS tooling, optional SDKs); install cost, disk, and time must be bounded and evidenced | ⚠️ contract sets explicit CI bounds |
| R3 | `GatewayRunner._handle_message` in-process driving requires Hermes-internal attribute surface; Hermes' own tests are the reference seam | ⚠️ probe design must be pinned in the contract |
| R4 | Windows ACL semantics for the descriptor; stdlib offers no DACL API | ❓ decision D3 |
| R5 | A gateway run with no platforms and no credentials must start offline; if it cannot, the interception probe needs an alternative harness | ⚠️ must be probed; fallback documented |
| R6 | Version drift between release `3c27eb6` and local install `be54f28` | ⚠️ pin the release; record drift if observed |
| R7 | The fake runtime must not inherit Hermes secrets/environment: environment must start from an allow-list, inherited secret variables removed | ⚠️ negative tests with secret canaries required (`threat-model-and-trust-boundaries.md` "Process and command defenses") |
| R8 | Descriptor path escape: descriptor must be resolved only inside the validated state root; symlink/junction/reparse-point escapes rejected | ⚠️ negative tests required (XSEC-01) |
| R9 | Port collision and stale-socket cleanup on both platforms | ✅ fixed: ≤3 fresh-port attempts, then `DEPENDENCY_UNAVAILABLE`; start-identity algorithm in §2.2 |
| R10 | A later target drift invalidates the ready Base or shared-path proof | fixed at READY: 00-04 integrated at `46798d86a2e48551a3a634e93d1e4dfe5cbf8786`; later drift triggers re-verification and rebinding |
| R11 | The new hermes-integration.yml workflow is not governed by the existing workflow policy checker | ✅ fixed scope: READY extends `scripts/check_documentation.py` with the `check_hermes_integration_workflow` rule set plus fixtures and dedicated verification commands; existing two workflows unchanged; no coverage claim before implementation |
| R12 | The Hermes/runtime provision is not reproducible, its children inherit ambient authority, or the probe suites assume Hermes exists inside the project dev environment | ✅ fixed: pinned locks, independent environments, dependency-bootstrap cutoff, fixture-built child allow-lists/canary, and state-root harness; probe suites skip without `HERMES_PIPELINE_PROBE_HERMES` and fail when set but broken |
| R13 | The source-install fixture's default HEAD does not equal the exact workflow Candidate, so install evidence binds the wrong commit | ✅ fixed: event-derived checkout SHA, fixture/installed SHA plus tree assertions, and a non-Candidate negative fixture (§3.6) |
| R14 | Historical 2026-08-10 observations are mistaken for current state | fixed: they remain historical; current READY evidence is Git Custodian verification of `46798d86a2e48551a3a634e93d1e4dfe5cbf8786` |

## 7. Evidence inventory

| Evidence | Source | Verified |
| --- | --- | --- |
| `hermes --version` → `v0.20.0` (2026.8.3), install dir, Python 3.11.15 | local execution, 2026-08-10 | ✅ |
| Install-directory Git HEAD `be54f28b16906f4153f618eeb4369495667af7ce`, remote `NousResearch/hermes-agent` | `git -C …/hermes-agent` | ✅ |
| Release tag `v2026.8.3` = commit `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`, dated 2026-08-03 | GitHub release page, fetched 2026-08-10 | ✅ |
| Plugin system: `hermes_cli/plugins.py` (manifest model, load, hooks, gating, `LoadedPlugin` registration records) | install dir, HEAD `be54f28` | ✅ |
| Install/update/uninstall: `hermes_cli/plugins_cmd.py` (`plugins list` = activation state only) | install dir, HEAD `be54f28` | ✅ |
| `pre_gateway_dispatch` fire site: `gateway/run.py:14277-14318` | install dir, HEAD `be54f28` | ✅ |
| Feishu synthetic `/card`: `plugins/platforms/feishu/adapter.py:3042-3095`, `plugin.yaml` | install dir, HEAD `be54f28` | ✅ |
| Official plugin guide: `website/docs/developer-guide/plugins/index.md` (in-tree) | install dir, HEAD `be54f28` | ✅ |
| Upstream docs URL: `https://github.com/NousResearch/hermes-agent/blob/<commit>/website/docs/developer-guide/plugins/index.md` | upstream | ✅ (same content at release pin to be confirmed at execution) |
| Hermes own hook tests: `tests/gateway/test_pre_gateway_dispatch.py` | install dir, HEAD `be54f28` | ✅ |
| `HERMES_HOME` resolution: `hermes_constants.py:78-140` | install dir, HEAD `be54f28` | ✅ |
| Workflow checker coverage: `scripts/check_documentation.py:604-752` covers exactly `documentation-contracts.yml` and `python-quality.yml` | repo Base `e238ecf` | ✅ |
| Binding design: ADR-0019/0020/0022/0025, `technology-stack.md`, `system-and-module-design.md`, `configuration-and-lifecycle.md`, `data-and-api-contracts.md`, `threat-model-and-trust-boundaries.md`, `ci-and-testing.md`, `compatibility-targets.md` | this repository at Base `e238ecf` | ✅ |
| 00-04 planning revisions `52562b5`/`4a13cfd` (unpushed, **not** a Candidate) and execution branch `feature/slice-00-04-domain-and-persistence-spikes` at `1e1b7ad` — **historical snapshot 2026-08-10, not current state**; READY re-verifies via Git Custodian/integration evidence | local `main` and `git worktree list`, 2026-08-10 | ✅ (snapshot only) |
