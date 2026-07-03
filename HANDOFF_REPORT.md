# air_robot_gt_projects 交接报告

## 项目整体描述

本仓库是 RabbitBot 机器人现场导览项目，目标机路径为 `/mnt/disk1/gt/air_robot_gt_projects`，当前重点分支为 `lanshi`，用于兰石企业产品导览。核心代码位于 `rabbitbot-dev-ros2-master/`，Python 包为 `rabbitbot`，主要通过 `rabbitbot-control-console.service` 提供前端控制台（8080），通过 `rabbitbot-loop.service` 启动导览主循环。

主要模块：
- `rabbitbot-dev-ros2-master/scripts_1/`：systemd 主循环入口、导航桥接与 workflow 编排脚本。
- `rabbitbot-dev-ros2-master/scripts_1/start_lanshi_product_guide.py`：兰石原地循环导览脚本。
- `rabbitbot-dev-ros2-master/rabbitbot/control_console/`：前端控制台后端，负责开始/关闭程序、状态查询、容器重启。
- `rabbitbot-dev-ros2-master/docker/portable/docker-compose.decoupled.yaml`：解耦容器栈配置。
- `rabbitbot-dev-ros2-master/tests/control_console/`：控制台相关测试。
- `runtime/portable.env`：目标机本地运行配置，未入库；`runtime/portable.env.example` 是模板。
- `logs/`：运行日志目录。

主要技术栈：Python、Bash、Docker Compose、systemd、ROS/导航桥接、HTTP TTS/动作接口。外部依赖包括 Docker、GitHub 仓库、TTS 服务 28185、Robot Agent/动作桥接 28180；VLM/Embedding/STT/Memory 在兰石模式下默认不启动。

核心数据流（兰石分支）：前端或终端启动 `rabbitbot-loop.service` -> `start_loop_entry.sh` 默认启用 `RABBITBOT_LANSHI_GUIDE_MODE=1` -> `start_nav_bridge_workflow_loop.sh` 仅拉起兰石相关容器与动作桥接 -> `start_lanshi_product_guide.py` 按句调用 TTS `/exec` 流式播报，并穿插 28180 动作请求 -> 播完后等待 5 秒循环。

## 当前状态

- 当前分支：`lanshi`，基于 `cb97945 调整TTS音频设备选择顺序为auto` 创建，专门服务兰石企业导览。
- 最新已提交功能：兰石原地循环导览、默认进入兰石模式、关闭 VLM/Embedding/STT/Memory、前端“关闭程序”仅重启 `rabbitbot-audio`、`rabbitbot-workflow`、`rabbitbot-navbridge`，根 `README.md` 改为兰石现场快速启动文档。
- 本次待提交文档微调：`README.md` 中前端访问地址从固定 IP 改为 `http://<orin的ip>:8080`，方便现场 IP 变化时使用。
- `ShuHao-orin` SSH 配置已由用户更新；此前确认旧 IP `192.168.101.111` 的 SSH 指纹迁移到 `192.168.101.100`。
- `new-orin` 上曾临时创建 `lanshi` 分支并出现部分写入，后续如继续同步需先检查其工作区，尤其不要删除既有未跟踪文件 `memory/test_memory_markdown.md`。

## 已验证事实

- `ShuHao-orin` 当前可通过 SSH 登录，项目目录存在，`lanshi` 分支 HEAD 为 `cc4b543 改写兰石现场启动说明`，提交链包含 `9c4adcf`、`080b24f`、`cc4b543`。
- 本机代理监听 `127.0.0.1:1082` 可通过 HTTP 代理访问 GitHub，适合用 SSH 远程端口转发给 Orin 推送 GitHub。
- 已验证过的代码检查：兰石导览相关脚本 `bash -n` / `py_compile`、compose config、`git diff --check`；控制台相关定向测试曾通过 30 项。完整控制台测试此前有 2 个既有隔离问题，不属于本轮兰石改动。
- 控制台如果已在运行，Python 代码更新后需要重启 `rabbitbot-control-console.service` 才能让“关闭程序”容器范围变化生效。

## 阻塞问题

- 尚未在现场实际启动 `rabbitbot-loop.service` 跑完整兰石循环，TTS 音量、28180 动作名称与现场动作库仍需实机确认。
- GitHub 推送依赖本机 Shadowrocket/代理端口转发和远端 GitHub 凭据；若凭据失效，推送会在认证阶段失败。
- `new-orin` 同步工作尚未完成；本次用户当前只要求先推送 `ShuHao-orin` 上的 `lanshi` 分支。

## 下一步

1. 在 `ShuHao-orin` 提交 README 地址占位符和本交接报告压缩更新。
2. 用 SSH remote forward 将 `ShuHao-orin:127.0.0.1:17890` 转发到本机 `127.0.0.1:1082`。
3. 在 `ShuHao-orin` 上通过 `HTTPS_PROXY=http://127.0.0.1:17890` 推送 `lanshi` 到 GitHub。
4. 推送后如继续同步 `new-orin`，在 `/mnt/disk1/gt/air_robot_gt_projects` 先检查工作区，再 fetch/pull `origin/lanshi`。

## 注意事项

- 现场前端启动：浏览器打开 `http://<orin的ip>:8080`，点击“开始程序”。“开始程序（无机器人）”只适合 TTS 测试，不适合动作展示。
- 终端启动：`sudo systemctl start rabbitbot-loop.service`；停止：`sudo systemctl stop rabbitbot-loop.service`。
- 查看日志：当前运行日志通常在 `/mnt/disk1/gt/air_robot_gt_projects/logs/current_runtime.log`，systemd 日志用 `journalctl -u rabbitbot-loop.service -f`。
- 兰石模式默认不启动 VLM、Embedding、STT、Memory；如要回到原导览模式，需要显式设置或切换分支，避免和兰石现场配置混用。
- 不要清理用户未跟踪文件；遇到 dirty worktree 先看 diff 再处理。

## 最近历史摘要

- `cc4b543` 改写兰石现场启动说明。
- `080b24f` 限制兰石关闭程序的容器重启范围。
- `9c4adcf` 新增兰石原地循环导览模式。
- 更早的内存、解耦容器、音频设备、模型下载等历史已压缩，必要时用 `git log --oneline --decorate --all` 和对应提交查看。
