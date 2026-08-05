# AI Coding Agent 的工作区隔离与人工门禁调研

- 日期：2026-08-05
- 范围：成熟 AI coding agent、coding workspace 以及 GitHub/GitLab CI/CD 的官方文档与一手工程资料
- 目的：回答两个问题：
  1. Git/worktree/sandbox 通常按任务、角色还是 attempt 隔离？
  2. 人工审批通常放在方案/计划、各执行阶段，还是最终 PR/MR？

> 本文是研究结论，不是已经接受的架构决策。涉及本项目的内容会明确标记为“建议”或“推断”。

## 摘要

调研结果不支持“每个顺序角色、每次 attempt 都必须拥有独立 Git worktree”作为默认规则。

主流产品更常见的边界是：

- 每个独立任务、会话或并行修改单元拥有独立环境或 worktree；
- 同一任务中的连续修改和反馈循环通常沿用同一分支或工作环境；
- 只读分析角色不必因为角色不同而复制一份可写 worktree；
- 独立测试或验收更需要的是“干净、可复现、固定 Candidate SHA 的运行环境”，不一定必须永久占用独立 Git worktree；
- attempt 级环境通常是短生命周期 sandbox，而不是长期保留的工作目录。

人工审批也主要集中在少数高价值边界：

- 编码前的方案/计划批准，可配置或按风险启用；
- PR/MR 合入前的代码审查和批准，通常是强制门禁；
- 生产部署前的批准，只对受保护环境启用；
- CI、自测、E2E、静态分析以及 AI 代码验收通常作为自动门禁，不需要每步人工点击。

因此，朋友公司采用的“方案设计批准 + 最终 MR 合入验收”与主流工程实践是相符的。对于本项目，更合适的默认策略是两个常规人工门禁，加上按风险触发的异常升级，而不是所有阶段都安排人工批准。

## 一、工作区与运行环境隔离

### 1. OpenAI Codex

OpenAI 对 Codex Cloud 的描述是：每个任务在独立的隔离环境中处理；任务结束后生成可审查的变更和测试证据。Codex App 则内置 worktree 支持，让并行 agent 在代码库的隔离副本中工作，不影响本地 Git 状态。

- [Introducing Codex](https://openai.com/index/introducing-codex/)：每个 task 独立运行在隔离环境中。
- [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)：每个并行 agent 使用隔离的代码副本，底层支持 worktree。
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)：OpenAI 将应用做成“每个 git worktree 可启动一个实例”，每个变更拥有独立的应用、日志和指标环境，任务结束后销毁。

**事实判断：** Codex 的主要隔离单位是 task、thread、change 或并行 agent，而不是一个顺序流水线中抽象的“PRD 角色”“架构角色”。

**对本项目的推断：** 当多个阶段只是顺序读取同一不可变提交时，为每个角色复制 worktree 不会显著提高 Git 安全性。真正需要隔离的是可写开发任务，以及对 Candidate SHA 的干净验证运行。

### 2. Claude Code

Claude Code 的官方文档清楚地区分了“会话/并行编辑隔离”和“角色协作”：

- [Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees)：worktree 用于隔离并行 Claude Code session，避免文件修改相互碰撞；桌面端会为每个新 session 自动建立 worktree。
- 同一文档说明，subagent 可以按需设置 `isolation: worktree`，并非所有 subagent 默认都必须使用 worktree。
- [Run agents in parallel](https://code.claude.com/docs/en/agents)：如果任务会修改相同文件，应使用 worktree；agent teams 本身并不自动隔离 worktree，无法隔离时应按文件所有权拆分工作。
- [Orchestrate teams of Claude Code sessions](https://code.claude.com/docs/en/agent-teams)：agent team 的重点是独立上下文、任务列表和消息协作；官方还指出，顺序任务、同文件修改或依赖很多的工作通常更适合单一 session 或 subagent。

**事实判断：** Claude Code 把 worktree 当作并行写入冲突的解决机制，而不是角色身份本身的安全边界。角色和 worktree 是两个正交概念。

**对本项目的推断：** “一个角色一个 worktree”会把逻辑角色和文件系统隔离错误绑定。更稳妥的规则应是：只要存在并行写入、独立候选变更或不可信运行，就创建独立环境；只读角色可读取受控快照。

### 3. GitHub Copilot cloud agent

GitHub Copilot cloud agent 为每个 coding task 提供独立的临时开发环境，并在一个分支上工作，一个任务最多产生一个 PR。

- [About GitHub Copilot cloud agent](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/about-assigning-tasks-to-copilot)：任务运行在 GitHub Actions 驱动的 ephemeral development environment；agent 一次只在一个分支上工作，每个 task 对应一个 PR。
- [GitHub Copilot Agents responsible use](https://docs.github.com/en/copilot/responsible-use/agents)：agent 只能推送到单一受控分支，不能直接推送默认分支；由 agent PR 触发的工作流在特定情形下还需要有写权限的人批准运行。
- [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)：cloud agent 文件系统是临时的，任务结束后文件会被丢弃，需要持久化的证据必须发送到外部系统。

**事实判断：** GitHub 的隔离边界是 task + ephemeral environment + branch + PR，而不是 plan/research/development/test 每个角色一个长期 checkout。

### 4. Google Jules

Jules 的隔离单位也是 task/session：

- [Getting started with Jules](https://jules.google/docs/)：Jules 在虚拟机中克隆代码、安装依赖和修改文件。
- [Managing tasks and repos](https://jules.google/docs/tasks-repos)：每个 task 在自己的 VM 中运行，并拥有自己的日志、环境安装和代码变更。
- [Jules Sessions API](https://jules.google/docs/api/reference/sessions/)：session 是执行一个 coding task 的核心资源，包含 source repository 和 starting branch。

**事实判断：** 每个任务一个 VM，而不是任务内部每个 agent 角色一个 VM。attempt 是否重建 VM 是产品实现策略，官方没有要求 attempt 永久对应独立 Git worktree。

### 5. SWE-agent / SWE-ReX

SWE-agent 的官方用法将一次 issue 处理作为一个 run，在 Docker/远程执行环境内拉取或复制仓库，最终输出 patch，随后再选择应用到本地或打开 PR。

- [SWE-agent command-line tutorial](https://github.com/SWE-agent/SWE-agent/blob/main/docs/usage/cl_tutorial.md)：GitHub 仓库可拉入运行环境，本地仓库会复制到 Docker container；成功结果可以先保存为 patch，再由外部流程检查和应用。
- [SWE-ReX](https://github.com/SWE-agent/swe-rex)：为 agent 提供可本地或远程运行的 sandboxed shell environment，并支持多个 agent run 并行。

**事实判断：** 隔离强调一次 agent run 的执行环境和输出 patch，而不是为顺序职责预先创建多个长期 worktree。

## 二、隔离粒度的共同模式

综合上述官方资料，可以得到以下模式：

| 场景 | 常见隔离单位 | 是否通常需要独立 Worktree |
| --- | --- | --- |
| 两个 agent 并行修改代码 | 每个 session/task/change | 是 |
| 一个 agent 连续开发、修复测试反馈 | 同一 task/branch | 通常复用 |
| PRD/架构等只读分析 | 不可变仓库快照 + 独立 LLM 上下文 | 不一定 |
| 自测 | 当前开发 workspace | 通常复用 |
| 独立 E2E/验收 | Candidate SHA + 干净临时运行环境 | 需要环境隔离；不一定需要长期 worktree |
| attempt 重试 | 新执行记录和新 sandbox，或清理后复用 | 取决于并发、取证和污染风险 |
| 多个候选方案并行竞争 | 每个 candidate/branch | 是 |

这里应区分三类经常被混在一起的隔离：

1. **LLM 上下文隔离**：不同角色必须使用新 session，避免角色污染。
2. **Git 源码隔离**：避免并行写入、保护用户工作区和固定 Candidate SHA。
3. **运行时隔离**：清除进程、端口、数据库、浏览器状态、缓存、环境变量和测试数据。

新的 LLM session 不等于需要新的 Git worktree；新的 E2E attempt 则往往更需要新的运行时 sandbox，而不只是一个新目录。

## 三、人工审批门禁

### 1. 方案/计划审批是常见能力，但通常可配置

Jules 是最明确的一手案例：

- [Reviewing plans & giving feedback](https://jules.google/docs/review-plan/)：编码前展示计划，用户可以反馈并批准；Web 界面在用户离开后还可能定时自动批准计划。
- [Jules Sessions API](https://jules.google/docs/api/reference/sessions/)：`requirePlanApproval` 为可选配置；API session 默认自动批准，只有显式设为 `true` 才进入 `AWAITING_PLAN_APPROVAL`。

GitHub Copilot cloud agent 也允许用户先让 agent 调研、生成计划、迭代，然后再创建 PR；也可以从其他入口直接让 agent 创建 PR：

- [About GitHub Copilot cloud agent](https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/about-assigning-tasks-to-copilot)

**事实判断：** 方案批准是成熟产品的重要控制点，但不是所有任务都强制人工门禁。通常会按入口、任务复杂度或组织策略决定。

### 2. PR/MR 合入审批是最标准、最强的人工门禁

- [GitHub protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)：可要求 PR 审批、状态检查、对话解决、成功部署、线性历史和限制推送；还可要求最新可审查提交由非提交者批准。
- [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)：按文件路径自动请求责任人审查，并可要求 Code Owner 批准后才能合入。
- [GitLab merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)：required approvals 在未满足时阻止合并，可按用户、规则和 Code Owner 配置。

**事实判断：** GitHub/GitLab 都把人工批准聚合在“候选变更进入受保护分支”这一不可逆或高影响边界，而不是要求人批准每个 CI job 或 agent 阶段。

### 3. 部署批准是独立且按环境启用的门禁

- [GitHub deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)：受保护 environment 可要求人工 reviewer、禁止发起人自批、限制分支；在批准前 job 无法访问环境 secrets。

**事实判断：** 合入批准与生产部署批准是两个不同的风险边界。并非所有项目都需要部署人工门禁，但生产环境、敏感 secrets 或受监管系统通常会启用。

### 4. 自动化审查用于降低人工频率，而不是替代最终责任

- [Introducing upgrades to Codex](https://openai.com/index/introducing-upgrades-to-codex/)：OpenAI 描述了 Codex 自动审查 PR、运行测试和在人工审查前发现问题的使用方式，同时明确建议把 Codex 当作额外 reviewer，而不是替代人工审查。

**事实判断：** 成熟实践倾向于让自动工具承担高频、重复、证据明确的检查，把人力留给意图、权衡、风险接受和最终合入。

## 四、对 Hermes Pipeline 的建议

以下是基于上述资料的设计建议，不是外部产品的直接规定。

### 建议 A：将 Worktree 从“角色边界”改为“写入/并行/candidate 边界”

推荐的默认拓扑：

```text
repository-mirror/                 # Controller 管理，只用于对象库和受控读取
pipelines/PIPE-0042/
└─ development/                    # 此 Pipeline 的持续可写 worktree/branch

runs/PIPE-0042/
├─ e2e-attempt-003/                # 临时 sandbox，可使用 detached checkout
└─ acceptance-attempt-002/         # 临时 sandbox，可使用 detached checkout
```

- PRD、Architecture：
  - 使用新的 Codex session；
  - 只读访问同一个固定 `Base SHA`；
  - 不因为角色不同创建长期可写 worktree。
- Development：
  - 每条 Pipeline 保留一个 Controller 管理的可写 worktree；
  - 修复循环沿用它，Controller 在边界处生成新的 Candidate SHA。
- E2E、Acceptance：
  - 每次都从精确 Candidate SHA 启动干净的临时运行环境；
  - 两者不能共享仍在运行的进程、浏览器 profile、数据库或缓存；
  - 可以使用不同的临时 detached checkout，也可以串行复用一个经过强制清理和 SHA 校验的验证 checkout；
  - 测试证据保存在 worktree 外的 artifact store。

只有以下情况才默认创建额外 worktree：

- 两个写入 agent 并行；
- 同时维护两个 Candidate；
- 执行不可信命令需要文件系统级隔离；
- 高风险任务要求完整取证；
- 旧 attempt 必须原样保留用于故障复盘。

该方案仍然保护用户工作区，也保留 Candidate SHA 可复现性，但避免为只读角色和每次普通重试长期复制依赖、构建缓存和 Windows 文件树。

### 建议 B：默认采用两个常规人工门禁

推荐的标准模式：

```text
需求提出与澄清
  -> Codex 生成 PRD + Architecture + Test Plan
  -> [人工门禁 1：方案基线批准]
  -> OpenCode 开发 + 自测
  -> OpenCode 独立 E2E
  -> Codex 自动验收
  -> 创建或更新 MR
  -> [人工门禁 2：MR 合入批准]
```

其中：

- “需求确认”保留为人与 prod-main 的交互行为，但不必再形成一个与方案批准分离的强制点击门禁；
- PRD 与 Architecture 仍可由两个独立 Codex session 产生，以保留职责分离；
- 人工一次审查完整的“需求基线 + 技术方案 + 测试计划”，避免连续收到 PRD 卡片和 DESIGN 卡片；
- 自测、E2E、Codex Acceptance 都是强制自动门禁；
- Codex Acceptance 不通过直接回 Development，不需要人确认测试缺陷是否真实；
- 最终 MR 由指定 reviewer/Code Owner 人工批准并合入。

### 建议 C：把额外人工审批改成条件触发

以下情况再暂停并请求人：

- agent 发现需求矛盾或缺少业务决策；
- 方案涉及安全边界、权限、不可逆数据迁移、公开 API 破坏或重大成本；
- `Base SHA` 漂移，需要 Baseline Refresh；
- 自动修复超过重试预算；
- E2E/Acceptance 结果冲突，无法自动归责；
- 需要获取额外凭据、访问外部系统或扩大权限；
- 生产部署本身被项目策略设为人工批准。

### 建议 D：提供可配置的审批策略，而不是硬编码一种组织流程

建议至少提供：

| 策略 | 常规人工门禁 | 适用场景 |
| --- | --- | --- |
| `standard` | 方案基线、MR 合入 | 默认团队项目 |
| `regulated` | 需求基线、技术方案、MR 合入、可选生产部署 | 受监管或高风险项目 |
| `fast-track` | MR 合入 | 小修复、低风险内部工具 |

无论使用哪种策略，agent 主动提问、权限升级、基线漂移和自动门禁无法判定时，都可以触发异常人工介入。

## 五、建议结论

1. 不建议确认“每个角色、每个 attempt 一个长期 worktree”的原方案。
2. 建议确认“每条 Pipeline 一个持续开发 worktree；每个独立验证运行使用干净的临时 sandbox；只读阶段共享不可变源码快照”。
3. 不建议把 PRD 审批、Architecture 审批、E2E 后审核、Codex 验收后审核全部设为默认人工门禁。
4. 建议默认采用“方案基线批准 + 最终 MR 合入批准”两个人工门禁，其他检查自动化，异常按条件升级。
5. 已经接受的 PRD/Architecture 职责分离仍然有价值；需要调整的是人工批准频率，而不是合并两个 agent 的职责。

