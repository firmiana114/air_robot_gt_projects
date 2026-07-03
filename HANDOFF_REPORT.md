# air_robot_gt_projects 交接报告

> 本报告是“当前状态快照”，逐轮改动细节见 Git 历史；本轮已按规范压缩冗长的逐轮记录。

## 背景和目标

RabbitBot 自主运行包，部署在 ShuHao-orin。Git 根 `/mnt/disk1/gt/air_robot_gt_projects`，主代码 `rabbitbot-dev-ros2-master`，Python 包 `rabbitbot`（>=3.10）。系统由 `rabbitbot-control-console.service`（控制台，nvidia 用户，8080）+ `rabbitbot-loop.service`（导览主循环）+ 一组容器化基础服务组成，支持 QA/导览 workflow、语音口令、返航、无机器人模式。

当前分支 `feature/memory-markdown-neo4j`（从 `feature/qa-vlm-workflow` 分出），本轮目标：把 Memory Agent（`rabbitbot-memory` 容器，28182）的记忆来源从"仅 Neo4j 知识图谱"扩展为"markdown 文档 + Neo4j 知识图谱"双来源，供 VLM/LLM 生成回答前检索相关记忆；Neo4j 检索异常或为空时自动忽略该来源，不影响 markdown 结果、不中断请求。

近期主线：把原来挤在单个 `rabbitbot-unified-runtime` 容器内的服务**解耦为多容器（docker-compose）**，并让导览 workflow 跑在专用容器上；配套修复前端、日志、TTS、STT、启动等问题。

## 当前运行架构（解耦栈，已上线）

由 `docker/portable/docker-compose.decoupled.yaml` 定义，全部 `network_mode: host`（服务间走 127.0.0.1，无需改服务地址）：

| 容器 | 镜像 | 端口/职责 |
|---|---|---|
| neo4j | 官方 neo4j:5.26-community | 7687 图数据库 |
| rabbitbot-vlm | core-portable | 8000 VLM + 8005 Embedding |
| rabbitbot-audio | core-portable | 28185 TTS(Kokoro) + 28184 STT(SenseVoice) |
| rabbitbot-memory | core-portable | 28182 Memory Agent(Graphiti) |
| rabbitbot-navbridge | nav-portable | 28180 导航桥接/Robot Agent |
| rabbitbot-workflow | core-portable | 导览 workflow 专用宿主（loop 经 docker exec 注入） |

- vlm/audio/memory/workflow 共用 core-portable 镜像，各只跑自己服务子集（`scripts_1/unified_runtime/start_role_container.sh`，按 `RABBITBOT_CONTAINER_ROLE` 分派；它 source `start_unified_container.sh` 复用启动函数）。
- loop 通过 `RABBITBOT_BASE_RUNTIME=compose`（写在 `runtime/portable.env`）切到解耦栈：`ensure_decoupled_services()` 用 `docker compose up` 拉起基础服务+workflow 宿主；`CONTAINER_NAME=rabbitbot-workflow`，所有 workflow 的 docker exec 指向它。真实机器人模式下 nav 唯一由 `rabbitbot-navbridge` 提供（前台 compose up 作进程组，复用既有 nav 生命周期）。
- 镜像未瘦身：3 个 rabbitbot 容器共用 core-portable（本机已无原始最小镜像）；容器层面已完全解耦。

## 当前状态

本轮更新（2026-07-03，兰石企业原地产品导览分支）：
- 当前分支：`lanshi`，基于 `cb97945 调整TTS音频设备选择顺序为auto` 创建，专门服务兰石企业导览任务。
- 任务定位：机器人站在原地循环介绍兰石平台产品，不进行导航移动，不启动 VLM、Embedding、STT、Memory；只保留 TTS、28180 动作桥接和 workflow 宿主。
- 已新增：`rabbitbot-dev-ros2-master/scripts_1/start_lanshi_product_guide.py`，直接调用 TTS `/exec`，按句执行 `text_to_speech` + `wait_speech`，每轮简介词播完后等待 5 秒继续下一轮；动作通过 28180 `/do_arm_async` 穿插触发，动作失败仅记录 WARNING，不中断循环介绍。
- 已调整：`start_loop_entry.sh` 在本分支默认进入 `RABBITBOT_LANSHI_GUIDE_MODE=1`，强制使用 portable compose 路径，关闭 VLM/Embedding/STT/模型自动下载和语音启动等待；`start_nav_bridge_workflow_loop.sh` 在兰石模式下会停止 `neo4j`、`rabbitbot-vlm`、`rabbitbot-memory`，只拉起 `rabbitbot-audio` 与 `rabbitbot-workflow` 基础容器，导航桥接只等待 28180 动作接口，不等待导航核心 Pose/Ready。
- 已调整：`scripts_1/unified_runtime/start_role_container.sh` 的 audio 角色不再强制启动 STT，改由 `RABBITBOT_UNIFIED_START_STT` 控制；`docker/portable/docker-compose.decoupled.yaml` 的 audio healthcheck 改查 TTS 28185，workflow 宿主不再强依赖 memory，支持兰石 TTS-only 运行。
- 待验证：尚未实际启动 `rabbitbot-loop.service` 跑兰石循环，需现场确认 28180 动作服务和 TTS 声音输出正常；如机器人动作名称与现场动作库不匹配，可通过 `RABBITBOT_LANSHI_ACTIONS` 覆盖动作序列。

本轮更新（2026-07-02，TTS 本地输出优先选择非 HDA 外接设备）：
- 背景：Aaron 询问 local 模式是否优先选择设备名非 `NVIDIA Jetson AGX Orin HDA` 的输出；原逻辑在未设置 `TTS_DEVICE_NAME` 时会优先非内置设备，但 `auto` 回退默认设置 `TTS_DEVICE_NAME=BT67` 后，BT67 不存在时会直接进入内置声卡回退，可能跳过其它外接输出。
- 已完成：`scripts/start_tts_app.bash` 的 sounddevice 扫描逻辑改为三档优先级：显式 `TTS_DEVICE_NAME` 匹配 > 非内置且非 HDA 的外接输出 > 允许内置声卡时的内置回退。
- 已完成：新增设备选择诊断字段 `orin_hda`、`matched` 和最终 `reason`，启动日志会显示 `preferred_name`、`non_hda_external` 或 `builtin_fallback`，便于排查为什么选中某个输出设备。
- 已验证：`bash -n rabbitbot-dev-ros2-master/scripts/start_tts_app.bash` 通过；容器内模拟选择当前会选 `REDMI Speaker 2-4550: USB Audio (hw:3,0)`，reason=`non_hda_external`。
- 已验证：重启 `rabbitbot-audio` 后 TTS/STT 均恢复，容器 healthy；TTS 日志显示 `使用输出音频设备 REDMI Speaker 2-4550: USB Audio (hw:3,0)，index=25，reason=non_hda_external`。
- 注意：如果 REDMI 只停留在 Bluetooth 设备列表、没有出现在容器 `sounddevice.query_devices()` 中，本逻辑仍无法选中它；需要先让宿主/容器音频层暴露出可用输出设备。

本轮更新（2026-07-02，Kokoro TTS 模型路径切到项目 models）：
- 背景：Kokoro 本地模型已放在项目根目录 `models/Kokoro-82M`，需要让 TTS 默认从项目目录读取，避免依赖容器内额外 `/models` 路径或在线下载。
- 已完成：`rabbitbot/audio/run_tts_espnet.py` 新增 Kokoro 模型目录解析逻辑，默认使用 `air_robot_gt_projects/models/Kokoro-82M`；仍保留 `KOKORO_MODEL_DIR` 显式覆盖，并在项目模型不完整但旧 `RABBITBOT_MODELS_DIR` 可用时记录 WARNING 后回退。
- 已完成：新增 INFO/启动日志，记录 Kokoro 模型目录来源、实际路径和完整性状态，便于排查路径错误、缺少 `config.json`/`kokoro-v1_0.pth`/`voices/zm_yunxi.pt` 或意外回退。
- 已验证：`python3 -m py_compile rabbitbot-dev-ros2-master/rabbitbot/audio/run_tts_espnet.py` 通过；`docker restart -t 20 rabbitbot-audio` 后 TTS(28185) 与 STT(28184) 均恢复，`rabbitbot-audio` 为 healthy。
- 已验证：TTS 日志显示 `KokoroTTS: 使用模型目录 source=project_models, dir=/workspace/projects/models/Kokoro-82M, ready=True`，并完成预热与 STT 启动提示语合成。
- 注意：工作区仍保留此前已有的 `docker/portable/docker-compose.decoupled.yaml` 未提交改动（TTS 后端默认 auto），本轮提交未纳入该文件。

本轮更新（2026-07-02，控制台服务状态宽限期修复与音频设备排查）：
- 背景：Aaron 反馈前端"服务状态"面板有时与实际不一致，典型场景是 Orin 整机重启后先手动启动控制台。
- 根因（读代码确认）：`status.py::get_runtime_service_statuses` 的"启动中"黄色态此前只有两条触发路径——①主循环(`rabbitbot-loop.service`)进程刚启动 180s 内；②有人点了前端"重启"按钮、记录过 `_recent_container_restarts`。但 `docker-compose.decoupled.yaml` 全部 6 个容器都是 `restart: unless-stopped`，Orin 重启后 docker 会自行拉起容器（不经过 loop），而控制台没有 `After=docker.service` 依赖、且默认不开机自启，手动启动后立刻对外提供 `/api/status`——此时两条触发路径都不满足，未就绪的服务会被误判为"离线"而非"启动中"。
- 已完成：`rabbitbot/control_console/status.py` 增加第三条触发信号——控制台进程自身的启动时间戳 `_console_process_start_epoch`（模块加载时记录），同一 180s 宽限期内同样让未就绪服务显示"启动中"；`get_runtime_service_statuses` 的 DEBUG 日志同步增加 `console_uptime` 字段便于排查。
- 已验证：直接 `docker restart rabbitbot-audio`（绕开控制台重启按钮，模拟容器被 docker 自动重启的场景）复现问题——从发起重启到 TTS/STT 端口全部就绪约 45 秒（14:33:16→14:34:01），期间 `/api/status` 全程返回 `state=offline`，从未出现 `starting`，与代码分析完全吻合。**修复代码已上传，但控制台进程仍是旧代码在跑（重启需交互式 sudo，本工具无法执行），须 Aaron 手动 `sudo systemctl restart rabbitbot-control-console.service` 后才会生效**；生效后可重复同一 `docker restart rabbitbot-audio` 测试，预期该窗口显示"启动中"而非"离线"。
- 顺带排查（Aaron 要求，现场新接入 REDMI 音箱与 DJI Mic Mini）：
  - **DJI Mic Mini（STT 输入）：确认正常**。`scripts/start_stt_funasr_app.bash` 启动前用 `sounddevice` 扫描设备并按名称关键字匹配，本次实测正确识别为 `hw:2,0`、导出 `INPUT_DEVICE_INDEX=24`，STT 日志 (`rabbitbot_stt.log`) 确认 `in_device_id: 24`。
  - **REDMI Speaker（TTS 输出）：确认不可达，两层原因**。①`docker-compose.decoupled.yaml` 里 `RABBITBOT_TTS_BACKEND` 默认写死为 `unitree`（`${RABBITBOT_TTS_BACKEND:-unitree}`），这个默认值先于 `scripts/start_tts_app.bash` 内部更智能的 `auto`（健康检查失败会自动回退本地设备）默认值生效，导致自动回退逻辑从未被触发；无机器人模式下调用 `/exec text_to_speech` 直接返回 `{"error":"Unitree G1 TTS 请求失败: returncode=127"}`。②即使回退到本地播放分支，REDMI 是通过蓝牙 A2DP 连接（`bluetoothctl`/`pactl` 可见 `bluez_sink.50_92_6A_86_78_D1.a2dp_sink`），只存在于宿主 PulseAudio/BlueZ 会话；`rabbitbot-audio` 容器只挂载了 `/dev/snd`（原始 ALSA），没有 Pulse/BlueZ 桥接，容器内 `sounddevice.query_devices()` 枚举不到 REDMI，本地设备扫描逻辑（`scan_once()`）最多只能落到 HDMI 或 Tegra APE 内置设备。实测：调用 `/exec text_to_speech` 前后 `pactl list short sinks` 中 REDMI 对应 sink 状态始终是 `SUSPENDED`，未收到任何音频。
  - **待 Aaron 决策**：REDMI 若要长期作为无机器人模式测试音箱，需要额外工作（把宿主 PulseAudio/BlueZ 桥接进容器，播放路径切到 `paplay`/pactl 感知的输出），工作量不小；若只是临时测试，可先把 `runtime/portable.env` 的 `RABBITBOT_TTS_BACKEND` 显式设为 `auto`，至少让现有健康检查回退逻辑生效、消除 `returncode=127` 报错（回退后会落到 HDMI/内置设备而非 REDMI，仍然没有声音，但行为更可预期）。本轮未改动任何 TTS 后端配置。

本轮更新（2026-07-02，模型按需自动下载）：
- 背景和目标：此前 `rabbitbot-control-console.service` 启动后，前端点“开始程序(无机器人模式)”会默认拉起 VLM/Embedding/STT，但 `deploy/ensure_models.sh` 又因 `RABBITBOT_ENABLE_VLM=0`、`RABBITBOT_ENABLE_STT=0` 在无参数时跳过下载，导致“运行时需要模型、下载脚本认为不需要模型”的配置错位。本轮目标是让 VLM/Embedding/STT 服务启动前自动检查并下载自身所需模型到项目根 `models/`。
- 已完成：`deploy/ensure_models.sh` 增加 `RABBITBOT_ENABLE_EMBEDDING` 支持、目标去重、关键文件完整性检查、半下载目录补齐下载、下载锁等待与耗时/阶段日志；VLM/Embedding 检查 `config.json`，SenseVoice 检查 `config.yaml`/`model.pt`/`am.mvn`，不再只凭目录非空判断模型存在。
- 已完成：`scripts_1/start_unified_integration_workflow.sh` 在单容器路径创建/启动基础服务前，按 `RABBITBOT_UNIFIED_START_VLM`、`RABBITBOT_UNIFIED_START_EMBEDDING`、`RABBITBOT_UNIFIED_START_STT` 自动调用 `deploy/ensure_models.sh` 下载 `qwen_vlm`、`qwen_embedding`、`sensevoice`；可通过 `RABBITBOT_AUTO_DOWNLOAD_MODELS=0` 显式禁用。
- 已完成：`scripts_1/start_nav_bridge_workflow_loop.sh` 的解耦 compose 路径在 `docker compose up` 前执行同样的模型检查/下载；`deploy/start_portable_stack.sh` 在启动 portable 基础服务前也会检查/下载模型。
- 已完成：解耦 compose 的 `/models` 挂载从旧 `/mnt/disk1/models` 改为 `${RABBITBOT_MODELS_CACHE_DIR:-/mnt/disk1/gt/air_robot_gt_projects/models}`，与下载位置统一到项目根 `models/`。
- 已完成：`runtime/portable.env.example`、`deploy/bootstrap_host.sh`、`third_party/manifest.lock` 将 VLM/Embedding/STT 默认改为启用，并加入 `RABBITBOT_AUTO_DOWNLOAD_MODELS=1`；当前目标机运行态 `runtime/portable.env` 也已同步为 `RABBITBOT_ENABLE_VLM=1`、`RABBITBOT_ENABLE_EMBEDDING=1`、`RABBITBOT_ENABLE_STT=1`、`RABBITBOT_AUTO_DOWNLOAD_MODELS=1`、`RABBITBOT_MODELS_CACHE_DIR=/mnt/disk1/gt/air_robot_gt_projects/models`。
- 已完成：`deploy/check_air_project.sh` 的 portable 模型策略检查改为验证自动下载链路和 `RABBITBOT_MODELS_CACHE_DIR` 挂载，不再要求构建机预先存在 `models/`。
- 已验证：远端 `bash -n` 覆盖 `deploy/ensure_models.sh`、`deploy/bootstrap_host.sh`、`deploy/start_portable_stack.sh`、`deploy/check_air_project.sh`、`scripts_1/start_unified_integration_workflow.sh`、`scripts_1/start_nav_bridge_workflow_loop.sh`；`python3 -m json.tool third_party/manifest.lock` 通过；`PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh` 通过；`docker compose -f docker-compose.decoupled.yaml config` 展开确认四个 core 容器的 `/models` 均挂载到 `/mnt/disk1/gt/air_robot_gt_projects/models`。
- 未完成/阻塞：未实际触发 Hugging Face 大模型下载，避免在本轮验证中长时间占用网络和磁盘；builder 模式自检仍因本机缺少 `/mnt/disk1/gt/air_robot_gt_projects/custom_action_ws/install/setup.bash` 失败，这是既有构建机外部产物缺失，和本轮模型下载链路无关。
- 建议下一步：如需立即启动导览，可直接点控制台“开始程序(无机器人模式)”或启动 `rabbitbot-loop.service`，首次启动会进入模型下载；下载过程会写入当前运行日志和 systemd 日志，下载完成后再拉起对应服务。若现场网络不可用，需先准备好 Hugging Face 模型缓存或手动拷贝完整模型目录。

实测（截至生成时间）：6 容器全部运行（neo4j/vlm/audio/memory healthy，navbridge/workflow 无 healthcheck 但 Up），7 端口（7687/8000/8005/28182/28184/28185/28180）全 up，`rabbitbot-loop.service` 按需启停（当前 inactive，compose 基础服务持续在线），`RABBITBOT_BASE_RUNTIME=compose`、`RABBITBOT_NAV_WORKFLOW_NO_ROBOT=1`。

已完成（本会话，`feature/memory-markdown-neo4j` 分支）：
- **记忆双来源合并**：新增 `rabbitbot/memory/markdown_memory.py::MarkdownMemoryStore`，扫描项目根目录 `memory/`（容器内 `/workspace/projects/memory`，与 `combined_data.json` 同级）下的 `.md` 文件，按标题（`#`~`######`）切分为片段，标题下正文超长再按空行分段；复用现有 `GRAPHITI_EMBD_MODEL`/`GRAPHITI_EMBD_MODEL_URL` embedding 服务计算片段向量，按文件 mtime 增量刷新（无需重启即可感知新增/修改/删除）。
- `AgentMemory`（`agent_memory.py`）新增 `query_combined(query, group_name, limit)`：并行整合 Neo4j 图检索与 markdown 检索；**Neo4j 查询抛异常或返回空列表时仅记 warning/debug 日志并忽略该来源**，不影响 markdown 结果、不向上抛异常。
- `memory_app.py` 的 `POST /query` 改为调用 `query_combined`，对 Neo4j 候选（沿用原按 `node.name` 重新计算相似度的方式）与 markdown 候选（复用检索时已基于分片全文计算的相似度，不再重复计算）合并取全局最高分，沿用原有响应 schema（`uuid/name/group_id/summary/attributes{location,image_path,description}`），**客户端 `provider.py::MemoryAgent` 无需改动**。markdown 命中时 `group_id="markdown"`、`location=None`，与 Neo4j 展点节点（有物理坐标）区分。
- 新增 `GET /memory_status` 诊断端点：返回 markdown 文档数/分片数与 Neo4j 连通性，便于排查"为什么没检索到"。
- 新建 `memory/README.md` 说明文档格式与生效方式；新增单元测试 `tests/memory/test_markdown_memory.py`（8 个用例：标题切分、长段落再切分、目录缺失降级、相似度排序、增量刷新增删改、单分片 embedding 失败不影响其它分片、无标题回退文件名）。
- **验证**：目标机 py310 环境无 `pytest` 且离线环境无法安装，已改为手动逐个调用 test_* 函数验证，8/8 通过；另在真实运行中的 `rabbitbot-memory` 容器内临时放入测试文档，`curl /query` 验证 markdown 来源命中（`group_id: markdown`）、`curl /memory_status` 验证文档计数正确，验证后已清理临时文档。uvicorn `--reload` 期间多次热重载均 `Application startup complete`，无导入/启动错误。
- **未变更范围**：`ctx.entity_lst`（`context.py` 启动时用 `get_group_names("展点")` 拉取的导航候选列表，供 `navi_check_execute` 的 `random.sample` 使用）仍只读 Neo4j，本轮未接入 markdown；Neo4j 展点为空时该处 `random.sample(ctx.entity_lst, num_entity)` 崩溃的已知 bug**依旧存在**（与本轮改的 `/query` 语义检索是不同代码路径），详见下方"已知未修 bug"。

已完成（此前会话）：
- 解耦多容器 + loop 对接解耦栈 + 真机模式 nav 协同（见上）。
- 日志统一搬到 air 根 `/mnt/disk1/gt/air_robot_gt_projects/logs`（容器内 `/workspace/projects/logs`），旧 `<project>/logs` 已删除；6 处“日志根”定义点统一改造（loop 入口/主循环/容器入口/控制台 config/compose/`rabbitbot/tools/logging.py`）。
- 控制台前端：无机器人按钮移到操作区最后；`config.py` 的运行容器名/nav 容器名随 `RABBITBOT_BASE_RUNTIME` 切换（compose→`rabbitbot-workflow`/`rabbitbot-navbridge`），“关闭程序”文案与操作随之正确。
- `get_inst_chat` 换成精简现场对话提示词；无机器人模式手臂动作在 `provider.py::_post_arm_action` 入口短路跳过（不再等 28180 超时）。
- 修复：①“开始程序”按钮触发的 workflow 残留死循环（`kill_stale_workflow` 按进程特征清理残留再启动）；②curl 注入文本被“低音量打断”忽略（STT 记录“上次消费是否注入”，注入时 `get_last_rms` 返回高哨兵 1.0）；③TTS(Kokoro) 本地模型路径错误致离线下载崩溃（默认改用 `RABBITBOT_MODELS_DIR`=`/models` 下的 `Kokoro-82M`）。
- 导览开场白被打断后**继续(resume)剩余开场白**：被打断→回答提问→重播本句→继续后续开场白，不再吞词（开场回答回调由调用点注入，因 guide_opening_speech 为模块级、取不到嵌套的 chat_execute）。
- 控制台服务状态面板：新增“启动中”黄色态（主循环启动 180s 窗口内、端口未就绪的服务显示“启动中”，窗口外才“离线”；后端 `ServiceStatus` 增 `state` 字段，按主循环进程 `/proc starttime` 判定启动窗口 `SERVICE_STARTUP_GRACE_SECONDS=180`）；并去除“开始程序”等待超时弹出的“服务仍未全部就绪”聚合提示（面板已逐服务展示状态）。新增 3 个状态判定测试，控制台测试 69 passed。
- 控制台“一键重启”按钮改名为“一键重启主循环”；`/api/restart` 不再硬编码真机模式，改为读取并沿用重启前的运行模式（无机器人模式则仍以无机器人模式重启 loop，避免一键重启把模式覆盖成真机），新增 `test_restart_preserves_no_robot_mode`，控制台测试 70 passed。
- 控制台服务状态面板为每个服务加“重启”按钮：弹“是否确认重启…服务？”确认框，同容器服务(TTS/STT、VLM/Embedding)额外提示一并重启；新增 `POST /api/service/restart`(按服务解析容器并 `docker restart -t 20`，免 sudo)，`ServiceStatus` 增 `container` 字段与 `resolve_service_container` 映射(随 `RABBITBOT_BASE_RUNTIME` 切换)，刚重启的容器在宽限期内其服务显示“启动中”。新增 5 个测试，控制台测试 75 passed。
- 修复服务重启按钮反馈延迟：端点改为先打“启动中”标记 + 后台异步 `docker restart` 并立即返回（不再被优雅停止 ~20s 阻塞 HTTP）；新增“强制启动中”窗口 `SERVICE_RESTART_FORCE_STARTING_SECONDS=22`（重启发起后即使旧端口仍开也优先显示“启动中”，覆盖 `docker stop` 时长）；前端点击确认后乐观地立即把同容器卡片标“启动中”。新增 force-starting 测试，控制台测试 76 passed。
- 进一步修复“重启后短暂闪回在线”：实测确认后端 `/api/status` 重启后 0~35s 全程返回“启动中”（后端无问题），根因是前端每 2s 轮询会重建卡片，而“点击前已在途、携带在线数据的轮询响应”在乐观标黄后才返回、重绘时盖回绿色；前端新增 `pendingRestartUntil`，点击后 22s 内该容器强制显示“启动中”、不被任何轮询响应覆盖（与后端 force 窗口对齐）。提醒：浏览器需硬刷新页面才能加载最新前端 JS。
- 部署链路适配解耦栈（原先解耦只在运行层，deploy/README 仍是单容器）：`README.md` 增「运行架构：解耦多容器栈」总览并修订端口拓扑/流程 B 启动/模型要求/env 约定；`runtime/portable.env.example` 补 `RABBITBOT_BASE_RUNTIME=compose` 与 `RABBITBOT_NEO4J_IMAGE`（全新 Orin 从模板生成的 env 默认即解耦栈）；`deploy/start_portable_stack.sh` 按 `RABBITBOT_BASE_RUNTIME` 分流（compose→`docker compose up docker-compose.decoupled.yaml`）；`deploy/export|import_portable_images.sh` 纳入 neo4j 官方镜像离线交付；`deploy/check_air_project.sh` 增 `docker-compose.decoupled.yaml` 存在性检查。`install_air_project.sh` 无需改（只装 systemd，容器由 loop 按 env 拉起）。已实测 compose 分支幂等启动 5 容器 healthy、neo4j 镜像就位、脚本 `bash -n` 通过；**全新 Orin 端到端冷启动未验证（本机为已部署机）**。
- 会前已完成：DJI Mic Mini 右声道 STT 输入修复（双声道按 RMS 选道、`STT_INPUT_GAIN=8.0`、新增 `get_last_rms` 诊断接口）。

未完成 / 待办：
- **控制台改动（`config.py` 容器名/日志路径、`status.py`/`app.py` 服务状态“启动中”态与去除聚合提示、本轮新增的控制台自身启动宽限期修复）需重启 `rabbitbot-control-console.service`（sudo）才生效，尚未重启。**
- REDMI 蓝牙音箱当前无法接收 TTS 音频（详见上方本轮更新），待 Aaron 决定处理方向后再动代码。
- 机器人离线：真机导航/返航、nav 核心 Pose/Ready 未端到端验证。
- 导览数据为空：`combined_data.json` 缺失 + Neo4j 展点 0 节点 → `navi_execute` 里 `ctx.memory.query()` 语义检索本轮已可回退到 markdown（`memory/` 目录下需要有对应展点文档才能命中，目前该目录只有 `README.md`，**尚未补充真实展点/业务 markdown 内容**），否则仍命中“异常结点”。
- 已知未修 bug（本轮未动，仍是不同代码路径）：`workflow.py::navi_check_execute` 的 `random.sample(ctx.entity_lst, num_entity)` 在 `ctx.entity_lst`（`context.py` 启动时 `get_group_names("展点")` 的结果，只读 Neo4j）为空时崩溃（“Sample larger than population”），挡住导览导航候选提示路径；`get_group_names`/`get_group_summary` 本轮未接入 markdown，需要的话应在这两个接口上做类似 `query_combined` 的合并。

## 已验证的事实

- nvidia 用户在 docker 组（免 sudo 跑 docker）；sudoers **仅** `systemctl start/restart/stop rabbitbot-loop.service` 免密；`rabbitbot-control-console.service` 重启需 sudo 密码（非交互无法执行，须 Aaron 手动）。
- Neo4j 凭据 `neo4j/neo4j_pass`；模型挂载 `/mnt/disk1/models` → 容器 `/models`；TTS 模型 = 本地 Kokoro-82M（中文音色 zm_yunxi，`/models/Kokoro-82M`）。
- 解耦栈实测通过：跨容器记忆写入/查询召回正确；loop(compose+无机器人)→workflow 在 `rabbitbot-workflow` 容器到 QA 待命、跨容器调 audio 容器 TTS 成功；TTS 本地模型加载无下载错误、`text_to_speech` 合成成功；STT 注入后 `get_last_rms` 由 0.0032 变 1.0；控制台测试 `66 passed`。
- STT 端口 28184，注入口令用 `/exec` 的 `inject_text_async`（与“对麦克风说话”同路径，被 `get_text_async` 消费）。
- 目标机 `rabbitbot-memory` 容器实际运行 Python 解释器是相对路径 `py310/bin/python`（cwd=`/workspace/projects/rabbitbot-dev-ros2-master`），内含 `graphiti-core 0.11.6`/`neo4j 6.0.2`，但**无 pytest 且 pip index（`pypi.jetson-ai-lab.dev`/`pypi.tuna.tsinghua.edu.cn`）在此机器上不可达，无法临时安装**；控制台测试此前能跑 76 passed 应是在另一个具备 pytest 的环境（如开发机或 `control_console_venv`，但该 venv 目前也未装 pytest），非本机 py310。后续如需在本机跑 pytest 套件，需先确认可用的 pytest 环境或离线 wheel 来源。
- markdown 记忆目录（`/mnt/disk1/gt/air_robot_gt_projects/memory`）已挂载进 `rabbitbot-vlm/audio/memory/workflow` 四个容器（原有 bind mount `/mnt/disk1/gt/air_robot_gt_projects:/workspace/projects`，无需新增挂载）；`/query` 端到端验证：临时写入 `memory/_verify_tmp.md`（含"斑马展台"内容，Neo4j 中不存在该节点），`curl /query` 正确返回 `group_id: markdown` 的匹配结果，验证后已删除该临时文件。
- `rabbitbot-audio` 容器内 STT 麦克风自动探测得到 DJI Mic Mini（PortAudio index 24，对应 `hw:2,0`；索引会随容器/设备重新枚举变化，以自动探测结果为准，不要硬编码）；REDMI 蓝牙音箱只存在于宿主 PulseAudio（`bluez_sink.50_92_6A_86_78_D1.a2dp_sink`），容器当前访问不到，`sounddevice` 设备列表里看不到它。
- 当前 `RABBITBOT_TTS_BACKEND` 实际生效值是 `unitree`（来自 compose 默认值，不是 `start_tts_app.bash` 脚本自身更智能的 `auto` 默认值），无机器人模式下调用会直接报错 `returncode=127`，不会自动回退本地播放。

## 阻塞问题

- 机器人离线：实机链路（eno1、Unitree DDS、导航核心、28180）无法端到端验证。
- 导览点位数据缺失（`combined_data.json` + Neo4j 展点为空 + `memory/` 目录尚无真实展点 markdown），叠加 `navi_check_execute` 的 `random.sample` 空列表崩溃，导致导览导航候选提示路径走不通（`navi_execute` 本身的语义检索已可回退 markdown，但巧妇难为无米之炊——没有内容可检索）。

## 建议的下一步

1. 重启控制台服务使 `config.py` 改动（容器名/日志路径）生效：`sudo systemctl restart rabbitbot-control-console.service`。
2. 在 `memory/` 目录下补充真实展点/业务 markdown 文档（参考 `memory/README.md` 的格式约定），让本轮新增的 markdown 检索真正发挥作用；或用 importer 把展点导入 Neo4j。
3. 修 `navi_check_execute` 的 `random.sample` 空列表崩溃（`ctx.entity_lst` 为空时的兜底分支），可考虑让 `get_group_names`/`get_group_summary` 也合并 markdown 来源（对齐本轮 `query_combined` 的思路）。
4. 机器人上线后：验证 `rabbitbot-navbridge` 输出 Pose/Ready、loop 进入真机导览与返航。
5. Aaron 决定 REDMI 蓝牙音箱的处理方向（桥接 PulseAudio/BlueZ 进容器 / 暂时把 `RABBITBOT_TTS_BACKEND` 设为 `auto` 消除报错 / 维持现状待真机上线后不再需要本地音箱）。
6. 控制台重启生效后，重跑一次 `docker restart rabbitbot-audio` 回归验证服务状态宽限期修复（预期离线窗口显示"启动中"而非"离线"）。

## 注意事项

- `RABBITBOT_BASE_RUNTIME=compose` 在 `runtime/portable.env`（本机配置，未入库；代码默认仍 `unified`）。回退旧单容器路径：改回 `unified`。
- 解耦栈与旧 `rabbitbot-unified-runtime` **互斥，勿同时启动**（host 网络端口冲突）；旧 unified 仅停未删，作回退。
- 日志属主：正常 loop 启动会先以 nvidia 建日志目录再起容器；若**手动 `docker compose up` 先于 loop**，docker 会以 root 建 air 根/logs 子目录致 loop(nvidia) 无法写，需 `docker exec <core 容器> chown -R 1000:1000 /workspace/projects/logs`。
- 无机器人开关 `RABBITBOT_NAV_WORKFLOW_NO_ROBOT=1`（兼容名 `RABBITBOT_WORKFLOW_NON_INTEGRATION`）；无机器人模式下手臂动作被跳过、不需 28180，可用 `RABBITBOT_ARM_ACTION_FORCE_WHEN_NO_ROBOT=1` 强制发送。
- 可调环境变量：`KOKORO_MODEL_DIR`（TTS 模型目录）、`STT_INJECTED_RMS`（注入哨兵音量，默认 1.0）、`STT_INPUT_GAIN`、`RABBITBOT_INTERRUPT_RMS_THRESHOLD`、`RABBITBOT_WORKFLOW_CONTAINER_NAME`。
- 服务状态面板是短超时端口探测，不等同于 systemd/Docker 状态。远端无 `rg`，用 `find`/`grep`。

## 关键文件与端口

- 解耦栈：`docker/portable/docker-compose.decoupled.yaml`、`scripts_1/unified_runtime/start_role_container.sh`、`start_unified_container.sh`。
- 编排：`scripts_1/start_loop_entry.sh`、`scripts_1/start_nav_bridge_workflow_loop.sh`。
- 控制台：`rabbitbot/control_console/{app,commands,config,status,dialogue}.py`；服务状态判定见 `status.py::get_runtime_service_statuses`（在线/启动中/离线三条宽限期信号：主循环启动、容器重启按钮、控制台自身启动）。
- 业务：`rabbitbot/agno_agents/{workflow,prompts}.py`、`rabbitbot/provider.py`、`stt_app_funasr.py`、`tts_app.py`、`rabbitbot/audio/run_tts_espnet.py`、`rabbitbot/tools/{sound_agno,logging}.py`。
- 音频设备自动探测：`scripts/start_stt_funasr_app.bash`（STT 输入设备扫描/`INPUT_DEVICE_INDEX`）、`scripts/start_tts_app.bash`（TTS 后端自动选择/输出设备扫描/`OUTPUT_DEVICE_INDEX`，含 unitree↔local 健康检查回退逻辑）。
- 记忆（本轮新增/改动）：`memory/`（项目根目录，markdown 文档存放处，含 `README.md`）、`rabbitbot/memory/markdown_memory.py`（新增）、`rabbitbot/memory/agent_memory.py::query_combined`、`memory_app.py`（`/query`、新增 `/memory_status`）、`tests/memory/test_markdown_memory.py`（新增）。
- 端口：Neo4j 7687 / VLM 8000 / Embedding 8005 / Memory 28182(`/memory_status` 可查记忆状态) / STT 28184 / TTS 28185 / Robot Agent·nav 28180 / 控制台 8080。

## 最近历史摘要（提交）

- 控制台服务状态"启动中"宽限期补充控制台自身启动信号，覆盖 Orin 整机重启场景（本轮提交）
- `3e135c6` 修复关闭程序的多容器重启逻辑
- `df752a1` 修复模型服务启动前的按需下载
- `15509e9` 合并阶段功能更新到 master
- `81f6cfa` 记忆系统支持 markdown 文档与 Neo4j 知识图谱双来源检索
- `573e753` 部署链路适配容器解耦：README + portable.env.example + start_portable_stack.sh + export/import + check 改用 compose 解耦栈
- `97ef15a` 修复“重启后前端短暂闪回在线”：前端加本地强制启动中窗口 `pendingRestartUntil`，不被在途轮询响应覆盖
- `02e5dcd` 修复服务重启按钮反馈延迟：先标记+后台异步重启+立即返回，新增强制启动中窗口与前端乐观更新
- `73982f0` 控制台服务状态面板每服务加“重启”按钮（重启对应容器/服务，TTS/STT 等同容器提示一并重启）
- `6761317` “一键重启”改名“一键重启主循环”并沿用重启前运行模式（无机器人模式不再被覆盖成真机）
- `c0bda9e` 控制台服务状态新增“启动中”黄色态、去除“服务仍未全部就绪”提示（含 3 个状态测试）
- `3a9e05d` 开场打断回答失败(NameError)修复：回答回调由调用点注入
- `33c6bb7` 开场白被打断后继续剩余开场白(resume)，不再吞词
- `e396078` TTS(Kokoro) 本地模型路径修复（离线本地加载）
- `dbf6f6b` 注入文本被“低音量打断”忽略修复
- `1f03820` “开始程序”按钮 workflow 残留死循环修复
- `dedea04` 日志统一迁移到 air 根并清理旧日志
- `adef602` 控制台前端适配解耦栈（容器名/文案随运行方式）
- `4d14a51` 真实机器人模式 nav 与解耦 compose 协同
- `4f156b3` loop 基础服务依赖解耦 compose、workflow 专用容器
- `64c4cdd` 解耦统一容器为五个独立容器(docker-compose)
- 更早：`6cd1543` get_inst_chat 精简提示词；`74ed6bf` 无机器人跳过手臂动作；`080a224` 控制台按钮顺序；`e67ee72` DJI 右声道 STT 修复；以及 TTS 声卡回退、Embedding/VLM 默认启用、当前运行日志面板、返航、portable core/nav 镜像、systemd/sudoers 治理（均已压缩，详见 git log）。

生成时间：2026-07-02（本轮更新：控制台服务状态宽限期修复、音频设备排查）
