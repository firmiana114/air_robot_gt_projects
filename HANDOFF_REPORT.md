# air_robot_gt_projects 交接报告

## 背景和目标

本仓库是 RabbitBot 机器人现场导览项目，目标机路径为 `/mnt/disk1/gt/air_robot_gt_projects`，当前重点分支为 `lanshi`，用于兰石企业导览。核心代码位于 `rabbitbot-dev-ros2-master/`，Python 包为 `rabbitbot`，主要通过 `rabbitbot-control-console.service` 提供前端控制台（8080），通过 `rabbitbot-loop.service` 启动导览主循环。

本轮目标：根据用户上传的 `绿色低碳智慧后勤管理平台修改稿终版.docx`，将兰石原地导览讲解词替换为更完整的绿色低碳智慧化校园管理服务平台版本，并让单轮讲解从第一个字开始到最后一个字结束的计划时长为 5 分 15 秒（315 秒）。

主要模块：
- `rabbitbot-dev-ros2-master/scripts_1/`：systemd 主循环入口、导航桥接与 workflow 编排脚本。
- `rabbitbot-dev-ros2-master/scripts_1/start_lanshi_product_guide.py`：兰石原地循环导览脚本，本轮修改点。
- `rabbitbot-dev-ros2-master/rabbitbot/control_console/`：前端控制台后端，负责开始/关闭程序、状态查询、容器重启。
- `rabbitbot-dev-ros2-master/docker/portable/docker-compose.decoupled.yaml`：解耦容器栈配置。
- `rabbitbot-dev-ros2-master/tests/control_console/`：控制台相关测试。
- `runtime/portable.env`：目标机本地运行配置，未入库；`runtime/portable.env.example` 是模板。
- `logs/`：运行日志目录。

核心数据流（兰石分支）：前端或终端启动 `rabbitbot-loop.service` -> `start_loop_entry.sh` 默认启用 `RABBITBOT_LANSHI_GUIDE_MODE=1` -> `start_nav_bridge_workflow_loop.sh` 仅拉起兰石相关容器与动作桥接 -> `start_lanshi_product_guide.py` 按句调用 TTS `/exec` 流式播报，并穿插 28180 动作请求 -> 单轮结束后等待 5 秒循环。

## 当前状态

- 当前分支：`lanshi`，修改前 HEAD 为 `d8f31e4 更新兰石现场文档地址说明`。
- 本轮已将 `start_lanshi_product_guide.py` 中旧的 5 句简介替换为 DOCX 正文对应的 29 段讲解词，内容覆盖平台背景、数字孪生、设备管理、能源管理、安环管理和结尾总结。
- 本轮新增单轮时长控制：默认 `RABBITBOT_LANSHI_TARGET_ROUND_SECONDS=315.0`，按当前 Unitree TTS 等待估算参数计算播报时长，并把差额补齐到句间停顿中；默认启用 `RABBITBOT_LANSHI_PACING_ENABLED=1`。
- 当前计划时长计算结果：29 段、可见字符 1283 个、估算纯播报 279.8 秒、基础句间停顿 5.6 秒、额外补齐 29.6 秒、计划总时长 315.0 秒。
- 为避免单句超过 Unitree 本体 TTS 等待估算的 30 秒上限，已将 DOCX 第一段长句拆成两个连续播报段，文字内容未删减。
- 本轮未启动真实导览，未触发 TTS 播报或机器人动作。

## 已验证的事实

- 已从用户上传 DOCX 中抽取正文，确认标题为“绿色低碳智慧化校园管理服务平台”，正文与本轮替换后的讲解词一致。
- 已执行 `python3 -m py_compile rabbitbot-dev-ros2-master/scripts_1/start_lanshi_product_guide.py`，语法检查通过。
- 已执行脚本内时长计划校验：`planned_total=315.000`、`target=315.000`、`drift=0.000000`。
- 已执行 `git diff --check`，未发现空白错误。
- 代码日志点已覆盖本轮新增关键路径：导览启动目标时长、轮次计划、每句 TTS 提交/完成耗时、句间节奏补齐等待、轮次结束实际耗时和偏差。

## 阻塞问题

- 尚未在现场实际启动 `rabbitbot-loop.service` 跑完整兰石循环，因此 315 秒目前是基于脚本和 Unitree TTS 等待估算的计划时长；如机器人本体实际发声速度与估算差异较大，需要现场根据日志中的 `drift` 调整 `RABBITBOT_LANSHI_ESTIMATED_CHARS_PER_SECOND` 或目标时长参数。
- 当前机器此前观察到 `rabbitbot-loop.service` 和 `rabbitbot-control-console.service` 为 inactive，28185 TTS、28180 动作桥接和 8080 控制台端口未监听；本轮未处理服务启动问题。
- 当前机器此前观察到旧容器 `rabbitbot-tts` / `rabbitbot-stt` 处于重启状态，且角色入口只接受 `vlm | audio | memory`；如果现场启动仍失败，优先清理旧音频容器并按当前 compose 设计拉起 `rabbitbot-audio`。

## 建议的下一步

1. 提交本轮修改后，在现场启动前确认容器名与当前 compose 一致，重点看 `rabbitbot-audio`、`rabbitbot-workflow`、`rabbitbot-navbridge`。
2. 启动 `rabbitbot-control-console.service` 后，通过前端点击“开始程序”或执行 `sudo systemctl start rabbitbot-loop.service`。
3. 首轮播放时关注 `logs/current_runtime.log` 或 `logs/nav_workflow_control/rabbitbot_workflow_latest.log` 中的 `planned_total`、`elapsed`、`drift`，确认实际单轮是否接近 315 秒。
4. 若实际偏快或偏慢，优先通过环境变量微调 `RABBITBOT_LANSHI_ESTIMATED_CHARS_PER_SECOND`；数值越大，估算播报越短，句间补齐越长。
5. 如果 TTS 或动作不可用，先恢复 28185 和 28180，再验证讲解词时长。

## 注意事项

- 现场前端启动：浏览器打开 `http://<orin的ip>:8080`，点击“开始程序”。“开始程序（无机器人）”只适合 TTS 测试，不适合动作展示。
- 终端启动：`sudo systemctl start rabbitbot-loop.service`；停止：`sudo systemctl stop rabbitbot-loop.service`。
- 查看日志：当前运行日志通常在 `/mnt/disk1/gt/air_robot_gt_projects/logs/current_runtime.log`，systemd 日志用 `journalctl -u rabbitbot-loop.service -f`。
- 兰石模式默认不启动 VLM、Embedding、STT、Memory；如要回到原导览模式，需要显式设置或切换分支，避免和兰石现场配置混用。
- 不要清理用户未跟踪文件；遇到 dirty worktree 先看 diff 再处理。

## 最近历史摘要

- 本轮：替换兰石讲解词为 DOCX 完整版，并新增 315 秒单轮节奏控制和诊断日志。
- `d8f31e4` 更新兰石现场文档地址说明。
- `cc4b543` 改写兰石现场启动说明。
- `080b24f` 限制兰石关闭程序的容器重启范围。
- `9c4adcf` 新增兰石原地循环导览模式。
- 更早的内存、解耦容器、音频设备、模型下载等历史已压缩，必要时用 `git log --oneline --decorate --all` 和对应提交查看。
