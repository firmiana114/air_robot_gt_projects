# 交接报告

## 项目整体描述

RabbitBot 是面向人形机器人导览、问答、导航和动作控制的 Python/ROS2 项目。核心功能包括：导览 workflow、TTS/STT 音频服务、VLM/Embedding、Neo4j 记忆服务、机器人导航桥接、手臂动作桥接、Web 控制台和若干现场启动脚本。

主要技术栈：Python 3.10+、FastAPI、ROS2 Humble、Docker Compose、Neo4j、Qwen/VLM 服务、Unitree/Kuavo 机器人动作与导航接口。部分底层动作源码位于同级工作区 `unitree_slam_example_new/example`，不在本仓库包内但与本项目运行链路耦合。

关键目录结构：

- `rabbitbot/`：主 Python 包，包含 agents、robots、tools、control_console 等模块。
- `scripts_1/`：现场主要启动/停止/诊断脚本；`start_lanshi_product_guide.py` 是兰石原地产品介绍循环脚本。
- `scripts/`：旧版或专项启动脚本，包括 TTS/STT/VLM/robot app 等。
- `docker/portable/`：portable 解耦运行时与 nav bridge 容器配置。
- `conf/`：导览台词与配置文件；部分 dialogue 文件可能被 `.gitignore` 忽略，仅现场保留。
- `docs/`：导览 workflow、机器人、音频、VLN、YOLO 等说明文档。
- `tests/`：单元测试与控制台测试。
- `runtime/`：运行态环境模板；真实 `portable.env` 通常不入 Git。

主要运行入口：

- 兰石原地导览：`python3 scripts_1/start_lanshi_product_guide.py`，通常由主循环/容器启动链路间接运行。
- 主循环入口：`bash scripts_1/start_loop_entry.sh`。
- 导航桥接 workflow loop：`bash scripts_1/start_nav_bridge_workflow_loop.sh`。
- 控制台：`bash scripts_1/start_control_console.sh`。
- Robot Agent：`robot_app.py`，对外提供 `/do_arm_async`、`/go_to_async` 等接口。

核心数据流：

1. 导览脚本或 workflow 生成台词和动作名。
2. TTS 请求发往 `28185`，逐句提交并等待播放完成。
3. 手臂动作通过 Robot Agent `28180 /do_arm_async` 发送，动作名字符串透传给 ROS2 `NaviArm` action client。
4. 底层 arm action server 执行动作；`release` 或别名可用于收回动作。
5. 导航/记忆/VLM 在完整 workflow 中通过对应服务端口和 Docker Compose 解耦容器协作。

重要配置文件：

- `kuavo_configs.json`：机器人 ROS/VLN/相机和远端服务开关。
- `runtime/portable.env.example`：portable 运行模式环境变量模板。
- `docker/portable/docker-compose.decoupled.yaml`：Neo4j、VLM、audio、memory、workflow、navbridge 解耦容器。
- `pyproject.toml`：Python 包和依赖声明。

外部依赖：ROS2 Humble、自定义 action workspace、Unitree/Kuavo 底层动作与导航程序、Docker/NVIDIA runtime、Neo4j、模型缓存目录、TTS/STT/VLM/Embedding 模型。部分现场路径和模型完整性未确认。

常用命令：

- 安装开发包：`uv venv && uv pip install -e .`
- 单元测试：`python -m unittest discover tests -v`
- 语法检查示例：`python3 -m py_compile scripts_1/start_lanshi_product_guide.py`
- 启动主循环：`bash scripts_1/start_loop_entry.sh`

部署或运行方式：现场优先使用 portable/compose 解耦运行时；兰石原地导览模式只依赖 TTS `28185` 和动作桥接 `28180`，会跳过 VLM、Embedding、STT、Memory。

## 本轮修改

- 控制台前端已同步为 `/Users/firmiana/Desktop/rabbitbot-dev-ros2-master` 参考项目风格：左侧导航、顶部状态条、任务控制科技风大屏、机器人展示图、机器人状态页、点位台词页和模型服务页。
- 新增静态资源挂载 `/static/control_console`，页面使用 `rabbitbot/control_console/static/unitree-g1-dashboard.png`。
- 同步参考项目点位台词热更新与嘉宾称呼功能，新增 `/api/dialogue/hot-rows`、`/api/dialogue/leader-calling`，支持从当前定位位姿回填坐标。
- 新增 `/api/autostart` 与开机自启动查询/设置函数，前端可启用或关闭 `rabbitbot-loop.service` 自启动。
- 保留当前项目已有控制台能力：服务容器后台重启、无机器人模式、portable nav 容器日志回退、runtime 日志和关闭程序时重启项目相关容器。
- 增加 `guide_state_file` 配置；如果当前项目没有参考项目的 `guide_state` 文件但 workflow ready，会兼容推断为 `qa_listening`，避免导览按钮不可用。
- 更新控制台页面测试断言以匹配新 UI。

## 当前状态

- 代码已修改并通过语法检查。
- 根目录和子项目 `HANDOFF_REPORT.md` 已更新。
- 本轮相关修改待整理为一次 Git 提交；静态图片目录被 `.gitignore` 忽略，提交时需强制 add 图片文件。

## 已验证事实

- 已执行 `python3 -m py_compile rabbitbot/control_console/app.py rabbitbot/control_console/dialogue.py rabbitbot/control_console/commands.py rabbitbot/control_console/status.py rabbitbot/control_console/config.py tests/control_console/test_app.py tests/control_console/test_commands.py tests/control_console/test_status.py`，语法检查通过。
- 当前系统 Python 缺少 `pytest` 和 `fastapi`，无法在本机用当前解释器运行控制台 pytest 或 FastAPI TestClient。
- 已确认本项目控制台前端是 FastAPI 内嵌 HTML/CSS/原生 JavaScript，不是独立 Node/Vite 项目。
- 已确认参考项目静态机器人图片已复制到当前项目，但该目录默认被 Git 忽略。
- 本轮未启动控制台服务、未发送 go/back、未移动机器人。

## 阻塞问题

- 本机缺少 `pytest`、`fastapi`，控制台单测和运行时接口自检未能执行。
- 当前项目版本未确认是否有脚本写入 `runtime/nav_workflow_control/guide_state`；已做 workflow ready 回退兼容，若要完全复刻参考项目状态语义，需继续核对或移植参考脚本的 `guide_state` 写入逻辑。
- 未做浏览器视觉验收；需启动控制台后确认静态图片可加载、布局与参考项目一致。

## 下一步

- 在具备依赖的环境运行 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/control_console/test_app.py tests/control_console/test_commands.py tests/control_console/test_status.py`。
- 启动 `scripts_1/start_control_console.sh` 或 `rabbitbot-control-console.service`，浏览器打开 8080 验收页面。
- 在网页保存一次点位台词和嘉宾称呼，确认 `conf/dialogue_0.json` 写入、备份和下一次导览读取正常。
- 如需严格对齐参考项目导览阶段展示，继续检查 `scripts_1/start_nav_bridge_workflow_loop.sh` 是否应同步 `guide_state` 写入逻辑。

## 注意事项

- 不要提交真实 `runtime/portable.env`、日志、大模型缓存或密钥类配置。
- `/api/service/restart` 会重启服务所在 Docker 容器；TTS/STT 同容器时会一并受影响。
- 点位台词保存会备份原 JSON，日志只记录路径、行数、点位 key 和错误类型，不记录完整台词或大段 JSON。
- 控制台“任务控制”页中的机器人状态、运动状态、任务信息、导航地图和语音交互为展示型模块，页面中标注“开发中”；真正联动的是底部导览、返航、重启、关闭和自启动按钮。

## 历史近期工作压缩记录

- 2026-07-02 至本轮前：历史记录主要围绕 portable/compose 解耦运行时、控制台服务重启、导航桥接、DOCX workflow、动作链路、TTS/STT/VLM/Memory/Neo4j 启动与现场排障；详细历史如需追溯请查看 Git 历史中的旧版 `HANDOFF_REPORT.md`。
