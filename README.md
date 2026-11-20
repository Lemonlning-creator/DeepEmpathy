# 深予 · DeepEmpathy

基于 inner-world 用户建模的共情陪伴应用，采用 **prompt-guided** 策略与模拟小程序界面。全部模型能力调用云端；没有本地模型、GPU 或训练依赖。

## 快速运行

Python 3.10+（本项目在 Python 3.13 上验证）。在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
deep-empathy --demo
```

打开 [本地应用](http://127.0.0.1:8000)。`--demo` 显式开启固定脚本演示，未配置云端时默认展示演示。点击话题、发送即可体验；自由输入只返回演示说明，不进行心理分析，也不写入真实用户画像。

按已验证环境安装：先 `python -m pip install -r requirements.lock`，再 `python -m pip install -e . --no-deps`。锁文件包含开发测试工具。

## 配置真实云端聊天

```bash
cp .env.example .env
```

填写 `.env` 的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，重启 `deep-empathy`。

- 支持 OpenAI-compatible **Chat Completions**。BASE_URL 包含版本前缀，例如服务地址末尾为 `/v1`；网关自动追加 `/chat/completions`。远端使用 HTTPS，本机测试可用 HTTP。
- `LLM_MODEL_RESPOND/PREPARE/ANALYSIS/SUMMARIZATION/EVALUATION` 可按任务覆盖模型名；留空复用 LLM_MODEL。
- 供应商不支持 response_format 时设置 `LLM_JSON_MODE=false`；后台分析仍验证 JSON 契约并最多修复一次；前台复杂分析格式错误直接报错，不增加第三次调用。流式回复不使用 JSON mode。
- 地址、密钥、模型名均未预填。密钥只在服务端读取，不发送到浏览器或写入数据库。
- 同时开启演示与云端时，在「我的空间」切换并建立独立会话，两类会话的记忆隔离。

## 已实现

- **陪伴**：默认一次流式回复，复杂场景两次调用，输入框支持「深入聊聊」，断流重试与回复体验反馈。
- **拾光**：跨重启保存、分页历史、会话重入与删除。
- **关于你**：五层画像，真实原文证据与字符位置，确认、纠正、撤回。
- **我的空间**：云端/演示切换、长期记忆开关、全部数据删除。
- Needs / Goals / Self-view 情境心理假设用于内部策略，未知可保留，不伪造概率、熵或自由能。
- SQLite 持久化、Cookie 匿名身份、用户隔离、跨站请求防护、用户级串行化、幂等请求和原子保存。
- 云端超时、有界重试、任务路由、首字/总耗时与用量记录、持久化后台建模任务。
- 独立 JSONL 云端评估入口。

### 实时交互的调用次数

| 场景 | 前台模型阶段 | 后台任务 |
|---|---|---|
| 普通聊天 | `respond`：一次调用内理解、选择支持方式、自查并流式表达 | 按需整理画像 |
| 复杂/深入对话 | `prepare` 合并分析与策略 → `respond` 流式回复 | 按需整理画像 |
| 重复成功请求 | 直接返回已保存结果，零模型调用 | 不重复入队 |
| 演示 | 固定脚本片段，零云端调用 | 不建模 |

复杂路由为本地可解释规则：明确要求深入分析、较长输入或风险信号；请求 `processing_mode` 支持 auto/fast/deep，风险信号不能强制降为 fast。规则不等于完整语义风险识别，回复提示同样包含安全约束。

后台只在出现显式新信息/纠正、每 4 轮（可配置）或结束会话时触发。一次建模通常 1 次 analysis；较长会话按需增加 1 次 summarization。它们不增加前台等待，但仍产生 token 费用。同一会话尚未执行的任务合并到最新消息。

新主流程不再独立调用 review 模型；改为生成时自查与代码约束。流式文本在整段生成完之前可见，不能承诺对已显示内容完成事前审核。失败片段不会写入正式历史，界面保留“未确认保存”标记以便重试。

表内是正常完成时的模型阶段数。连接前限流/暂时性错误可能触发有界 HTTP 重试，实际请求数记录在 trace；已输出文本后不自动重试上游。首字与总耗时以实际云端服务为准，未配置 API 时没有实测云端延迟。

如供应商默认开启长思考，可按其文档通过 `LLM_EXTRA_BODY` 关闭；参数并非跨厂商通用。`LLM_STREAM_USAGE=true` 可请求流式用量（需供应商支持），否则用量可能未上报，不代表免费。

## 验证

```bash
python -m pytest -q
ruff check src tests
node --check src/deep_empathy/web/app.js
```

测试使用 fixture 和 HTTP mock，不调用真实模型。覆盖一/两次前台调用、首字早于完成、断连取消、后台不阻塞、任务合并、过期写入拦截，以及证据、纠正、隔离、删除、幂等与云端异常。

离线评估需先配置云端：

```bash
python -m deep_empathy.evaluation.runner examples/evaluation.jsonl data/evaluation/results.jsonl
```

该命令将输入样例发送至配置的云端服务，输出 Resonation / Expression / Reception、依据检查和用量。模型估计不能代替真实用户 UMSC、自述反馈或人工证据审查。

## 项目结构

```text
src/deep_empathy/
  api/             HTTP 路由、身份和访问控制
  domain/          领域契约与错误
  llm/             云端网关和固定脚本演示
  prompts/         分任务提示词及版本
  perception/      事件、支持偏好、情境心理分析
  user_model/      画像证据门槛、冲突与版本
  memory/          短期上下文、Mem0 情景/语义记忆、向量检索与持久化后台任务
  planning/        轻量路由、双视角支持约束
  generation/      共情表达
  safety/          保留旧版独立审核组件，实时流程不调用
  orchestration/   单轮闭环、快照、串行化
  storage/         SQLite、事务和级联删除
  evaluation/      显式执行的云端评估
  web/             无构建依赖的模拟小程序前端
```

旧版四阶段方案见 [架构规划](docs/architecture.md)，实际实现见 [实现说明](docs/implementation.md)。

## 运行边界

这是本机研究原型，默认仅监听 127.0.0.1，使用**单进程、单 worker**。前台锁和后台任务执行器在进程内，不支持直接启用多个 worker。后台队列会在进程重启后恢复；运行时依赖同一应用进程，无需另开 worker。Cookie 是本地匿名身份，清除后无法恢复原身份；未提供正式账号、跨设备同步或账号恢复。

真实文本发送至配置的云端服务。数据库位于 `data/deep_empathy.db`，没有应用层加密；不自动上传、备份或跨供应商转发。删除覆盖当前库的消息、证据、画像、摘要和派生记录，不管理用户自行制作的备份。

本版为浏览器中的小程序模拟器，手机宽度铺满屏幕、桌面显示手机框；不含微信原生工程或发布。公开部署、PostgreSQL、多进程、语音、多模态、向量检索和论文训练复现为后续扩展。

## 3D 书店界面

新增 `/bookstore`：左侧三维书店，右侧上半实时画像、下半流式聊天。老板人设为「林予」，用户是来书店相处的朋友。支持进出店、角色走路/坐下/起身、取书阅读归还、制作咖啡与递杯饮用。详见 [书店操作与实现说明](docs/bookstore.md)。

书店启动：`python scripts/preview_bookstore.py --port 8001`，访问 `http://localhost:8001/bookstore`；默认读取项目 `.env`，使用与主应用相同的云端聊天、后台画像和数据库，配置完整时自动选择“云端陪伴”。需要隔离的纯脚本演示时，显式增加 `--offline`（不读取 `.env`，使用独立演示数据库）。额外状态机检查：`node --test tests/bookstore.test.mjs`。

## Mem0 分层记忆

长期记忆已接入 Mem0 OSS + 本地 Qdrant：近期对话作为短期记忆，真实对话事件作为情景记忆，证据支持的画像条目作为语义记忆。Embedding 调用云端，检索超时降级，索引增量后台写入，不增加前台聊天模型调用次数。当前 DashScope 配置自动复用现有密钥和端点。配置与删除/纠正规则见 [记忆说明](docs/memory.md)，示例见 [memory.env.example](configs/memory.env.example)。
