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

- 将 `scripts_1/start_lanshi_product_guide.py` 的兰石默认穿插动作从 `high_wave` 替换为 `双手平摊开掌心向上`。
- `DEFAULT_ACTIONS` 当前为 `["face_wave", "right_hand_up", "", "right_hand_up", "双手平摊开掌心向上"]`。
- 本轮未新增日志；该脚本已有 INFO/WARN 日志会打印动作触发、动作返回和失败上下文。

## 当前状态

- 代码已修改并通过语法检查。
- `HANDOFF_REPORT.md` 已按超过 150 行需压缩的规则重写为精简版。
- 本轮相关修改已整理为一次 Git 提交。

## 已验证事实

- `双手平摊开掌心向上` 是底层自定义动作解析支持的中文别名，会映射到 `both_hands_stable`。
- 兰石脚本动作链路不做本地白名单校验，只把动作名通过 HTTP 表单字段 `task` 发给 `/do_arm_async`。
- `start_lanshi_product_guide.py` 语法检查通过。
- 本轮未启动真实 TTS、Robot Agent 或 ROS2 action server，未做真机动作验证。

## 阻塞问题

- 无阻塞。
- 真机上是否正确执行该中文别名，仍取决于现场实际启动的底层 arm action server 是否为支持 `g1_actions::ParseActionInput` 的自定义动作服务；如果现场只启动官方预置动作服务，该中文别名可能会被拒绝。

## 下一步

- 在现场启动兰石导览后观察日志中 `触发兰石穿插动作` 是否出现 `action=双手平摊开掌心向上`。
- 若 Robot Agent 返回动作名无效，应确认当前 `navi_arm` 服务是自定义动作服务还是官方预置动作服务。

## 注意事项

- `RABBITBOT_LANSHI_ACTIONS` 环境变量会覆盖 `DEFAULT_ACTIONS`；若现场环境里显式设置了该变量，本轮默认值修改不会生效。
- `release` 收手逻辑不在兰石脚本中自动追加；该脚本只按默认动作列表逐句穿插触发动作。

## 历史近期工作压缩记录

- 2026-07-02 至本轮前：历史记录主要围绕 portable/compose 解耦运行时、控制台服务重启、导航桥接、DOCX workflow、动作链路、TTS/STT/VLM/Memory/Neo4j 启动与现场排障；详细历史如需追溯请查看 Git 历史中的旧版 `HANDOFF_REPORT.md`。
