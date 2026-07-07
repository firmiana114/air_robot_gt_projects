# air_robot_gt_projects 交接报告

## 项目整体描述

本仓库是 RabbitBot 机器人现场导览项目，目标机路径通常为 `/mnt/disk1/gt/air_robot_gt_projects`，当前重点分支为 `lanshi`。项目用于机器人导览、问答、导航桥接、TTS/STT、VLM/Embedding、Memory/Neo4j、动作控制和局域网 Web 控制台。

核心代码位于 `rabbitbot-dev-ros2-master/`，Python 包为 `rabbitbot`。前端控制台不是独立 Node/Vite 项目，而是 `rabbitbot/control_console/app.py` 中 FastAPI 内嵌 HTML/CSS/原生 JavaScript，并由 `rabbitbot-control-console.service` 或 `scripts_1/start_control_console.sh` 启动。

主要模块和目录：
- `rabbitbot-dev-ros2-master/rabbitbot/control_console/`：本轮修改重点，FastAPI 控制台、状态查询、台词编辑、开机自启动和容器重启接口。
- `rabbitbot-dev-ros2-master/rabbitbot/agno_agents/`：导览、QA 和 workflow 逻辑。
- `rabbitbot-dev-ros2-master/rabbitbot/robots/`：机器人动作、导航和任务管理封装。
- `rabbitbot-dev-ros2-master/scripts_1/`：现场主启动/停止/诊断脚本；当前项目版本未确认是否包含参考项目的 `guide_state` 写入逻辑。
- `rabbitbot-dev-ros2-master/scripts/`：TTS/STT/VLM/robot app 等专项入口。
- `rabbitbot-dev-ros2-master/conf/`：导览 JSON 配置，控制台热更新读写 `dialogue_*.json`。
- `rabbitbot-dev-ros2-master/docker/portable/`：portable/compose 解耦运行时配置。
- `rabbitbot-dev-ros2-master/tests/control_console/`：控制台相关测试。
- `deploy/`：宿主安装、检查、镜像导入导出和 systemd 部署脚本。
- `logs/`、`runtime/`：运行日志和运行态配置；真实现场文件通常不入 Git。

主要技术栈：Python 3.10+、FastAPI、Pydantic、Uvicorn、pytest、ROS2 Humble、Docker Compose、Neo4j、Unitree/Kuavo 动作与导航接口。模型、ROS action 工作区和现场设备依赖完整性未确认。

核心数据流：
1. 浏览器访问控制台 8080，控制台调用 `/api/status` 展示主循环、导航桥接、workflow、定位和服务状态。
2. 控制台“导览/返航/重启/关闭/自启动”等按钮调用白名单 API，再由 `systemctl`、Docker 或 `send_nav_workflow_command.sh` 执行。
3. 点位台词页面读写 `conf/dialogue_*.json`，下一次导览读取更新后的 opening、steps、points 和 `variables.leader_calling`。
4. 导览 workflow 通过导航桥接 28180、TTS/STT/VLM/Memory 等服务完成讲解、导航和交互。

常用命令：
- 控制台入口：`bash rabbitbot-dev-ros2-master/scripts_1/start_control_console.sh`
- 主循环入口：`bash rabbitbot-dev-ros2-master/scripts_1/start_loop_entry.sh`
- 控制台检查：`python3 -m py_compile rabbitbot-dev-ros2-master/rabbitbot/control_console/app.py`
- 控制台测试：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest rabbitbot-dev-ros2-master/tests/control_console/test_app.py rabbitbot-dev-ros2-master/tests/control_console/test_commands.py rabbitbot-dev-ros2-master/tests/control_console/test_status.py`

## 本轮修改

- 本轮追加修改：local TTS 默认改为使用系统默认音频输出，不再默认扫描 BT67 或绑定 sounddevice index。
- `scripts/start_tts_app.bash` 在 local 后端下默认设置 `RABBITBOT_TTS_USE_SYSTEM_DEFAULT=1` 且清空 `OUTPUT_DEVICE_INDEX`，由系统默认输出设备播放。
- `rabbitbot/audio/run_tts_espnet.py` 在未传指定设备 index 且 `RABBITBOT_TTS_USE_SYSTEM_DEFAULT=1` 时，通过 `sd.query_devices(None, 'output')` 和 `sd.OutputStream(device=None, ...)` 打开系统默认输出。
- 如需恢复旧的按设备名/index 扫描逻辑，可设置 `RABBITBOT_TTS_USE_SYSTEM_DEFAULT=0`，再配置 `TTS_DEVICE_NAME` 等旧变量。
- 将当前项目控制台前端同步为 `/Users/firmiana/Desktop/rabbitbot-dev-ros2-master` 参考项目风格：左侧导航、顶部状态条、任务控制科技风大屏、机器人展示图、机器人状态页、点位台词页和模型服务页。
- 新增静态资源挂载 `/static/control_console`，页面引用 `rabbitbot/control_console/static/unitree-g1-dashboard.png`。
- 同步参考项目的点位台词热更新与嘉宾称呼功能：新增 `/api/dialogue/hot-rows`、`/api/dialogue/leader-calling`，支持从当前定位位姿回填坐标。
- 新增 `/api/autostart` 与 `loop_service_autostart_enabled`/`set_loop_service_autostart`，支持前端开关 `rabbitbot-loop.service` 开机自启动。
- 保留当前项目已有能力：`/api/service/restart` 后台重启服务容器、`/api/start-no-robot`、无机器人模式、portable nav 容器日志回退、runtime 日志查询和关闭程序时重启项目相关容器。
- 增加 `guide_state_file` 配置；若当前项目没有参考项目的 `guide_state` 文件，但 workflow 已 ready，则 API 兼容推断为 `qa_listening`，避免导览按钮被永久禁用。
- 更新控制台页面测试断言以匹配新 UI。

## 当前状态

- 代码已完成修改。
- `HANDOFF_REPORT.md` 已更新。
- 需要提交本轮修改；静态图片目录被 `.gitignore` 忽略，提交时需 `git add -f rabbitbot-dev-ros2-master/rabbitbot/control_console/static/unitree-g1-dashboard.png`。

## 已验证事实

- 已执行 `python3 -m py_compile rabbitbot-dev-ros2-master/rabbitbot/audio/run_tts_espnet.py rabbitbot-dev-ros2-master/tts_app.py`，语法检查通过。
- 已执行 `bash -n rabbitbot-dev-ros2-master/scripts/start_tts_app.bash`，脚本语法检查通过。
- 已执行 `python3 -m py_compile` 覆盖 `app.py`、`dialogue.py`、`commands.py`、`status.py`、`config.py` 和控制台测试文件，语法检查通过。
- 当前系统 Python 缺少 `pytest` 和 `fastapi`，无法在本机用当前解释器运行 FastAPI TestClient 或 pytest。
- 已确认当前项目不是 Node/Vite 前端，页面由 FastAPI 内嵌 HTML/CSS/JS 提供。
- 已确认参考项目包含控制台静态图片，当前项目静态目录此前不存在且被 Git 忽略。
- 本轮未启动控制台服务、未访问真实 8080 页面、未发送 go/back、未移动机器人。

## 阻塞问题

- 本机缺少 `pytest`、`fastapi`，控制台单测和运行时接口自检未能执行。
- 当前项目版本未确认是否有脚本写入 `runtime/nav_workflow_control/guide_state`；已通过 workflow ready 回退兼容，但现场若要完全复刻参考项目状态语义，需确认或移植参考脚本的 guide_state 写入逻辑。
- 未做浏览器视觉验收；需启动控制台后确认静态机器人图片可加载、移动端布局可用。

## 下一步

1. 在具备依赖的环境运行控制台 pytest 命令。
2. 启动 `rabbitbot-control-console.service` 或脚本入口，浏览器打开 `http://<orin-ip>:8080` 做视觉和按钮可用性检查。
3. 在现场确认点位台词热更新写入 `conf/dialogue_0.json` 后，下一次导览能读取新点位和嘉宾称呼。
4. 如需严格对齐参考项目导览阶段展示，继续检查 `scripts_1/start_nav_bridge_workflow_loop.sh` 是否应同步 `guide_state` 写入逻辑。

## 注意事项

- 系统默认音频由宿主或容器内 ALSA/PulseAudio/PipeWire 默认输出决定；如果默认输出设错，TTS 会播到系统当前默认设备。
- Docker 场景仍需保证容器能访问系统音频设备或音频服务，否则系统默认输出打开会失败并记录异常。
- 不要把真实 `runtime/portable.env`、日志、大模型缓存或密钥类配置提交到 Git。
- `/api/service/restart` 会重启服务所在 Docker 容器；TTS/STT 同容器时会一并受影响。
- 点位台词保存会备份原 JSON，日志只记录路径、行数、点位 key 和错误类型，不记录完整台词或大段 JSON。
- 控制台“任务控制”页中的机器人状态、运动状态、任务信息、导航地图和语音交互为展示型模块，页面中标注“开发中”；真正联动的是底部导览、返航、重启、关闭和自启动按钮。
