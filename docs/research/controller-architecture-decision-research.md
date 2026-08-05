# Controller 架构决策调研

- 状态：供架构审查
- 日期：2026-08-05
- 范围：Pipeline Controller 的持久化、安全、交付、重试与生命周期协议
- 非范围：本轮不选择数据库、消息队列、Web 框架或部署拓扑

## 1. 结论摘要

本轮建议直接敲定以下原则：

1. **业务 Domain Event Log 是 Pipeline 唯一事实源。** `Pipeline`、`Stage`、审批、租约、Artifact、远程交付状态都是可重建投影。
2. **采用 Inbox + Transactional Outbox + 乐观并发控制。** 外部效果按“至少一次投递 + 幂等消费”设计，不宣称端到端 exactly-once。
3. **执行所有权使用 Lease，并用单调递增的 Fencing Token 阻断旧 Worker。** 只有持有当前 token 的 Attempt Execution 才能提交结果。
4. **LangGraph 定位为 Agent 编排执行层，不是业务状态机的权威。** Checkpoint 是可丢弃、可重建的执行游标；LangGraph 节点只能通过 Controller Command 请求业务变化。
5. **Sandbox 按能力边界划分，而不是按角色名称机械划分。** 默认拒绝；显式授予文件、网络、凭据、进程、浏览器和资源能力。
6. **交付物由不可变 `ArtifactManifest` 描述。** 状态事件只引用 manifest ID/digest，不内嵌大文件，也不信任 Agent 自报路径。
7. **远程 Git 写操作由独立 Remote Delivery Adapter 承担。** Agent 与 Controller 核心都不持有 merge 权限；Adapter 可以推送受控分支、创建/更新 MR/PR、发布检查，但不能批准或合并。
8. **拆分 `planning_base_sha` 与 `integration_base_sha`。** 目标分支普通漂移不重开 PRD/设计；生成新的集成候选并重跑受影响的自动门禁。Merge Queue 产生的新 SHA 必须重新验证。
9. **方案基线审批以 Controller 为权威，最终合入审批以 Git Host 为权威。** 飞书是交互和通知通道，不是 MR/PR 合入事实源。
10. **失败按语义分类。** 基础设施失败可自动重试；产品/测试失败形成新 Stage Attempt；输入、权限、冲突和策略失败停止并等待处理。
11. **Pause、Resume、Cancel、Timeout、Reassign、Recovery、Cleanup 都是显式 Command/Event。** 不允许通过人工改表、删除目录或重启进程隐式改变状态。

## 2. 调研依据

### 2.1 LangGraph

LangGraph 的 checkpointer 会按 graph step 保存 thread checkpoint，支持 fault tolerance、interrupt、pending writes、历史回放和 state update。回放旧 checkpoint 时，checkpoint 之后的节点会重新执行；`update_state` 会创建新的 checkpoint；Store 又是独立于 thread checkpoint 的跨线程 JSON memory。这说明 checkpoint/state history 的目标是**执行恢复与 Agent memory**，并不天然等价于不可变的业务审计账本。[Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

`interrupt()` 会保存状态并等待 `Command(resume=...)`，但恢复时从包含 interrupt 的 node 开头重新执行；官方明确要求 interrupt 前的 side effect 必须幂等。子图中的 interrupt 还会让父节点和子图节点都从头重跑。[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)

Functional API 通过 `@task` 持久化任务结果来避免不必要的重复计算，但仍要求 API 调用放入 task 且本身具有幂等性；恢复必须保持相同的任务调用顺序。[Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)

`Command` 可以更新 graph state、动态 goto、跨 subgraph 路由和 resume interrupt；这些是 graph 内部控制流能力，不提供项目授权、租约 fencing、远程 Git 审批权威或 transactional outbox 语义。[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)

本地固定源码进一步表明：

- `Durability` 有 `sync/async/exit` 三种模式；`async` 可在下一 step 执行时异步持久化，`exit` 只在 graph 退出时持久化，不能等同于每次业务状态转移的同步提交：`reference/langgraph/libs/langgraph/langgraph/types.py`。
- `StateSnapshot`、`Command`、`Interrupt` 和 task stream 都属于 graph 执行模型：`reference/langgraph/libs/langgraph/langgraph/types.py`。
- `BaseCheckpointSaver` 以 `thread_id/checkpoint_id` 保存 checkpoint 和 pending writes，并允许 list/history：`reference/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py`。
- Postgres checkpointer 的 schema 分开保存 checkpoint 与 task writes：`reference/langgraph/libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py`。

因此，LangGraph 可承担长流程编排，但不能在不增加业务协议的情况下替代 Controller。

### 2.2 Temporal 对照

Temporal 的强保证来自服务端 Event History：Workflow replay 生成的 commands 会与既存历史核对，失败后从最后记录的 event 恢复；外部非确定性操作必须放入 Activity。[Workflow Execution](https://docs.temporal.io/workflow-execution)

Temporal 默认重试 Activity，而不默认重试整个 Workflow；官方区分 transient/intermittent/permanent failure，并建议对 Activity 设置 retry policy、timeout 和 non-retryable errors。[Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies)

本项目暂不选 Temporal，但借用两条成熟约束：

- 编排决策必须可重放，副作用必须移到受控执行边界；
- 重试具体 Activity/Execution，不盲目重启整个 Pipeline。

### 2.3 OpenHands Software Agent SDK

OpenHands 的本地固定源码提供了三个可参考的实现边界：

- `EventLog` 以 append 模式保存事件、拒绝重复 event ID，并用锁保护并发写；源码同时警告本地文件锁在 NFS/网络文件系统上不可靠：`reference/software-agent-sdk/openhands-sdk/openhands/sdk/conversation/event_store.py`。
- `ConversationLease` 保存 owner、过期时间和单调递增 generation；takeover 后旧 owner 在 guarded write 时会被阻断：`reference/software-agent-sdk/openhands-agent-server/openhands/agent_server/conversation_lease.py`。
- 安全确认策略将 `AlwaysConfirm`、`NeverConfirm`、`ConfirmRisky` 建模为执行策略，而非依赖提示词：`reference/software-agent-sdk/openhands-sdk/openhands/sdk/security/confirmation_policy.py`。
- Git 会话工作区按 conversation 建立 worktree：`reference/software-agent-sdk/openhands-agent-server/openhands/agent_server/conversation_service.py`，并在仓库 `AGENTS.md` 中规定 `/tmp/conversation-worktrees/<conversation_id>/...`。

这些实现支持“事件 + lease generation + 执行策略”的方向，但文件 EventLog 与本地锁不适合作为本项目未来多实例部署的最终存储约束。

### 2.4 Codex 权限模型

Codex 本地固定源码将 read-only、workspace-write、danger-full-access 建模为不同 permission profile，并分别解析文件系统与网络策略：`reference/codex/codex-rs/core/src/config/permissions.rs`。工具审批又单独处理 shell、exec、apply patch 与网络策略修改：`reference/codex/codex-rs/core/src/tools/approvals.rs`。

这支持“操作系统/运行时强制能力边界 + 工具审批”模式；`AGENTS.md` 或 prompt 只能补充行为要求，不能替代 sandbox。

### 2.5 GitHub、GitLab 与飞书

GitHub protected branch 可强制 required reviews、required checks、Code Owners、dismiss stale approvals；Merge Queue 会对目标分支最新状态和队列中前序变更组成的新版本重新运行 required checks。[Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)

GitLab protected branch 明确区分直接 push 与通过 MR merge 的权限，并建议生产分支禁止直接 push；MR approval rules 和 Code Owners 决定合入资格。[Protected branches](https://docs.gitlab.com/user/project/repository/branches/protected/)、[MR approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)

飞书卡片支持按钮回调，但服务端必须在 3 秒内响应；回调来源可以用签名或 Verification Token 校验。[飞书回调](https://open.feishu.cn/document/event-subscription-guide/callback-subscription/receive-and-handle-callbacks?lang=zh-CN) 这使飞书适合作为审批交互入口，但卡片投递、更新或回调超时不应改变 Git Host 对最终合入的权威性。

## 3. 敲定方案：业务持久化协议

### 3.1 唯一事实源

`Pipeline Event Log` 是唯一业务事实源，事件 append-only，按每条 Pipeline 的 `revision` 严格递增。

同一事务必须完成：

1. 验证并登记 Inbox Command；
2. 验证 `expected_revision` 和授权；
3. 追加一个或多个 Domain Event；
4. 更新 Pipeline/Stage/Approval/Lease 等查询投影；
5. 写入待投递 Outbox Message。

投影损坏时从 Event Log 重建；Outbox 丢失时从事件补发。禁止只更新投影、只修改 LangGraph state 或只发送外部消息。

### 3.2 Command Envelope

所有状态变化只能由 Command 请求。最小 envelope：

```yaml
command_id: uuid
command_type: SubmitStageResult
pipeline_id: PIPE-0042
project_id: PROJ-001
actor:
  principal_id: ...
  principal_type: human | service | agent
expected_revision: 37
correlation_id: ...
causation_id: ...
issued_at: ...
schema_version: 1
payload: {}
```

约束：

- `command_id` 全局幂等；
- `expected_revision` 防止基于陈旧状态推进；
- actor 身份来自可信 adapter/session，不接受 LLM 自报；
- Agent Result 必须额外携带 `stage_attempt_id`、`execution_id`、`fencing_token`、输入 SHA 和 `artifact_manifest_id`；
- 相同 `command_id` + 相同 payload 返回原结果；相同 ID + 不同 payload 是安全错误。

### 3.3 Event Envelope

```yaml
event_id: uuid
event_type: StageResultAccepted
pipeline_id: PIPE-0042
revision: 38
occurred_at: ...
actor: {}
correlation_id: ...
causation_id: ...
schema_version: 1
payload: {}
```

事件不可更新或删除。隐私删除通过 payload redaction/key destruction 与新的审计事件处理，不能篡改状态历史。Event schema 必须支持 upcaster；未知 event version 必须 fail closed。

### 3.4 Inbox、Outbox 与投递语义

- Inbox 对每个 `source + command_id` 建唯一约束；
- Outbox 记录 destination、message type、payload、idempotency key、attempt、next retry time；
- Dispatcher 只发送已提交事务中的 Outbox；
- 外部 Adapter 以 idempotency key 去重；
- 投递成功/失败再通过 Command 写回 Domain Event；
- 不对跨数据库、飞书、Git Host、CLI 进程宣称 exactly-once；契约是 at-least-once delivery + idempotent effect。

### 3.5 Lease 与 Fencing

每个运行中的 Stage Attempt 只有一个 active Execution Lease：

```yaml
resource: stage_attempt_id
owner_execution_id: ...
fencing_token: 12
leased_until: ...
heartbeat_at: ...
```

- claim/takeover 原子递增 `fencing_token`；
- 心跳只能续当前 token；
- 所有结果、Artifact finalize、Candidate 提交都必须校验 token；
- 过期 token 的迟到结果保存为 `LateResultRejected` 证据，但不能推进状态；
- Lease 只解决执行所有权，不等于业务授权。

## 4. 敲定方案：LangGraph 的角色

### 4.1 推荐定位

LangGraph 是 **Agent Stage Orchestrator**：

- 组织 Codex/OpenCode 的模型调用、工具循环与子任务；
- 保存 Stage Execution 的对话/graph state；
- 在需要人或 Controller 决策时 interrupt；
- 对单个 Agent execution 做 checkpoint、有限 retry、streaming 和可观测性；
- Stage/Execution 默认使用新的 thread；不要把整条长期 Pipeline 的所有角色塞进共享 thread。

Controller 是 **Business Process Authority**：

- 接收 Command、执行业务状态机、授权与 revision 校验；
- 发租约和 fencing token；
- 决定 Stage/Attempt 创建、接受或拒绝 Agent 结果；
- 管理 Artifact、Git delivery 和人工审批。

### 4.2 避免双事实源

LangGraph node 不得直接更新业务表。它只能：

1. 读取 Controller 提供的不可变 `ExecutionInput`;
2. 执行 Agent 工作；
3. 通过具备 idempotency key 的 Controller API 提交 Command；
4. 将 Controller 返回的 `accepted_event_id/revision` 记入 checkpoint。

如果 Command 已被 Controller 接受、但 LangGraph 来不及保存 checkpoint 就崩溃，node replay 会用同一 `command_id` 重提；Inbox 返回原结果。因此无需让 Controller 与 LangGraph checkpointer 跨库事务提交。

LangGraph checkpoint 可以丢弃并从 Controller 的 ExecutionInput 重新启动；Domain Event Log 不可以。任何授权、审批、Stage status、lease、Candidate SHA 或 merge status 查询都以 Controller projection 为准。

### 4.3 LangGraph 使用约束

- 生产使用 durable checkpointer，关键步骤使用同步持久化语义；`exit` 不得用于包含外部副作用的长任务；
- 外部 API、CLI 启动和 Artifact finalize 包装成 task/node，并具备稳定 idempotency key；
- interrupt 前后的副作用都必须幂等；
- 不把大日志、源码树、截图二进制放入 graph state；
- Store 只用于 Agent memory/检索缓存，不用于业务授权或 Pipeline 状态；
- graph/subgraph 版本写入 Execution metadata；升级后无法安全 replay 时启动新 Execution，而不是强行恢复旧 checkpoint；
- `Command(goto/update)` 只能表达 graph 内路由，不能绕过 Controller transition。

## 5. 敲定方案：Stage Capability Sandbox

Worktree 是版本隔离，不是安全沙箱。每次 Execution 必须绑定不可变 Capability Profile：

| Stage | 文件 | 进程/工具 | 网络 | 凭据 | 写入结果 |
|---|---|---|---|---|---|
| PRD | `planning_base_sha` 只读快照 | 搜索/读取；无 Git 写 | 默认拒绝；可选文档域 allowlist | 无仓库写凭据 | Artifact staging |
| Architecture | 同上 | 搜索、静态分析、必要的只读命令 | 同上 | 无仓库写凭据 | Artifact staging |
| Development | 单 Pipeline 可写 worktree | build/test/dev tools；Git porcelain 写命令禁止 | 依赖源与项目服务 allowlist | 短期、按服务注入；禁止 prod secret | worktree + Artifact staging |
| E2E | `candidate_sha` 干净临时 sandbox；源码只读 | app runner + Chrome DevTools MCP | 仅测试环境域名/loopback | 短期测试账号 | 报告、截图、trace |
| Acceptance | `candidate_sha` 或 integration candidate 只读 | review、build/test；无源码修改 | 默认拒绝或测试依赖 allowlist | 无交付凭据 | 验收报告 |
| Remote Delivery | 无 Agent shell | 固定 Git/API 操作 | 仅 Git Host | 最小 scope app/token | 远程分支/MR/check |

共同规则：

- deny by default；Capability Profile 由 Controller 生成，Agent 不得扩权；
- 凭据通过 broker 按 Execution 动态注入，短 TTL，日志自动脱敏；
- 禁止访问 Hermes 主目录、用户工作副本、其他 Pipeline、宿主 Docker socket、SSH agent 和云 metadata；
- 限制 CPU、内存、磁盘、进程数、运行时长和输出量；
- E2E 禁止访问生产环境，测试账号和数据可回收；
- profile hash 写入 Execution 和 ArtifactManifest，便于复现与审计；
- Agent 内部 confirmation policy 是第二层防护，不能代替 OS/container sandbox。

## 6. 敲定方案：ArtifactManifest

所有可推动状态的产物都必须先 finalize 为不可变 manifest：

```yaml
manifest_id: artm_...
schema_version: 1
artifact_type: PRD | DESIGN | TEST_PLAN | IMPLEMENTATION_REPORT | E2E_REPORT | ACCEPTANCE_REPORT
pipeline_id: PIPE-0042
stage_attempt_id: ...
producer_execution_id: ...
fencing_token: 12
inputs:
  planning_base_sha: ...
  candidate_sha: ...
  integration_base_sha: ...
items:
  - logical_name: report
    uri: artifact://sha256/...
    sha256: ...
    media_type: text/markdown
    size: 1234
producer:
  role: ...
  adapter_version: ...
  model: ...
  prompt_policy_digest: ...
capability_profile_digest: ...
created_at: ...
classification: internal
```

规则：

- 对象 content-addressed，manifest 自身也计算 digest；
- manifest finalize 后不可改变；“最新版”只是可变 pointer；
- Controller 只信任已校验 digest、归属、fencing token、schema 和必要 items 的 manifest；
- Agent 声称“测试通过”不是证据；必须有命令、退出码、环境信息和报告项；
- 日志、截图、trace 和二进制存 Artifact Store，Git 仓库只保留项目明确要求版本化的文档；
- retention、legal hold、redaction 分离；清理对象前先验证无有效 manifest 引用。

## 7. 敲定方案：Remote Delivery Adapter

Remote Delivery Adapter 是唯一远程 Git 写边界：

- 可以创建/更新 Controller 命名的远程 topic branch；
- 可以创建/更新 MR/PR、发布 commit status/check、读取 mergeability、审批和 merge queue 状态；
- 不得 approve、dismiss review、修改保护规则、force push、删除非本 Pipeline 分支或 merge；
- 使用 GitHub App/GitLab project token 等最小范围凭据；每个 Project 单独授权；
- 所有请求带 `delivery_operation_id` 并可幂等恢复；
- Adapter 回调不直接改状态，只提交 Controller Command；
- Git Host webhook 和定期 reconciliation 双轨核对，防止 webhook 丢失。

## 8. 敲定方案：双基线与 Merge Queue

### 8.1 SHA 定义

- `planning_base_sha`：方案开始时冻结，PRD、Architecture、Development 的语义基线；
- `candidate_sha`：Controller 从 Development worktree 形成的候选；
- `integration_base_sha`：准备交付/验证时目标分支的最新权威 SHA；
- `integration_candidate_sha`：`candidate_sha` 与 `integration_base_sha` 合成的可验证结果；
- `merge_group_sha`：Git Host Merge Queue 生成的最终队列候选。

### 8.2 漂移处理

目标分支更新时：

1. 不修改 `planning_base_sha`，不默认重开 PRD/Architecture；
2. 生成新的 `integration_base_sha` 和 `integration_candidate_sha`；
3. 发生冲突则回 Development；
4. 无冲突则重跑 build、E2E、Codex acceptance 和项目 required checks；
5. 只有检测到需求/接口/安全假设发生实质变化，才创建 `BaselineImpactReview`，由人决定是否重开方案；
6. Merge Queue 产生 `merge_group_sha` 后，对该 SHA 重跑 Git Host required checks；此前 Candidate 的测试只能作为证据，不能代替 merge-group check。

最终人工审批绑定 Git Host 显示的最新 diff/head SHA。若 Git Host 因新 commit、merge base 变化或策略而撤销审批，Controller 必须同步回等待审批状态，不能沿用飞书中的旧按钮结果。

## 9. 敲定方案：审批权威

### 9.1 方案基线审批

Controller 是权威：

- 飞书卡片、Dashboard、CLI 都只是提交 `ApproveSolutionBaseline` Command 的 adapter；
- 回调必须验签、绑定可信 user ID、校验 Project role、approval request ID、revision、有效期和一次性 nonce；
- 3 秒内先返回接收结果，业务处理异步完成，再更新卡片；
- 飞书投递失败时可用 Dashboard/CLI 完成同一审批，不改变审批语义。

### 9.2 最终 MR/PR 合入审批

GitHub/GitLab 是权威：

- Controller 读取 protected branch、required reviews/checks、Code Owners、latest SHA 和 merge queue 状态；
- 飞书只显示深链接、摘要、提醒和“已查看”，不得创造一个与 Git Host 平行的最终批准；
- 实际 merge 由 Git Host 受保护分支策略与有权限的人执行；
- Pipeline 在观察到 Git Host merged event 并核对 merge commit 后才完成。

## 10. 敲定方案：Retry Taxonomy

区分两个层次：

- **Stage Attempt**：一次具有明确输入和期望产物的语义尝试；
- **Execution Attempt**：为完成同一 Stage Attempt 而进行的运行时执行。

| 失败类型 | 示例 | 处理 |
|---|---|---|
| Transport | webhook/飞书/Git API 超时、5xx | 同一 Outbox/operation 自动重投；不建新 Stage Attempt |
| Transient Infrastructure | Worker 崩溃、沙箱启动失败、临时网络故障 | 有限次数新 Execution Attempt；新 lease/token |
| Capacity/Quota | LLM quota、无可用 runner、磁盘不足 | 有界退避后 PAUSED/WAITING_CAPACITY，通知管理员 |
| Agent/Model | 模型超时、无有效结构化输出 | 有界新 Execution Attempt；保留前次证据 |
| Product/Verification | 单测、E2E、验收失败 | 不视为 infra retry；形成反馈 Artifact，回 Development 新 Stage Attempt |
| Deterministic Input | schema 错、缺文件、未知版本 | 不重试；BLOCKED_INPUT |
| Authorization/Policy | 权限不足、sandbox 扩权、secret policy | 不重试；BLOCKED_POLICY 并审计 |
| Integration Conflict | rebase/merge conflict、target deleted | 回 Development 或人工处理 |
| Unknown | 未分类异常 | 最多一次保守重试，然后 NEEDS_REVIEW |

所有自动重试必须有：

- max attempts、总 elapsed budget、指数退避与 jitter；
- 可观察的 RetryScheduled/Exhausted event；
- 稳定 idempotency key；
- 不得因重试覆盖原始日志或 Artifact；
- 不得自动重试人类拒绝、测试失败或不满足业务条件。

## 11. 敲定方案：生命周期与恢复

### 11.1 Pause/Resume

- `PausePipeline` 阻止新 dispatch，并向 active execution 发出 cooperative stop；
- 已经返回的结果进入 quarantine，待 resume 时重新校验，不自动推进；
- `ResumePipeline` 创建新 revision，按最新 projection 决定续租、重启 Execution 或重新验证；
- 人工审批等待不是 PAUSED，而是独立 `WAITING_APPROVAL`。

### 11.2 Cancel

- `CancelPipeline` 是终态请求：撤销 lease、凭据和待发任务，停止新外部效果；
- active process 先 cooperative cancel，超时再强制终止；
- 迟到结果只记录，不推进；
- 远程 branch/MR 默认保留并标记 cancelled，删除需独立、有权限的显式操作；
- 已合入的 Pipeline 不能 cancel，只能创建 revert/follow-up 流程。

### 11.3 Timeout

分别设置：

- dispatch timeout；
- start timeout；
- heartbeat/lease timeout；
- execution timeout；
- stage elapsed timeout；
- human approval reminder/escalation deadline；
- pipeline inactivity timeout。

Human deadline 默认只提醒和升级，不自动批准或拒绝。Execution timeout 按 retry taxonomy 处理。

### 11.4 Reassignment

- 只有没有有效 active lease 时才能更换 Agent executor；
- reassignment 递增 fencing token，并产生 `StageExecutionReassigned`；
- 人工审批人变更由有权限的 Project Administrator 操作并留事件；
- 已发生的批准不自动转移到另一个 approval scope；批准绑定 request、revision 与 artifact digest。

### 11.5 Recovery/Reconciliation

Controller 启动和周期任务执行：

1. 重发未完成 Outbox；
2. 回收过期 lease；
3. 核对 LangGraph execution/checkpoint 与 Controller execution projection；
4. 核对沙箱进程、worktree、Artifact staging；
5. 核对远程 branch/MR/check/merge queue；
6. 对不一致提交明确的 Recovery Command/Event；
7. 无法自动判断时进入 `NEEDS_RECOVERY_REVIEW`，不猜测成功。

恢复器不得直接改投影；它和其他调用者一样提交幂等 Command。

### 11.6 Cleanup

- 清理是独立可重试工作流，不与业务完成事务耦合；
- worktree、sandbox、临时凭据、Artifact staging、日志分别有 retention；
- 完成/取消后立即撤销凭据和停止进程，延迟删除取证数据；
- ArtifactManifest、Domain Event、审批和 remote delivery audit 按项目审计策略保留；
- 每个清理动作都有 resource ID 和 idempotency key；
- 清理失败不把已完成 Pipeline 改回失败，而进入 `CLEANUP_PENDING/FAILED` 运维状态。

## 12. 仍属于技术栈决策的内容

以下内容本轮故意不敲定：

- 业务 Event Log/Projection/Inbox/Outbox 的数据库产品；
- 是否使用独立消息队列；
- LangGraph checkpointer 的具体 backend；
- Controller API/Web 框架；
- Sandbox 使用容器、VM、Windows Sandbox 或远程执行平台；
- Artifact Store 产品；
- GitHub 与 GitLab adapter 的首发顺序；
- 单进程、主从还是多副本部署。

技术栈评估必须满足本文件的协议，而不能倒过来削弱协议。特别是：

- 如果选 LangGraph，仍需独立业务 Event Log；
- 如果 LangGraph checkpointer 与业务库使用同一种数据库，也必须保持不同 schema/责任边界；
- 不需要跨 LangGraph checkpoint 与业务事务做分布式事务，靠稳定 Command idempotency 消除双写窗口；
- 初版即使单进程，也保留 revision、Inbox/Outbox、lease/fencing 字段，避免未来多实例重构协议。

## 13. 审查清单

建议用户本轮只审查以下架构结论：

- 是否接受“Controller Event Log 唯一业务事实源，LangGraph 是可恢复 Agent 执行层”；
- 是否接受“Git Host 是最终 MR/PR 审批与合入权威，飞书只做方案审批与交互”；
- 是否接受“双基线 + integration candidate + merge queue SHA 复验”；
- 是否接受 capability sandbox、ArtifactManifest、Remote Delivery Adapter 三个强制边界；
- 是否接受 retry taxonomy 与完整生命周期命令化。

通过后再进入技术栈选择，优先评估 LangGraph 如何嵌入这一边界，而不是让 LangGraph 替代 Controller。
