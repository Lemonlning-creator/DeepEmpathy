# 分层记忆：Mem0 OSS

## 三层职责

| 层 | 内容 | 保存与调用方式 |
|---|---|---|
| 短期记忆 | 当前会话最近至多30条消息，按上下文字符预算截断；必要时使用已有会话摘要 | 应用 SQLite 的 messages / summaries，直接进入本轮上下文 |
| 长期情景记忆 | 带时间、会话与原始消息编号的真实对话记录，明确区分用户原话和林予当时的回复 | Mem0 以 episodic 元数据索引；回复不是用户事实或动作完成证明 |
| 长期语义记忆 | 初始认知画像与后续有证据支持的偏好、身份、习惯、认知等条目 | Mem0 以 semantic 元数据索引，保留层级、确定性和可追溯来源 |

使用 `mem0ai==1.0.11` 的 `Memory.add/get_all/search/delete`，向量存储为项目内 Qdrant。
SQLite 的真实消息和有效 claims 是事实来源；Mem0 是可重建的长期语义索引，不替代用户隔离、证据检查或画像纠正。
`infer=False` 写入已经过应用检查的内容，避免让 Mem0 再把隐藏用户设定、助手虚构动作或被撤回画像提炼成事实。语义抽取仍由现有后台云端 analysis 执行，Mem0 负责存储和检索；没有本地 LLM 或本地 Embedding。
角色完整设定 `user_setting.yaml` 不索引；只索引智能体实际可见的有效认知画像。已识别的紧迫风险对话不进入普通长期索引。

## 写入与检索时序

1. 普通前台仍为一次 respond；复杂场景为 prepare + respond。短期对话、当前画像和明确纠正直接读取。
2. 回答前用 Mem0 按当前内容检索相关记忆。语义搜索需要一次云端 Embedding，不是一次额外聊天模型生成。
3. 检索默认最多8条、约2500字符；超时上限1.2秒，或向量索引正在写入时，使用原有画像、近期对话和关键词召回继续回复，不伪造检索命中。
4. 成功保存一轮对话后，在同一 SQLite 事务记录 memory_sync；后台增量索引新情景记录。画像后台任务提交后再同步新增或修订的语义记忆。
5. 启动时自动为已有用户做索引对账和回填。索引内容未变化时不重复生成 Embedding；重启中断的任务恢复执行。

Mem0 写入和本地 Qdrant 操作使用独立单线程执行器，避免阻塞 FastAPI 事件循环。超时的 SDK 调用继续持有执行门，避免取消等待后产生并发文件操作。SDK云端调用最长8秒、关闭自动重试；索引失败每30秒重试，错误信息不包含密钥、对话正文或上游响应正文。

## 纠正、删除与隔离

- 每个请求只使用当前匿名身份的 user_id，Mem0 检索同时过滤 memory_revision。
- 画像确认/纠正/撤回、明确聊天纠正、记忆开关和会话删除会更新世代。旧世代的命中立即失效；后台随后清理旧向量并重建当前仍有效的记录。
- 检索结果还需匹配当前 SQLite 来源、内容摘要和世代；返回的是当前权威文本，不直接信任向量库中的正文。
- 删除会话同步移除其情景索引和受其证据影响的画像索引；关闭长期记忆或删除身份会排队清理该用户的全部 Mem0 向量。
- 清理是异步的，因此物理清理完成前旧向量仍可能存在文件中，但已不能被检索进入对话。删除状态可通过状态接口查看。
- Mem0 自带历史日志使用内存数据库，并在删除单条向量时清理对应审计内容；长期来源与更新记录仅保存在应用 SQLite，不额外落地一份历史正文。

## 配置

默认云端启动启用 Mem0。当前 DashScope 配置自动复用已有 `LLM_BASE_URL` / `LLM_API_KEY`，使用云端 `text-embedding-v4`、1024维，不需要额外 Mem0 平台账号或 API Key。
其他云端供应商需显式设置 Embedding 模型、维度及端点。可参考 `configs/memory.env.example` 合并到项目 `.env`：

```dotenv
MEMORY_PROVIDER=mem0
MEMORY_PATH=./data/mem0
MEMORY_SEARCH_TIMEOUT=1.2
MEMORY_TOP_K=8
MEMORY_CONTEXT_CHARS=2500
# 可选独立云端配置；不设置时复用现有 LLM 端点和密钥
# MEMORY_EMBEDDING_BASE_URL=
# MEMORY_EMBEDDING_API_KEY=
# MEMORY_EMBEDDING_MODEL=text-embedding-v4
# MEMORY_EMBEDDING_DIMS=1024
```

缺少 Embedding 配置时 `configured=false`，保留原聊天与画像逻辑；`MEMORY_PROVIDER=disabled` 可显式停用 Mem0。纯脚本预览不加载此配置。
Embedding 服务需为 HTTPS，禁止无意回退本地模型。模型、端点或维度改变时必须使用新的 MEMORY_PATH 重建索引，不能混用不兼容向量；旧目录属于备份数据，需要自行管理。单个本地向量目录只支持单进程使用，不要启动多个服务共同占用它。
SDK遥测已关闭。密钥只在服务端使用，不写入索引元数据或浏览器。

## 数据位置与接口

- `data/deep_empathy.db`：messages、claims、evidence，以及 memory_sync（持久任务）、memory_index（来源到Mem0 ID映射）、memory_epochs（索引世代）。SQLite迁移至v4，保留现有记录。
- `data/mem0/vectors/`：长期记忆向量及元数据；`embedding.json` 记录索引兼容性标识，runtime/ 存放Mem0运行配置。
- `GET /v1/me/memory-status`：当前用户配置状态、情景/语义索引条数和同步状态。
- `POST /v1/me/memories/search`：`{"query":"上次提到的工作经历"}`，返回 episodic、semantic 与检索状态。
- 所有接口沿用身份 Cookie，POST 仍需 `X-Deep-Empathy: 1`；查询正文放在 JSON 内，不放 URL 查询日志。
- 原画像接口、雷达图、记忆开关、删除与聊天接口保留。

## 验证

自动测试包含：真实Mem0+Qdrant存取（用假云端Embedding客户端，无外部请求）、增量/幂等索引、检索来源校验、用户隔离、纠正/删除/关闭记忆后的即时失效和物理清理、慢检索降级、异步旧写入竞态、持久失败重试与接口鉴权。
还使用真实云端 `text-embedding-v4` 对非敏感测试文本完成了写入、语义搜索和删除验证。

参考：[Mem0 OSS 配置](https://docs.mem0.ai/open-source/configuration)、[Mem0 Python 快速开始](https://docs.mem0.ai/open-source/python-quickstart)、[阿里云 Embedding](https://www.alibabacloud.com/help/en/model-studio/embedding)。
