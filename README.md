# DeepEmpathy · 慢屿书屋

面向人机交互研究的深度共情陪伴智能体，采用 **prompt-guided** 方案。智能体「林予」是慢屿书屋的店主，也是用户的朋友：在日常聊天中理解用户、维护有证据的用户画像，并提供阅读与情感陪伴。

项目包含 **3D 虚拟书屋** 和 **模拟小程序** 两套前端，共用 FastAPI 后端。聊天、画像分析和 Embedding 均调用云端服务，无需本地大模型、GPU 或训练。

## 项目功能

### 聊天与陪伴

- SSE 流式显示回复。普通聊天前台通常只调用一次模型；复杂或主动选择「深入聊聊」时，先准备分析，再生成回复，共两个模型阶段。
- 支持「到店面对面」与「线上聊天」，将交互方式、当前书屋天气和场景状态带入回复上下文。
- 林予的人设、语言风格和边界由配置与提示词约束；聊天正文不输出第一人称动作剧本。
- 八项陪伴能力：书籍推荐、文学讨论、阅读感受交流、阅读经验分享、情感理解、共情回应、用户记忆、持续关怀与关系维护。
- 能力使用情况与本轮主要心理状态在**生成回复的同一次调用**中返回结构化元数据，不单独增加一次判断调用。

### 用户模型与记忆

- **Explicit Profile**：Core、Regulation、Cognition、Identity、Behavior 五层画像，展示 Clarity 与本轮变化。实际更新的层暖金色高亮，下方显示整理状态、更新内容或「本轮暂无画像更新」。
- **Latent Psychology**：Needs、Goals、Self-view 每轮最多激活一项，必须有本轮用户原话依据，否则不激活。
- **Agent Self**：根据模型返回的本轮能力使用结果绿色高亮，不使用关键词匹配模拟能力激活。
- 以 `configs/initial_profile.yaml` 中的周禾「智能体认知画像 v0.1」为起点更新，不把完整人物设定当作智能体已知事实。
- 后台分析证据、保存画像并处理冲突；模型回复结束与画像更新完成是两个不同时间点。
- Mem0 OSS + 本地 Qdrant 提供长期情景记忆、语义记忆和检索；近期消息与摘要提供短期上下文。SQLite 保留原始消息、画像和证据作为事实来源。
- 模拟小程序提供历史、画像依据与确认/纠正/撤回、记忆开关和数据删除入口。

### 3D 书屋

- 桌面默认左侧 60% 为书屋、右侧 40% 为画像与聊天；Three.js 已随仓库提供，无需 npm 构建。
- 四组书架、窗边对坐沙发与共享圆桌、独立角落阅读位、两层主题书展台、绿植、吧台和咖啡机。
- 支持进店自动落座、行走、起身、取书、阅读、归还、制作咖啡等动作。聊天中的受支持行动承诺会进入场景动作队列。
- 老板送出的书和咖啡放在用户对应圆桌；用户说「喝口咖啡」「翻开书看看」时触发相应动作，结束后物品放回桌面。
- 老板按北京时间日程自主活动；不可随意中断的咖啡萃取等待安全点。09:00–18:00 可到店，闭店后熄灯、老板离店，仍可线上聊天。
- 默认接入广州天气。室内保留明亮暖色，阴雨雪天减弱直射光和投影；雨雪限制在室外，并遮挡会投影到室内画面的粒子。

> 这是研究原型：能力高亮是模型对本轮回复的自述，Clarity 是前端依据有效画像证据计算的展示指标，心理状态是有依据的暂时假设，均不等同于客观心理测量。

## 安装与运行

### 1. 环境要求

- Python **3.10+**；项目已在 Python **3.13** 上验证，建议使用该版本。
- Git 与支持 WebGL 的现代浏览器。
- Node.js 22 用于前端自动测试；只运行应用不需要 Node.js。
- 真实聊天需要可用的云端 OpenAI-compatible Chat Completions 接口；启用 Mem0 时还需要云端 Embedding 接口。

### 2. 下载与安装

```bash
git clone https://github.com/Lemonlning-creator/DeepEmpathy.git
cd DeepEmpathy
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Windows PowerShell 使用 `py -3 -m venv .venv` 创建环境，再执行 `.venv\Scripts\Activate.ps1`；之后使用同样的 `python -m pip ...` 命令。

如需按已记录的版本安装，可在 Python 3.13 环境中改用：

```bash
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
```

### 3. 配置 `.env`

```bash
cp .env.example .env
```

Windows PowerShell 可用 `Copy-Item .env.example .env`。至少填写以下三项，具体值以自己供应商、地域与账号的配置为准：

```dotenv
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=填写你自己的云端密钥
LLM_MODEL=qwen3.7-plus
```

这里展示仓库示例中的服务与模型名，不保证你的账号有该模型权限。可以替换为其他兼容服务，**URL、密钥、模型须属于同一服务和可用地域**。`.env` 仅供本机使用，已被 Git 忽略；不要把真实密钥写进 `.env.example`。

**刷新是否保留数据：** 仓库示例为 `TEST_RESET_ON_RELOAD=true`。测试时每次刷新或重新打开页面，都会清除当前浏览器身份的会话、记忆与后续画像，恢复初始认知画像。希望持续积累对话与记忆时，先改为 `false`。

### 4. 启动 3D 书屋（推荐）

在项目根目录、已激活虚拟环境的终端中运行：

```bash
python scripts/preview_bookstore.py --port 8001
```

打开：

- 3D 书屋：<http://127.0.0.1:8001/bookstore>
- 模拟小程序：<http://127.0.0.1:8001/>
- API 文档：<http://127.0.0.1:8001/docs>

此启动器优先读取项目 `.env`，覆盖同名旧 shell 环境变量。配置完整时使用云端陪伴；不需要另启动一个后端。修改 `.env`、Python 代码或人设配置后，用 `Ctrl+C` 停止并重新执行启动命令。

### 5. 其他启动方式

**纯离线界面演示，无需密钥：**

```bash
python scripts/preview_bookstore.py --offline --port 8001
```

使用独立的 `data/bookstore-preview.db`，不读取 `.env`，只提供固定脚本回复；不会调用大模型分析自由输入，不启用 Mem0；天气接口仍可能访问网络。适合检查布局和场景动作。

**通过命令行入口启动同一应用：**

```bash
deep-empathy --port 8000
```

对应 <http://127.0.0.1:8000/> 与 <http://127.0.0.1:8000/bookstore>。添加 `--demo` 可允许固定脚本会话，但不会像 `--offline` 那样隔离数据库或忽略 `.env`。CLI 默认不覆盖已存在的 shell 环境变量。

同一数据库和 Mem0 目录只运行一个应用进程。不要为了同时打开两套界面而启动两个服务；它们在同一个端口下即可访问。

## `.env` 配置说明

配置在服务启动时读取，布尔值使用 `true` / `false`，时间单位均为秒。下表「默认」指程序未设置该变量时的值；与仓库示例不同的地方会单独标明。

### 云端模型与速度

| 配置项 | 默认 / 填写方式 | 作用 |
|---|---|---|
| `LLM_BASE_URL` | 必填；如示例中的 `https://dashscope.aliyuncs.com/compatible-mode/v1` | 服务基础地址，包含服务要求的版本前缀。网关自动追加 `/chat/completions`，不要填写完整聊天接口路径。远端使用 HTTPS。 |
| `LLM_API_KEY` | 必填；自己的密钥 | 仅后端读取，不发送到浏览器。 |
| `LLM_MODEL` | 必填；账号有权限的模型 ID | 各任务未单独指定时使用的基础聊天模型。 |
| `LLM_JSON_MODE` | `true` | 分析等结构化任务请求 JSON object；供应商不支持该参数时设 `false`。输出仍须通过应用结构校验。流式正文不使用 JSON mode。 |
| `LLM_TIMEOUT` | `45` | 云端 HTTP 超时配置；建立连接单独使用 10 秒上限。提高它不会提高生成速度。 |
| `TURN_TIMEOUT` | `180` | 整轮处理超时上限。 |
| `REPLY_MAX_TOKENS` | `600` | 流式回复输出预算，包含同次生成的结构化元数据。过低可能截断回复或导致能力高亮缺失。 |
| `LLM_STREAM_USAGE` | `false` | 是否发送 `stream_options.include_usage`；服务支持时才开启。 |
| `LLM_EXTRA_BODY` | `{}` | 所有模型任务的附加请求字段，须填写合法 JSON，参数取决于供应商。 |
| `LLM_RESPOND_EXTRA_BODY` | `{}`，可自行添加 | 仅前台 `respond` 的附加字段，优先于通用参数。 |

`LLM_EXTRA_BODY` / `LLM_RESPOND_EXTRA_BODY` 不是通用功能开关集合，只填写供应商确实支持的字段。代码对 DashScope 上 `qwen3.7-` 开头模型的 `respond`、`analysis` 默认设置 `enable_thinking=false`，显式配置可覆盖；其他服务不自动套用此规则。

### 按任务选择模型

以下变量都可留空，通常只填 `LLM_MODEL` 即可：

| 配置项 | 用途与回退 |
|---|---|
| `LLM_MODEL_RESPOND` | 前台流式回复；留空时先兼容回退到 `LLM_MODEL_GENERATION`，再到 `LLM_MODEL`。 |
| `LLM_MODEL_PREPARE` | 复杂对话的前置理解与策略准备；留空复用基础模型。 |
| `LLM_MODEL_ANALYSIS` | 后台画像分析；留空复用基础模型。 |
| `LLM_MODEL_SUMMARIZATION` | 较长会话按需摘要；留空复用基础模型。 |
| `LLM_MODEL_EVALUATION` | 显式运行评估脚本时使用；留空复用基础模型。 |
| `LLM_MODEL_PLANNING` | 旧流程 / 实验组件保留，新实时主流程不独立调用。 |
| `LLM_MODEL_GENERATION` | 旧生成任务配置，同时保留为流式回复模型的兼容回退。 |
| `LLM_MODEL_REVIEW` | 旧独立审核组件保留，新实时主流程不独立调用。 |

这些覆盖项只改变模型名，仍共用 `LLM_BASE_URL` 和 `LLM_API_KEY`，不是多个供应商的独立路由配置。

### 后台画像

| 配置项 | 默认 | 作用 |
|---|---|---|
| `BACKGROUND_ENABLED` | `true` | 是否执行后台画像分析与按需摘要。关闭后前台聊天仍可工作，但不执行这些后台建模任务。 |
| `BACKGROUND_INTERVAL` | 程序默认 `4`；仓库示例 `1` | 周期建模间隔。`1` 使每轮都具备周期触发条件，但没有新证据时仍不产生画像更新；显式新信息、纠正、结束会话也可触发。 |
| `BACKGROUND_TIMEOUT` | `120` | 单个后台任务的超时上限。 |

后台任务不阻塞前台回复，但可能需要排队或修复结构化输出。「回复完成」后画像框仍显示「正在整理本轮画像…」是正常时序，完成后才显示实际更新或暂无更新。

### Mem0 与云端 Embedding

Mem0 使用开源库和项目本地的 Qdrant 文件存储，**不需要额外注册 Mem0 平台账号，也不需要 Mem0 平台密钥**。

| 配置项 | 默认 / 填写方式 | 作用 |
|---|---|---|
| `MEMORY_PROVIDER` | `mem0` | `mem0` 启用长期向量索引与检索；`disabled` 停用该索引，近期对话和原有画像仍可使用。 |
| `MEMORY_PATH` | 项目 `data/mem0` | Mem0 / Qdrant 本地数据目录。 |
| `MEMORY_EMBEDDING_BASE_URL` | 不设置时复用 `LLM_BASE_URL` | 云端 Embedding 基础地址，要求 HTTPS；使用独立服务时填写其兼容地址。 |
| `MEMORY_EMBEDDING_API_KEY` | 不设置时复用 `LLM_API_KEY` | Embedding 服务密钥。 |
| `MEMORY_EMBEDDING_MODEL` | DashScope 默认 `text-embedding-v4`；其他服务默认空 | 向量模型，不要填写聊天模型。其他服务需显式配置。 |
| `MEMORY_EMBEDDING_DIMS` | `1024` | 向量维度，须与服务支持的输出维度一致。 |
| `MEMORY_SEARCH_TIMEOUT` | `1.2` | 前台检索等待上限；超时或索引写入繁忙时，降级到已有画像与近期上下文。 |
| `MEMORY_TOP_K` | `8` | 检索条数，代码限制为 1–20。 |
| `MEMORY_CONTEXT_CHARS` | `2500` | 检索记忆的上下文字符预算，代码限制为 500–6000。 |

注意：**不设置变量**与**设置为空字符串**不同。希望自动复用聊天端点 / 密钥时，不要把 `MEMORY_EMBEDDING_BASE_URL=` 或 `MEMORY_EMBEDDING_API_KEY=` 空行取消注释。只有独立配置时才填写。非 DashScope 服务若暂时没有 Embedding，可先设置 `MEMORY_PROVIDER=disabled`。

改用其他 Embedding 端点、模型或维度时，应同时设置新的 `MEMORY_PATH` 重建索引，不能混用旧向量。检索需要云端 Embedding 请求，后台写入也有 Embedding 费用；它们不属于额外的聊天生成调用。详情见 [记忆实现](docs/memory.md)。

### 数据、测试、天气与 Cookie

| 配置项 | 默认 | 作用 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/deep_empathy.db` | 当前仅支持 SQLite。相对路径按启动目录解析，建议从项目根目录运行。目录自动创建。 |
| `TEST_RESET_ON_RELOAD` | 程序默认 `false`；仓库示例 `true` | 测试模式下刷新 / 重开页面会清空当前浏览器身份的历史、后续画像与记忆，恢复初始画像。需要保留数据时改 `false`。 |
| `DEMO_ENABLED` | `false` | 是否允许固定脚本演示会话；CLI 的 `--demo` 也可开启。 |
| `COOKIE_SECURE` | `false` | 本地 HTTP 保持 `false`；通过 HTTPS 部署时可设 `true`。 |
| `WEATHER_ENABLED` | `true` | 是否获取书屋位置天气；不调用大模型，也不读取访客 GPS。 |
| `WEATHER_LOCATION` | `广州` | 书屋所在地显示名称。改变城市时需一起修改经纬度。 |
| `WEATHER_LATITUDE` | `23.1291` | 书屋纬度。 |
| `WEATHER_LONGITUDE` | `113.2644` | 书屋经度。 |

天气由 Open-Meteo 提供，服务端缓存约 10 分钟；失败时使用有时效标记的缓存，超过有效期显示未知。聊天沿用页面显示的天气快照，避免场景与回复不一致。测试模式提供标注为「非实时」的天气预览，不修改真实天气或营业时间。

## 调用次数与响应时序

| 场景 | 前台聊天生成阶段 | 其他工作 |
|---|---|---|
| 普通对话 | `respond` 一次，流式返回正文与本轮元数据 | 按条件后台分析画像、同步记忆 |
| 深入 / 复杂对话 | `prepare` → `respond` 两个阶段 | 同上 |
| 重复已成功请求 | 返回保存结果，不重新生成 | 不重复入队 |
| 固定脚本演示 | 零云端生成 | 不做真实用户分析 |

后台通常一次 `analysis`，长会话可能另做 `summarization`。结构修复、暂时性错误的有界重试可能增加实际请求数，不能把上述阶段数视作所有情况下的请求总数。流式正文已开始显示后不自动重试上游。

首字延迟受供应商排队、模型思考、网络与记忆检索影响。可优先使用快速模式、减少不必要的长回复、按供应商能力关闭长思考；单纯调大超时不会改善首字速度。

## 数据与主要代码位置

| 位置 | 内容 |
|---|---|
| `data/deep_empathy.db` | 消息、画像条目、原话证据、摘要、轮次 trace、后台任务与记忆同步状态 |
| `data/mem0/` | 长期向量索引、元数据与兼容性标识 |
| `configs/persona.yaml` | 林予的人设与语言风格 |
| `configs/initial_profile.yaml` | 初始化时注入的智能体认知画像 |
| `configs/user_setting.yaml` | 实验用户的完整人物设定，不直接作为智能体已知画像注入 |
| `src/deep_empathy/llm/gateway.py` | HTTPX 云端聊天调用、流式解析、鉴权与错误处理 |
| `src/deep_empathy/prompts/templates.py` | 回复、分析与各任务提示词 |
| `src/deep_empathy/orchestration/service.py` | 一轮对话、前后台调度和结果保存 |
| `src/deep_empathy/orchestration/capabilities.py` | 能力与主要心理状态元数据解析、校验 |
| `src/deep_empathy/memory/` | 短期上下文、Mem0 适配、检索与后台同步 |
| `src/deep_empathy/bookstore.py` / `weather.py` | 营业日程 / 书屋天气 |
| `src/deep_empathy/web/bookstore*.js`、`bookstore*.mjs` | 3D 场景、动作状态机、聊天与画像面板 |
| `src/deep_empathy/web/app.js` | 模拟小程序界面 |

聊天网关直接使用 **HTTPX** 调用兼容接口；Mem0 的云端 Embedding 适配使用其依赖的 OpenAI SDK。两个前端均访问本项目后端，不持有云端密钥。

浏览器以 HttpOnly Cookie 识别匿名用户。固定使用同一地址访问（例如一直使用 `127.0.0.1`），不要在 `localhost` 与 `127.0.0.1` 之间来回切换后误认为历史丢失。数据不会因普通服务重启丢失，但开启刷新清空测试模式时会按上述规则重置。SQLite 与向量文件没有应用层加密，也没有自动远端备份。

## 验证与评估

```bash
python -m pytest -q
ruff check src tests
node --test tests/bookstore*.test.mjs
node --check src/deep_empathy/web/bookstore.js
node --check src/deep_empathy/web/bookstore-scene.js
node --check src/deep_empathy/web/app.js
```

当前自动测试包括 91 项 Python 测试和 39 项前端 Node 测试，使用 fixture / mock，不要求真实云端密钥。覆盖流式响应、调用路由、证据与画像、能力元数据、记忆隔离与删除、场景寻路和动作、天气遮挡及闭店状态。

显式运行云端评估（需要配置密钥，会产生调用费用）：

```bash
python -m deep_empathy.evaluation.runner examples/evaluation.jsonl data/evaluation/results.jsonl
```

输出共情维度评分、依据检查与用量记录；模型评分不能代替真实用户反馈或人工审查。

## 常见问题

- **提示「云端模型鉴权失败」**：核对端点地域、密钥所属账号、模型权限与 `LLM_API_KEY` 是否填写；URL 只填基础地址。配置修改后必须重启服务。CLI 还需检查 shell 是否保留同名旧变量；书屋启动器优先使用项目 `.env`。不要在报错截图或 GitHub Issue 中粘贴密钥。
- **只返回界面演示说明**：确认未使用 `--offline`，已配置三项必需 LLM 参数，并选择云端会话。脚本演示不会分析自由输入。
- **首字慢或等待超时**：先确认供应商服务与模型速度、思考开关，再检查记忆检索状态；深度模式比普通对话多一个前台阶段。
- **回复完成后画像才更新**：画像整理在后台独立运行；看「本轮画像更新」状态，分析完成且通过证据检查后才会保存。
- **刷新后数据消失**：检查 `TEST_RESET_ON_RELOAD`，持续使用时应设 `false` 并重启。
- **Mem0 未启用 / 检索失败**：检查 `MEMORY_PROVIDER`、云端 Embedding 配置与维度；不要留空覆盖需要自动继承的变量。确保只有一个进程占用同一向量目录。
- **端口已占用**：先停止旧服务，或给启动命令传入其他 `--port`；关闭浏览器页面不会停止终端里的服务。
- **书屋很暗、不能进店或看不到老板**：按北京时间判断营业状态，18:00 至次日 09:00 闭店。天气预览不会改变营业时间，可继续线上聊天。

## 运行边界与进一步说明

本项目默认只监听 `127.0.0.1`，使用**单进程、单 worker**。后台任务随应用进程运行和恢复，无需另启动 worker；不支持直接用多个 worker 共享 SQLite、内存锁和本地 Qdrant。

这是浏览器里的小程序模拟器，未包含微信原生工程、正式账号系统、跨设备身份恢复、语音或多模态交互。真实输入会发送到你配置的云端服务；公开部署前需自行补充认证、访问控制、数据保护与运维措施。

文档入口：[书屋实现与操作](docs/bookstore.md) · [Mem0 记忆](docs/memory.md) · [实现说明](docs/implementation.md) · [最初架构规划](docs/architecture.md)。早期设计文档保留了演进记录，当前行为以本 README 和代码为准。
