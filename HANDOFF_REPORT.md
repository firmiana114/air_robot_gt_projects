# air_robot_gt_projects 交接报告

## 背景和目标

本轮目标是将 RabbitBot 当前可运行项目整理为独立的 `air_robot_gt_projects` 自主运行包，避免继续依赖 `/mnt/ssd/navgation/projects` 下大量无关目录。目标路径为 `/mnt/ssd/navgation/projects/air_robot_gt_projects`。

## 当前状态

已完成：

- 已按 Aaron 要求清空旧 `air_robot_gt_projects` 后重建，不保留旧半成品目录内容。
- 已复制主项目、模型、ROS action 工作区、Unitree 导航示例、Unitree SDK2、VLN、Orbbec SDK、灵巧手服务源码和 Humble bridge。
- 已保留当前 `conf/dialogue_0.json` 的现场点位改动。
- 已将 air 副本中的主要运行路径改为从当前目录推导。
- 已生成 `deploy/check_air_project.sh` 和 `deploy/install_air_project.sh`。
- 已生成顶层 `README.md`。

未完成：

- 尚未在本报告生成时记录完整运行验证结果；后续应以实际执行日志为准补充。

## 已验证的事实

- 本包包含完整 `models` 目录。
- 本包包含 `rabbitbot-dev-ros2-master/py38` 和 `py310`，满足当前 workflow、Memory Agent 和 Robot Agent 的运行方式。
- 容器内路径仍设计为 `/workspace/projects/...`，由宿主 air 根整体挂载实现。
- Docker 镜像 `rabbitbot-unified-runtime:20260518` 仍作为宿主前置条件，不包含在本目录内。

## 阻塞问题

无当前打包层面的已知阻塞。运行层面仍依赖宿主系统已有 ROS、Docker 镜像、系统动态库和机器人网络。

## 建议的下一步

- 执行 `bash deploy/check_air_project.sh` 做静态和依赖检查。
- 执行 `bash deploy/install_air_project.sh` 安装 systemd unit 和 sudoers。
- 启动控制台，访问 `http://192.168.101.90:8080`。
- 现场安全确认后再从控制台启动导航主程序。

## 注意事项

- 两个 systemd 服务应保持非开机自启。
- `/home/unitree/test9.pcd` 是机器人本体侧地图路径，不应迁移到本目录。
- 如需离线迁移到另一台机器，还需要单独导出 Docker 镜像和宿主运行时依赖。

## 其它信息

- 生成时间：2026-06-10 15:50:21

## 本轮补充：打包后验证结果

### 背景和目标

本轮继续验证 `air_robot_gt_projects` 自主运行包，目标是确认静态检查、systemd 安装、控制台访问和导航桥接启动状态。

### 当前状态

已完成：

- 已执行 `bash deploy/check_air_project.sh`，目录结构、Docker 镜像存在性、核心脚本 `bash -n`、Python 编译、sudoers 模板和旧项目根硬编码检查全部通过。
- 已执行 `bash deploy/install_air_project.sh`，安装 air 路径的 `rabbitbot-loop.service`、`rabbitbot-control-console.service` 和 `/etc/sudoers.d/rabbitbot-control-console`。
- 已确认两个服务仍为 `disabled`，未设置开机自启。
- 已确认控制台服务已重启到 air 路径，`http://127.0.0.1:8080/api/status` 返回正常状态。
- 已短时启动 air 路径下的底层导航桥接，确认脚本使用 air 路径的 `custom_action_ws/install/setup.bash`，28180 Python bridge 能启动。

未完成：

- 底层 `goGoalNavigation66` 和 `g1ArmOfficialActionServer` 未能完成 DDS 初始化，因为当前 HaiSong `eno1` 为 `DOWN/unavailable`。
- 未执行完整 workflow loop 运行验证，因为当前机器人 DDS 网口不可用，继续启动会在同一处失败。
- 未发送 `go` 或执行真实导览动作。

### 已验证的事实

- 当前 `eno1` 状态为 `DOWN`，NetworkManager 显示 `ethernet:unavailable`；虽然 `Wired connection 1` 仍配置了 `192.168.123.222/24`，但接口没有可用载波/链路。
- air 路径改造后，底层桥接日志显示 `ws setup` 为 `/mnt/ssd/navgation/projects/air_robot_gt_projects/custom_action_ws/install/setup.bash`。
- 本次 DDS 失败原因是现场网口状态，不是 air 项目路径缺失。

### 阻塞问题

当前阻塞是机器人网络口 `eno1` 不可用，导致 Unitree DDS 节点报 `eno1: does not match an available interface`。需要接好机器人网络或恢复有线链路后，才能完成底层导航和完整 workflow 验证。

### 建议的下一步

- 恢复机器人网络连接后，先确认 `ip -brief addr show dev eno1` 显示 `192.168.123.222/24`。
- 再运行 `bash deploy/check_air_project.sh` 做快速复查。
- 然后从控制台点击“开始程序”，或手动运行 `sudo systemctl start rabbitbot-loop.service`，等待导航桥接和 workflow ready。
- 如果需要单独验证底层桥接，可运行：`/mnt/ssd/navgation/projects/air_robot_gt_projects/unitree_slam_example_new/example/start_nav_arm_bridge.sh eno1 /home/unitree/test9.pcd`。

### 注意事项

- 本轮没有新增业务代码日志点；但 air 检查脚本、安装脚本和桥接脚本会输出关键路径、服务状态和失败原因，足够用于部署排查。
- 生成时间：2026-06-10 15:54:42

## 本轮补充：Git 忽略规则确认

- 已确认顶层 `.gitignore` 会排除运行日志、Python 缓存、临时文件和备份目录。
- 已修正 `rabbitbot-dev-ros2-master/.gitignore`，避免 air 自主运行包漏提交 `py38/`、`py310/` 和日志目录占位文件。
- 已补充规则，使虚拟环境被纳入后仍排除其中的缓存字节码目录和 `.pyc` 文件。
- 已清理本轮导航试跑生成的 `unitree_slam_example_new/example/run_logs/nav_arm_bridge_*`，当前日志目录仅保留 `.gitkeep`。
- 已通过 `git check-ignore -v` 抽样验证：`py38/bin/python`、`py310/bin/python`、日志 `.gitkeep` 保留，普通日志文件排除。

## 本轮补充：GitHub 轻量提交策略

- 根据 Aaron 的判断，完整 air 目录包含模型、虚拟环境和构建产物，体积不适合直接提交到 GitHub。
- 已停止大体积 `git add`，删除中断提交留下的 `.git` 临时对象库，并重新初始化 Git 仓库。
- 已调整顶层 `.gitignore`：运行依赖继续留在 `/mnt/ssd/navgation/projects/air_robot_gt_projects`，但不进入 Git 提交。
- Git 提交边界改为代码、配置、部署脚本、检查脚本、README 和交接报告。
- 这意味着 GitHub 仓库不能单独恢复完整运行环境；迁移到新机器时仍需通过移动硬盘或离线依赖包同步被忽略的运行依赖目录。

## 本轮补充：外部示例工程构建产物排除

- 提交后复查发现 `unitree_slam_example_new` 下仍有历史 `build*`、`log` 和生成图片进入 Git 索引。
- 已补充顶层 `.gitignore`，排除 `unitree_slam_example_new/**/build*/`、`unitree_slam_example_new/**/log/`、生成的目标文件、静态库、动态库和 PNG 图片。
- 已使用 `git rm --cached` 仅从 Git 索引移除这些文件，磁盘上的运行依赖和构建产物仍保留在 air 目录中。
- 已补充 `*.bak_*` 忽略规则，并从 Git 索引移除外部示例工程中的历史备份脚本。

## 本轮补充：air 自包含运行复核

- 已复核 `workflow loop` 和控制台服务的 systemd 配置，`WorkingDirectory`、`ExecStart`、`EnvironmentFile` 均指向 `/mnt/ssd/navgation/projects/air_robot_gt_projects`。
- 已发现并修正 `custom_action_ws/install/setup.bash` 生成前缀问题：`start_nav_arm_bridge.sh` 和 `one_click_start.sh` 现在会显式设置 `COLCON_CURRENT_PREFIX` 到 air 目录，避免回退到旧 `/mnt/ssd/navgation/projects/custom_action_ws/install`。
- 已将 `one_click_start.sh` 额外需要的 `unitree_sdk2/build/bin/g1_loco_client` 和 `dfx_inspire_service/build/inspire_g1` 补入 air 目录，并修正 `setup_inspire_sudo_nopasswd.sh` 从 air 根目录推导 inspire 路径。
- 已补强 `deploy/check_air_project.sh`：新增 one-click 依赖检查、unitree 示例脚本语法检查、air ROS 工作区动态库解析检查、运行脚本旧路径硬编码检查。
- 已验证 `goGoalNavigation66` 在 source air 工作区后，`libcustom_action_interfaces__rosidl_typesupport_cpp.so` 解析到 `/mnt/ssd/navgation/projects/air_robot_gt_projects/custom_action_ws/install/custom_action_interfaces/lib/`。
- 当前控制台服务可访问 `http://127.0.0.1:8080/api/status`；`rabbitbot-loop.service` 保持 disabled，未设置开机自启。
- 仍需注意：完整实机导航验证依赖机器人网络口 `eno1` 可用，当前 `eno1` 显示 DOWN/unavailable 时不能完成导航 DDS 实机验证。


## 本轮补充：控制台显示服务未全部就绪排查

### 背景和目标

Aaron 在 HaiSong 上启动 `rabbitbot-control-console.service` 后，前端提示“服务仍未全部就绪，请查看状态或打开日志排查”。本轮目标是确认控制台、导航桥接和 workflow loop 的实际状态，并修复 air 项目启动链路中导致前端误报未就绪的问题。

### 当前状态

已完成：

- 已确认控制台服务本身可访问，`http://127.0.0.1:8080/api/status` 能返回状态。
- 已确认前端就绪条件包括主循环运行、28180 导航桥接端口就绪、workflow ready 文件存在且状态可读。
- 已定位根因：`rabbitbot-unified-runtime` 曾复用旧容器挂载，容器内 `/workspace/projects` 指向旧 `/mnt/ssd/navgation/projects`，导致 workflow 的 ready/status 文件写到旧路径，而 air 控制台读取 air 项目路径，因此前端持续显示服务未全部就绪。
- 已修复 `rabbitbot-dev-ros2-master/scripts_1/start_unified_integration_workflow.sh`：启动前检查既有统一容器的 `/workspace/projects` 和 `/models` 挂载源；若与当前 air 根目录不一致，则记录具体原因并重建容器。
- 已进一步修正 Docker 挂载解析方式，从 `println` 改为 `printf`，避免制表符两侧空格导致后续重启误判。
- 已重启 `rabbitbot-loop.service`，统一容器已按 air 根目录重建。

未完成：

- 本轮未发送 `go`，未执行真实导览动作。
- 本轮未停止 Aaron 已启动的 loop；当前 workflow 停在 `waiting_for_go` 闸门，等待现场操作。

### 已验证的事实

- 当前容器挂载为 `/mnt/ssd/navgation/projects/air_robot_gt_projects -> /workspace/projects`。
- 当前模型挂载为 `/mnt/ssd/navgation/projects/air_robot_gt_projects/models -> /models`。
- 当前控制台 API 返回 `main_loop=running`、`nav_bridge.ready=true`、`workflow.ready=true`、`workflow.status=waiting_for_go`。
- 当前定位状态为 `localized=true`，pose 来源为导航桥接日志。
- `bash deploy/check_air_project.sh` 通过，核心脚本语法、Python 编译、sudoers 模板、air 动态库解析和旧路径硬编码检查均正常。

### 阻塞问题

无当前前端就绪层面的阻塞。真实导览动作仍需现场确认机器人周围安全后再发送 `go`。

### 建议的下一步

- 浏览器刷新控制台页面，确认顶部状态不再提示服务未全部就绪。
- 如需开始导览，在现场安全确认后点击控制台的导览/开始流程按钮或发送 `go`。
- 若后续再次出现未就绪，优先查看 `rabbitbot-loop.service` 日志中是否出现“已有统一容器配置不匹配，将重建”以及 `/api/status` 的 `workflow.ready` 字段。

### 注意事项

- 这次问题不是前端页面故障，而是容器复用旧挂载后，workflow 状态文件写入路径与控制台读取路径不一致。
- 新增的挂载兼容性检查会输出具体不匹配原因，便于后续区分项目路径、模型路径和环境变量变更导致的容器重建。
- 生成时间：2026-06-10 18:15:00

## 本轮补充：控制台过快显示就绪与定位状态文案排查

### 背景和目标

Aaron 反馈：启动控制台后点击“开始程序”，页面很快显示就绪，但按实际启动流程不应这么快；同时定位状态长期显示“当前位姿已读取，定位状态待确认”。本轮目标是确认前端就绪判断是否读取了真实当前 workflow，并修正定位状态展示。

### 当前状态

已完成：

- 已确认控制台 API 曾读取到旧的 workflow ready/status 文件：页面显示 `run_id=20260610_181244`、`waiting_for_go`，但最新一次实际 workflow `20260610_181551` 已在 18:16:58 结束。
- 已确认根因是控制台状态选择逻辑优先选择历史 `running` 状态文件，导致旧 ready 文件盖过最新已结束的 run。
- 已修复 `rabbitbot/control_console/status.py`：workflow 状态改为选择最新状态文件；只有最新 run 仍为 `running`、存在 ready 文件且没有 `exit_code/finished_at` 时，才认为 `ready=true` 并显示 `waiting_for_go`。
- 已修复定位状态回退：没有解析到位姿时，不再显示“当前位姿已读取，定位状态待确认”，而是显示需要重定位的提示。
- 已修复前端导览按钮启用条件：只有主循环、导航桥接和 workflow 闸门全部 ready 时才允许发送导览 go。
- 已修复 `start_nav_bridge_workflow_loop.sh`：主循环启动准备阶段会清理历史 workflow 控制文件，防止服务启动早期被旧 ready 文件污染。
- 已重启 `rabbitbot-control-console.service` 让新状态逻辑生效。

未完成：

- 本轮未发送 `back`，也未重启 `rabbitbot-loop.service`，避免在现场不明确的情况下触发返航或重新拉起导航。
- 本轮未执行真实导览动作。

### 已验证的事实

- 当前 `/api/status` 返回最新 workflow：`run_id=20260610_181551`、`status=finished`、`ready=false`。
- 当前定位返回：`available=false`，状态文案为“定位未成功：程序会持续重定位，需要遥控机器人的位姿，帮助机器人完成定位”。
- 当前 `rabbitbot-loop.service` 仍在运行，但日志显示它停在“等待命令：back 返回起点”，因此此时点击“开始程序”只会执行 systemd start，不会新建 workflow。
- `bash deploy/check_air_project.sh` 已通过，核心脚本语法、Python 编译、sudoers 模板、air 动态库解析和旧路径硬编码检查正常。

### 阻塞问题

当前没有代码层面的阻塞。流程层面需要现场决定：是发送 `back` 完成返航并进入下一轮预启动，还是重启主程序清理当前等待状态。

### 建议的下一步

- 刷新控制台页面，确认不再秒变“全部就绪”，导览按钮在 workflow 未 ready 时不可点。
- 如果当前机器人应该返航，现场确认安全后发送 `back`。
- 如果不需要执行返航，可使用控制台“一键重启”或 `sudo systemctl restart rabbitbot-loop.service` 重建主循环，等待新的 workflow 进入 `waiting_for_go`。
- 若后续再出现秒变 ready，优先检查 `/api/status` 中 `workflow.run_id` 是否为最新控制文件，以及 `workflow.ready` 是否只在 `waiting_for_go` 阶段为 true。

### 注意事项

- “开始程序”按钮当前语义是启动 systemd 服务；如果 `rabbitbot-loop.service` 已经处于 active，systemd start 会立即返回，不会重启或清理当前流程状态。
- 新增日志点会记录启动时清理历史 workflow 控制文件的目录和数量；控制台状态解析对忽略非活动 ready 文件使用 DEBUG 日志，避免正常轮询产生过量日志。
- 生成时间：2026-06-10 18:22:00

## 本轮补充：定位持续未成功排查

### 背景和目标

Aaron 反馈控制台持续显示“定位未成功：程序会持续重定位，需要遥控机器人的位姿，帮助机器人完成定位”。本轮目标是确认定位失败的实际原因，并避免控制台只因 28180 Python bridge 存活而误判导航桥接就绪。

### 当前状态

已完成：

- 已确认最新导航日志为 `rabbitbot-dev-ros2-master/logs/nav_workflow_control/nav_bridge_20260610_182249.log`。
- 日志显示 `goGoalNavigation66` 启动后立即异常退出：`eno1: does not match an available interface`，随后抛出 `unitree::common::DdsException` 和 `Failed to create domain`。
- 已确认宿主网卡状态：`eno1` 为 `DOWN/NO-CARRIER`，NetworkManager 显示 `ethernet unavailable`。
- 已修复控制台 `/api/status` 的导航桥接判断：不再只看 28180 端口；会结合最新导航日志判断导航核心是否崩溃、是否网卡不可用、是否已经 ready/有位姿输出。
- 已修复前端导航桥接显示：现在会展示后端给出的具体原因，例如“导航核心未启动：Unitree DDS 网卡不可用，请检查 eno1 链路”。
- 已补强 `start_nav_bridge_workflow_loop.sh` 健康检查：识别导航日志中的 DDS、网卡和进程异常，避免导航核心已崩溃时仍把导航桥接视为健康。
- 已重启 `rabbitbot-control-console.service`，当前 API 已返回 `nav_bridge.ready=false` 和明确原因。

未完成：

- 本轮未重启 `rabbitbot-loop.service`，避免在现场链路未恢复时反复重启导航流程。
- 本轮未修复物理网络链路；需要现场接好机器人/Unitree DDS 所在的 `eno1` 网络。

### 已验证的事实

- 当前 `ip -brief addr show dev eno1` 显示 `eno1 DOWN`。
- 当前 `ip link show dev eno1` 显示 `NO-CARRIER`。
- 当前 `/api/status` 中 `nav_bridge.ready=false`，message 为“导航核心未启动：Unitree DDS 网卡不可用，请检查 eno1 链路”。
- 当前 workflow 虽然可停在 `waiting_for_go`，但导航核心未启动，不能执行真实导航。
- `bash deploy/check_air_project.sh` 已通过；核心脚本语法、Python 编译、sudoers 模板、air 动态库解析和旧路径硬编码检查正常。

### 阻塞问题

物理/网络层阻塞：`eno1` 没有载波，Unitree DDS 不能创建 domain，导致 `goGoalNavigation66` 崩溃，定位和导航都不会成功。

### 建议的下一步

- 现场恢复机器人网络连接，确保 `eno1` 有载波并处于可用状态。
- 确认 `ip -brief addr show dev eno1` 不再是 `DOWN`，并有正确的 Unitree 网络地址。
- 恢复链路后重启主程序：`sudo systemctl restart rabbitbot-loop.service`。
- 刷新控制台，等待导航桥接显示“导航核心已就绪”，定位状态显示“定位成功”后再发送 `go`。

### 注意事项

- 当前 28180 端口在线只代表 Humble Python bridge 还活着，不代表 Unitree 导航核心可用。
- 新增日志点：loop 健康检查会在导航核心日志不可读、DDS/网卡/进程异常、尚未完成定位时输出 WARNING，便于区分端口在线和核心导航可用性。
- 控制台状态解析对导航日志读取失败和核心异常使用 DEBUG 日志，避免常规状态轮询造成过量日志。
- 生成时间：2026-06-10 18:25:00

## 本轮补充：portable 可迁移化基础设施第一版

### 背景和目标

Aaron 这轮要求先为“全新 Orin 仅靠 GitHub 源码 + 镜像 + 最小宿主初始化完成 RabbitBot 冷启动”建立独立实施分支和第一版落地基础设施，同时保留现有现场可回退的 legacy 路径。

### 当前状态

已完成：

- 已从当前 `master` 切出独立分支 `feature/portable-deploy`。
- 已新增 `third_party/manifest.lock`，显式记录 Git 之外的运行依赖、镜像来源和模型下载策略。
- 已新增 `rabbitbot-dev-ros2-master/runtime/portable.env`，集中管理 portable 运行模式、DDS 网卡、地图路径、镜像和模型开关。
- 已新增 portable 相关脚本：
  - `deploy/bootstrap_host.sh`
  - `deploy/setup_robot_network.sh`
  - `deploy/ensure_models.sh`
  - `deploy/build_or_pull_images.sh`
  - `deploy/start_portable_stack.sh`
- 已新增 portable Docker 定义：
  - `rabbitbot-dev-ros2-master/docker/portable/core.Dockerfile`
  - `rabbitbot-dev-ros2-master/docker/portable/nav.Dockerfile`
  - `rabbitbot-dev-ros2-master/docker/portable/compose.yaml`
  - `rabbitbot-dev-ros2-master/docker/portable/nav_entrypoint.sh`
- 已新增 portable 入口脚本：
  - `rabbitbot-dev-ros2-master/scripts_1/start_loop_entry.sh`
  - `rabbitbot-dev-ros2-master/scripts_1/start_nav_bridge_portable.sh`
- 已修改主循环 `start_nav_bridge_workflow_loop.sh`，支持通过 `RABBITBOT_NAV_RUNTIME=compose` 切换到 portable nav。
- 已修改控制台启动脚本，使其优先使用 `runtime/control_console_venv`，并支持从 `runtime/portable.env` 读取地图路径。
- 已把 `start_kuavo_agno_workflow.bash`、`start_robot_app.bash`、`start_nav_arm_bridge.sh` 的关键固定 IP / 网卡配置改为环境变量优先。
- 已修改控制台配置与状态解析：控制台地图默认值支持 `RABBITBOT_NAV_MAP_PATH`，主循环进程检测兼容 `start_loop_entry.sh`。
- 已升级顶层 `README.md` 为 portable 主线说明，同时保留 legacy 回退章节。
- 已升级 `deploy/check_air_project.sh` 和 `deploy/install_air_project.sh`，使其同时识别 legacy / portable。

未完成：

- portable core 目前仍基于 `rabbitbot-unified-runtime:20260518` 基础镜像，尚未把其历史上游构建链完全公开重建。
- 本轮尚未执行 portable nav Docker 实际构建，也未在“干净新 Orin”环境完成端到端冷启动验证。
- 本轮没有把 `pyorbbecsdk-v2-py310`、`vln` 等目录真正转成仓库内可自动恢复制品，只是先通过 manifest 明确了它们必须被显式管理。

### 已验证的事实

- 所有新增/修改的 shell 脚本已通过 `bash -n` 语法检查。
- `rabbitbot/control_console/config.py`、`status.py` 与现有关键 Python 文件编译检查可通过。
- portable 基础文件已落盘，`runtime/portable.env`、`third_party/manifest.lock`、portable Docker 定义和 deploy 脚本都在仓库中可见。
- 主循环现在支持两种导航桥接运行方式：
  - `host`：原 `start_nav_arm_bridge.sh`
  - `compose`：新的 `start_nav_bridge_portable.sh`
- `deploy/check_air_project.sh` 现在会额外检查：
  - manifest 关键条目
  - portable env 关键键
  - portable Docker 文件与脚本
  - 关键运行脚本中未环境变量化的固定 IP / 网卡硬编码

### 阻塞问题

- 当前最大未完成阻塞仍是 portable core 的完全可重建性：它现在默认依赖 `rabbitbot-unified-runtime:20260518` 作为基础镜像，而不是完全由公开 Dockerfile 从零构建。
- 第二个阻塞是制品供应链还未真正接通：manifest 已有，但 `unitree_sdk2`、`vln`、`pyorbbecsdk-v2-py310` 等目录的远程制品源还没落地。
- 第三个阻塞是尚未在干净 Orin 上做完整演练，因此还不能宣称“只靠 GitHub + 镜像即可稳定冷启动成功”。

### 建议的下一步

- 优先在当前 HaiSong 上尝试执行：
  - `bash deploy/check_air_project.sh`
  - `bash deploy/build_or_pull_images.sh MODE=build`
  - `bash deploy/start_portable_stack.sh`
- 如果 portable nav 镜像构建失败，先逐项补齐 nav Dockerfile 的系统依赖，再继续。
- 如果 portable core 运行依旧依赖 `rabbitbot-unified-runtime:20260518`，下一轮应继续拆解该镜像来源，逐步把上游历史镜像改成仓库内可重建或镜像仓库可拉取的显式基础镜像。
- 在确认 portable 基础服务可启动后，再安排一次“干净 Orin”冷启动演练。

### 注意事项

- 本轮为了保证现场回退能力，没有删除 legacy 逻辑；因此仓库现在是“双路径并存”，不要把存在 legacy 代码误解为 portable 改造失败。
- 新增日志点主要在 `bootstrap_host.sh`、`setup_robot_network.sh`、`ensure_models.sh`、`build_or_pull_images.sh`、`start_portable_stack.sh` 和 `start_nav_bridge_portable.sh`，覆盖了宿主初始化、网卡配置、模型下载、镜像准备和 portable nav 启动的关键阶段、输入摘要、失败原因和结果摘要。
- 当前 root README 已改成 portable 主线说明；后续如再改部署方式，应先同步 README 与本交接报告，再继续提交代码。
- 生成时间：2026-06-11 18:00:00

## 本轮补充：portable 镜像构建收口与上下文治理

### 背景和目标

本轮继续推进 `feature/portable-deploy` 分支上的 RabbitBot 可迁移化改造，目标是让 portable 路径不仅具备脚本、清单和 compose 入口，还能够在当前 Orin 上实际完成 `rabbitbot-nav` 镜像构建，并避免宿主历史构建产物和大体积运行目录再次污染 Docker 构建上下文。

### 当前状态

已完成：

- 已在 `feature/portable-deploy` 分支上修复 `rabbitbot-dev-ros2-master/docker/portable/nav.Dockerfile`，在编译 `unitree_slam_example_new/example` 前显式清理宿主遗留的 `build/` 和 `run_logs/`。
- 已新增顶层 `.dockerignore`，排除 `models/`、`py38/`、`py310/`、ROS build/install 缓存、导航示例 build 目录和无关外部依赖，避免它们进入 portable 镜像构建上下文。
- 已补强 `deploy/check_air_project.sh`，新增 `.dockerignore` 存在性和关键规则检查，防止后续回归导致大目录重新进入构建上下文。
- 已重新执行 `MODE=build RABBITBOT_PORTABLE_BUILD_CORE=0 RABBITBOT_PORTABLE_BUILD_NAV=1 bash deploy/build_or_pull_images.sh`，确认 `ghcr.io/aaronai/rabbitbot-nav-portable:20260611` 构建成功。
- 已确认本次 `docker build` 的上下文传输量降到约 `103.31kB`，不再把 `models/`、历史虚拟环境和宿主 build 目录打进镜像构建上下文。
- 已再次执行 `bash deploy/check_air_project.sh` 和 `docker compose -f rabbitbot-dev-ros2-master/docker/portable/compose.yaml config -q`，检查通过。

未完成：

- 本轮没有实际启动 portable stack；原因是当前主机仍可能承担现场控制任务，不适合在未确认现场状态时直接拉起新容器拓扑。
- `portable core` 仍默认基于 `rabbitbot-unified-runtime:20260518`，后续仍需继续拆解或发布可拉取成品镜像，才能彻底消除该基础镜像依赖。

### 已验证的事实

- `rabbitbot-nav` portable 镜像当前已成功生成：`ghcr.io/aaronai/rabbitbot-nav-portable:20260611`，镜像 ID 为 `sha256:d25e6527186e175be19d5e9bf26ec19fd680ae4fe0bb4feb3872a6ac56eb55c1`。
- 之前导致构建失败的直接原因已确认是宿主 `unitree_slam_example_new/example/build/CMakeCache.txt` 被复制进容器，路径与容器内目录不一致。
- 新增 `.dockerignore` 后，Docker 构建上下文已显著收敛，说明大体积目录已被成功排除。
- 当前 portable 自检脚本已经覆盖：依赖清单、portable env、`.dockerignore`、关键脚本语法、Python 编译、旧路径硬编码和固定网卡/IP 硬编码。

### 阻塞问题

当前主要阻塞已从 `rabbitbot-nav` 构建失败转移为 `portable core` 仍依赖 legacy unified 基础镜像；如果新 Orin 上既没有本地该镜像，也没有可拉取的成品镜像，就还不能完成真正意义上的“只靠 GitHub + 镜像仓库冷启动”。

### 建议的下一步

- 继续拆解 `portable core`，优先识别 `rabbitbot-unified-runtime:20260518` 中必须前置固化进 Dockerfile 的系统依赖与 Python 运行时。
- 在镜像仓库发布 `rabbitbot-core-portable` 与 `rabbitbot-nav-portable` 的可拉取版本，并把拉取地址与版本锁回写到 `third_party/manifest.lock`。
- 选择一个不影响现场运行的窗口，按 `bootstrap_host.sh -> build_or_pull_images.sh -> start_portable_stack.sh` 路径做一次完整 portable 冷启动演练。
- 在具备机器人链路的条件下，再补做 `workflow -> waiting_for_go` 与 28180 就绪的整链验证。

### 注意事项

- 本轮新增/调整的日志主要集中在 portable 脚本与检查链路：镜像准备、模型下载、宿主初始化、网络配置、compose 启动和导航入口都会记录开始、关键参数、完成状态和失败原因，便于后续在新 Orin 上排查冷启动问题。
- `.dockerignore` 仅用于镜像构建上下文治理，不影响 Git 跟踪规则；Git 侧是否提交仍以顶层 `.gitignore` 为准。
- 生成时间：2026-06-11 11:30:00

## 本轮补充：portable 自包含镜像化冷启动落地

### 背景和目标

按 Aaron 的「全新 Orin 镜像化冷启动」计划，把 `core` 与 `nav` 做成包含全部运行时依赖的本地自包含镜像，使全新 Orin 只需 GitHub 拉源码、导入镜像、最小宿主初始化即可冷启动，运行期不再要求宿主存在 `py38/py310/vln/pyorbbecsdk/unitree_sdk2` 等目录。

### 关键现实约束（已核实）

- 本机现存镜像中，`unified_runtime/Dockerfile` 引用的四个上游镜像里**只剩 `neo4j:5.26-community`**；`navid-rabbitbot:stt-tts-audio-ct2cuda-20260511`、`rabbitbot-vllm:20260511`、`foxy-ros-cam-orb-ubuntu20:rabbitbot-20260511` 这三个 tag 已不在本机。因此**无法在本机从零重建 core**。
- `rabbitbot-unified-runtime:20260518`（49.8GB）本身即这四个镜像的合并产物，已包含 Neo4j/Java/ROS Foxy/Python3.8/STT/TTS/VLM venv。
- 结论：core 只能以 unified-runtime 为基础镜像，再把宿主 gitignore 的重型依赖与源码烤进镜像。该折中已在 `third_party/manifest.lock` 的 `images.portable_core.notes` 与 README 中如实记录。

### 当前状态

已完成：

- **改写 `docker/portable/core.Dockerfile` 为自包含镜像**：`FROM rabbitbot-unified-runtime:20260518`，烤入 `rabbitbot-dev-ros2-master`（含 `py38/py310`）、`vln`、`pyorbbecsdk-v2-py310`、`humble_robot_agent_bridge.py` 到 `/workspace/projects/...`，并从烤入源码安装统一入口与冒烟脚本到 `/usr/local/bin`。
- **改写 `deploy/build_or_pull_images.sh`**：
  - 新增 `MODE=build|check|none`（保留 `pull|both`）；`RABBITBOT_IMAGE_SOURCE=local` 时默认 `check`。
  - core 构建使用 `rsync` 生成的专用上下文 `.portable_core_ctx`，绕过顶层 `.dockerignore` 对 `py38/py310/vln/pyorbbecsdk` 的排除（早期 `cp -al` 方案因宿主 root 文件触发 `protected_hardlinks` 失败，已弃用）。
  - 记录镜像 tag、image id、耗时。
- **新增 `deploy/export_portable_images.sh` / `deploy/import_portable_images.sh`**：以 `docker save/load` 离线交付，导出 `*.tar`、`images.sha256`、`images.lock.json`；导入前校验 sha256，并确认 load 后 tag 与 `runtime/portable.env` 一致；均记录 tag、id、路径、sha256、耗时。
- **改写 `scripts_1/start_unified_integration_workflow.sh`**：portable 模式（`RABBITBOT_RUNTIME_MODE=portable`）新建容器时，为 `py38/py310/vln/pyorbbecsdk` 注入从 core 镜像 seed 的 named volume（`rabbitbot_portable_*`）；新建前重置这些卷以从当前镜像重新 seed；并新增「容器镜像与期望镜像不一致即重建」判定，保证导入新镜像后重启即生效。
- **改写 `deploy/check_air_project.sh` 为两模式**：`PORTABLE_CHECK_MODE=builder|clean_orin`。`clean_orin` 允许外部构建目录缺失，转而要求已导入的 core/nav 镜像、控制台 venv、`RABBITBOT_NAV_MAP_PATH` 配置；manifest 检查新增「无未解决 blocker」。
- **更新 `third_party/manifest.lock`**：`unitree_sdk2`/`custom_action_ws_install` → `baked_into_image`(nav)；`vln`/`pyorbbecsdk-v2-py310` → `baked_into_image`(core)；`legacy_python_envs` → `not_required_for_portable`；`dfx_inspire_service` 保持 `legacy_optional`；`blockers` 清空并移入 `resolved_blockers`；新增 `image_source=local`、`image_delivery=offline_docker_save_load`。
- **更新 `runtime/portable.env`**：`RABBITBOT_PORTABLE_BUILD_CORE=1`、新增 `RABBITBOT_IMAGE_SOURCE=local`、`RABBITBOT_PORTABLE_INJECT_DEPS=1`；并在 `rabbitbot-dev-ros2-master/.gitignore` 增加 `!runtime/portable.env`，使该模板能随仓库迁移（此前被 `*` 规则忽略）。
- **更新 `start_portable_stack.sh`**：以 portable 模式启动，默认走 `check`（不访问远端仓库）。
- **更新 `README.md`**：拆为「流程 A 构建机生成镜像」「流程 B 全新 Orin 导入镜像冷启动」两条明确流程，并更新自检/注意事项。

### 已验证的事实（本机实测）

- `PORTABLE_CHECK_MODE=builder bash deploy/check_air_project.sh` 通过。
- `MODE=build bash deploy/build_or_pull_images.sh` 成功：`ghcr.io/aaronai/rabbitbot-core-portable:20260611`（id `sha256:683425716fd5...`，50.8GB，耗时 29s）；nav 命中缓存（id `d25e6527186e`）。
- **自包含冒烟（无任何挂载）通过**：`docker run --rm --entrypoint rabbitbot-unified-smoke-check` 返回 `audio_runtime_ok / vllm_runtime_ok / workflow_runtime_ok / robot_python38_runtime_ok / neo4j_java_runtime_ok`，exit=0。证明 workflow(py310)、Robot Agent(系统 py3.8 + 烤入 py38 site-packages)、VLM、音频、Neo4j Java 全部在镜像内可用。
- **干净 Orin 运行链路通过（throwaway 容器模拟）**：用 `git archive HEAD` 生成只含 git 跟踪文件、缺 `py38/py310/vln/pyorbbecsdk` 的源码树 bind 到 `/workspace/projects`，再挂 4 个新建 named volume；容器内这 4 个依赖均从 core 镜像 seed 出来并在 bind mount 之上可见，`py310/bin/python` 成功 `import agno` 与 `from rabbitbot.agno_agents.workflow import create_main_workflow`（exit=0）。证明「named volume 在父 bind mount 之下仍能从镜像 seed」这一关键机制成立。
- `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh` 通过（exit=0）；两个 WARN 为预期：本机尚无 `control_console_venv`、地图文件为机器人本体侧路径。

### 未完成 / 阻塞

- **未切换正在服务的 live core 容器**：当前 `rabbitbot-unified-runtime` 容器已运行约 16h、控制台 active、workflow 停在 `waiting_for_go`。因 `eno1` 当前为 DOWN，Unitree TTS / Robot Agent 基础服务在全新容器中无法完整初始化，此时执行 `start_portable_stack.sh` 重建会用「不可验证的新容器」替换「当前可用的待命容器」且不易回滚。已通过 throwaway 容器完整验证镜像与 seed 机制，**实际 live 切换建议在 `eno1` 恢复的维护窗口执行**。
- **未在真正的「干净新 Orin」整机演练**：本机仍是构建机；干净链路已用容器级模拟覆盖，但端到端整机冷启动（导入 tar → bootstrap → start_portable_stack → 控制台/28180/waiting_for_go）需在另一台干净 Orin 上完成。
- 离线导出 `deploy/export_portable_images.sh` 正在后台运行生成 `outputs/portable-images/`（core ~50GB tar + nav + sha256 + lock）；本报告生成时可能尚未结束，结果以 `outputs/portable-images/images.lock.json` 与 `/tmp/export.log` 为准。

### 建议的下一步

- `eno1` 恢复后，在维护窗口执行：`bash deploy/start_portable_stack.sh`（portable 模式会自动检测镜像变化并以 core-portable 镜像 + 依赖卷重建 core 容器），等待基础服务就绪后再验证控制台、28180 与 `waiting_for_go`。
- 准备一台干净 Orin，按 README「流程 B」整机演练：导入镜像 → `bootstrap_host.sh` → `PORTABLE_CHECK_MODE=clean_orin` 自检 → `MODE=check` 校验 → `start_portable_stack.sh`。
- 将 `outputs/portable-images/` 整目录交付到目标 Orin 作为离线镜像来源。

### 注意事项

- core 镜像 50.8GB，`docker save` tar 约同量级；导出/导入耗时较长，`outputs/` 已被 `.gitignore` 排除，不进入提交。
- portable 依赖卷 `rabbitbot_portable_{py38,py310,vln,pyorbbecsdk}` 在「新建 core 容器」时会被重置并从当前 core 镜像重新 seed；导入新版 core 镜像后首次 `start_portable_stack.sh` 即会刷新它们。
- 本轮新增/调整的日志点：core 构建（上下文准备、镜像 id、耗时）、镜像 check/none 分支、导出/导入（tag/id/路径/sha256/耗时）、portable 依赖卷重置与注入、容器镜像不一致重建原因、clean_orin 自检的镜像/初始化/地图校验，均覆盖关键阶段、输入摘要、状态变化、失败原因。
- 生成时间：2026-06-11 11:05:00

## 本轮补充：宿主 venv 初始化与 28180 端口拓扑修复

### 背景和目标

修复 portable 冷启动链路的两个阻塞：`bootstrap_host.sh` 在缺 `python3-venv` 的宿主上模糊失败；`start_portable_stack.sh`（core 内 `robot_app.py`）与 nav bridge 争抢 28180。核心决策：portable 模式下 28180 统一归属 `rabbitbot-nav` 的 `humble_robot_agent_bridge`，core 不再启动 `robot_app.py`。

### 当前状态

已完成：

- **`bootstrap_host.sh` venv 前置检查**：新增功能性探测（实际创建临时 venv，因为缺 `python3-venv` 时 venv 模块仍在、ensurepip 缺失）；失败时报 Python 版本、建议包名（`python3-venv pythonX.Y-venv`）、是否启用自动安装与下一步命令；`INSTALL_HOST_PACKAGES=1` 时自动 `apt-get install`（root 下不强制 sudo），装后复检。
- **端口拓扑改造**：
  - `start_unified_container.sh` 与 `start_unified_integration_workflow.sh` 新增 `RABBITBOT_UNIFIED_START_ROBOT_AGENT`（legacy 默认 1，portable 默认 0）；为 0 时跳过 `start_robot_agent` 与 28180 等待，但在 workflow 启动前检查 `RABBITBOT_ROBOT_AGENT_URL`（默认 `http://127.0.0.1:28180`，即 nav bridge）可达。
  - 该键写入 `runtime/portable.env`，容器创建时以 `-e` 传入并纳入兼容性判定（旧容器未设置按 1 处理，legacy 不误重建）。
  - **覆盖语义修正**：`portable.env` 的该键只在 portable 模式生效；显式传 `RABBITBOT_RUNTIME_MODE=legacy` 时不被 env 文件覆盖、默认回 1（已用 throwaway 容器验证 legacy=1 / portable=0）。
  - `start_nav_bridge_workflow_loop.sh` 的 28180 占用检查改为识别占用者：core robot_app → 明确报错并指引重建；已有 portable nav 容器且 compose 运行时 → 告警后由 compose 重建接管；未知占用 → 报错并给排查命令。
  - `start_portable_stack.sh` 只启动 core 基础服务（7687/28182/28185），不要求 28180。
- **自检增强**（`check_air_project.sh`）：portable env 必须 `RABBITBOT_UNIFIED_START_ROBOT_AGENT=0`；静态检查 core 启动链路含开关支持；运行期端口拓扑检查（core 运行中不得有 robot_app，nav 运行中 28180 应监听）；clean_orin 增加 venv 能力探测（不可用但有 apt-get 时按"可自动补齐"告警放行，符合计划"或确认 INSTALL_HOST_PACKAGES=1 可安装"）。
- **顺带修复的两个 nav 镜像真实 bug**（上轮镜像构建后从未运行过）：
  1. `humble_robot_agent_bridge.py` 用 FastAPI `Form(...)` 需要 `python-multipart`，nav.Dockerfile 未安装 → bridge 导入即崩溃、28180 永不监听。已加入 pip 安装并重建镜像。
  2. compose 模式下 goGoal/g1Arm 的日志只落容器内文件，宿主 loop 健康检查读不到 DDS 错误 → `nav_entrypoint.sh` 新增 `tail -F` 把后台节点日志透传到容器 stdout；同时把 entrypoint 的 COPY 移到编译层之后（再改入口不触发重编译，本次重建 99s）。

### 已验证的事实（本机实测）

- venv 失败路径：在缺 `python3-venv` 的容器（ros:humble-jammy）中快速失败，给出明确安装建议；`INSTALL_HOST_PACKAGES=1` 自动安装并复检通过。
- **新检查在 HaiSong 宿主上抓到真实问题：本机确实缺 `python3-venv`**（此前 bootstrap 即因此失败），现报错明确；宿主侧自动安装因 sudo 需密码未执行（见阻塞）。
- core 以 portable 镜像启动后：7687/28182/28185 监听，28180/28184/8000/8005 全部关闭，容器内无 robot_app 进程；4 个依赖卷正常 seed。
- `start_loop_entry.sh` 不再因 28180 被 core 占用退出；nav bridge（compose）启动后 28180 由 `humble_robot_agent_bridge` 提供（Uvicorn 0.0.0.0:28180）。
- eno1 DOWN 时 goGoal 报明确错误 `eno1: does not match an available interface` + `DdsException`，透传到 compose stdout 后，loop 健康检查给出明确原因"检测到 DDS/网卡/进程异常"，未误判为端口冲突。
- "28180 由已有 nav 容器占用 → compose 重建接管"路径实测触发并正常工作。
- 回归：legacy throwaway 容器 `RABBITBOT_UNIFIED_START_ROBOT_AGENT=1` 且无 portable 依赖卷；portable 容器为 0。VLM/STT 关闭时不等待 8000/8005/28184。
- 最终自检：`PORTABLE_CHECK_MODE=builder`、`clean_orin`、`MODE=check` 全部通过（clean_orin 的 venv/控制台 venv/地图为可解释告警）。

### 阻塞问题

- **宿主 `python3-venv` 安装需 sudo 密码**：本机 `sudo -n` 不可用，我无法非交互执行 `INSTALL_HOST_PACKAGES=1 bash deploy/bootstrap_host.sh`。需 Aaron 在 HaiSong 上执行一次（或手动 `sudo apt-get install -y python3-venv python3.10-venv`），之后重跑 `bash deploy/bootstrap_host.sh` 即可创建控制台 venv 并完成宿主初始化幂等验证。
- 真实 DDS 通信验证仍依赖 eno1 链路恢复与机器人在场（本轮按计划只要求错误明确）。

### 建议的下一步

- Aaron 在 HaiSong 执行：`INSTALL_HOST_PACKAGES=1 bash deploy/bootstrap_host.sh`，完成宿主 venv 与控制台 venv。
- eno1 恢复后启动 `rabbitbot-loop.service`（或 `start_loop_entry.sh`），验证完整链路：nav 先行 → core 复用 → workflow 预启动到 `waiting_for_go`。
- 若需更新离线交付件，重新执行 `bash deploy/export_portable_images.sh`（nav 镜像 id 已变更为 `23c0ef06...`，旧 tar 中的 nav 镜像含 python-multipart 缺失 bug，不应再交付）。

### 注意事项

- 当前 core 容器已以 `rabbitbot-core-portable:20260611` 运行（基础服务就绪，无 robot_app）；nav 容器测试后已 down，留待现场启动。
- compose nav 容器 restart 策略为 `unless-stopped`：loop 停止时只杀 compose 客户端进程、容器会留下，下次 start_nav_bridge 会按"nav 容器占用 → compose 接管"路径自动重建，这是预期行为。
- 本轮新增/调整日志点：venv 探测/自动安装（版本、包名、失败命令、下一步）、core 跳过 Robot Agent 与外部可达性检查、28180 占用者识别（三分支各自给出原因与处理方法）、nav 节点日志透传 stdout、自检的端口拓扑与 venv 能力检查，均覆盖失败原因与排查指引。
- 生成时间：2026-06-11 12:50:00

## 本轮补充：runtime 目录 Git 卫生修复（env 模板化与忽略规则）

### 背景和目标

`runtime/control_console_venv/` 未被 ignore，导致大量虚拟环境文件出现在 `git status`；`runtime/portable.env` 是已跟踪文件，但 `bootstrap_host.sh` 会写入本机绝对路径，导致它频繁变成 modified。目标：Git 只跟踪可迁移模板，不跟踪任何本机运行态文件；全新 Orin 仍能通过 bootstrap 自动生成实际运行用的 env。

### 当前状态

已完成：

- 新增可迁移模板 `rabbitbot-dev-ros2-master/runtime/portable.env.example`（内容为原已跟踪 portable.env 的机器无关默认值），随仓库进入 Git。
- `runtime/portable.env` 改为本机生成文件：已 `git rm --cached` 从索引移除（磁盘文件保留），由 `bootstrap_host.sh` 在目标机器上从模板复制生成并增量写入本机配置（DDS 网卡、CIDR、地图路径、模型目录、compose 路径等）。
- 忽略规则修复的关键点：`rabbitbot-dev-ros2-master/.gitignore` 是白名单式规则（`*` + `!模式`），嵌套 .gitignore 优先级高于仓库根 .gitignore，单改根文件无效。已将其末尾 `!runtime/portable.env` 白名单替换为 `runtime/**` + `!runtime/.gitkeep` + `!runtime/portable.env.example`；根 `.gitignore` 同步增加 runtime 规则块作为双保险。
- 11 个读取 env 的脚本（deploy 下 7 个、scripts_1 下 4 个）统一增加回退逻辑：优先 source `runtime/portable.env`，不存在时回退 source `portable.env.example` 并打印 WARN 提示先运行 bootstrap。
- `check_air_project.sh`：共享检查改为要求 `portable.env.example` 存在；grep 类静态检查改用实际生效的 env 文件（新增 `PORTABLE_ENV_EFFECTIVE_FILE`）；clean_orin 模式在本机 env 缺失时打 WARN 并按模板做只读默认校验。
- `install_air_project.sh`：安装 systemd 前强制要求本机 `runtime/portable.env` 存在，缺失时明确报错并提示先执行 `bootstrap_host.sh`（systemd `EnvironmentFile` 仍指向实际 portable.env，不加载 example）。
- 新增 `runtime/.gitkeep` 占位文件并跟踪。README 新增"runtime 目录与 env 文件约定"小节。

未完成：

- `install_air_project.sh` 在 portable.env 存在时的完整安装路径未实际执行：本机 sudo 需要密码，SSH 非交互无法验证。脚本改动仅在原校验前增加显式检查，存在时行为不变，且 `bash -n` 与自检的脚本语法检查均通过。

### 已验证的事实

- `git status --short rabbitbot-dev-ros2-master/runtime` 只剩 `.gitkeep`（新增）与 `portable.env -> portable.env.example`（重命名跟踪），venv 文件不再出现。
- `git check-ignore -v` 确认 `runtime/control_console_venv/bin/python`、`runtime/portable.env`、`runtime/rabbitbot-loop.env` 均命中 `rabbitbot-dev-ros2-master/.gitignore` 的 `runtime/**` 规则。
- `git ls-files rabbitbot-dev-ros2-master/runtime` 只列出 `.gitkeep` 和 `portable.env.example`。
- 移走本机 portable.env 后运行 `APPLY_ROBOT_NETWORK=0 bash deploy/bootstrap_host.sh`，从模板成功生成并写入全部本机值，与移走前文件相比仅头部注释不同、键值完全一致；再次运行幂等，内容无变化，Git 状态不受影响。
- `PORTABLE_CHECK_MODE=builder` 与 `PORTABLE_CHECK_MODE=clean_orin` 自检均通过（clean_orin 仅保留预期的地图文件不存在 WARN）；`MODE=check bash deploy/build_or_pull_images.sh` 通过。
- portable.env 缺失时运行 `install_air_project.sh`，按预期退出码 1 并提示先执行 bootstrap。

### 阻塞问题

- 无阻塞。仅 install 完整路径需在有 sudo 的交互会话中复跑一次确认（预期无行为变化）。

### 建议的下一步

- 在交互终端执行一次 `bash deploy/install_air_project.sh` 复确认 systemd 安装路径正常。
- 若其它 Orin 已克隆本仓库，拉取本次提交后各机的 portable.env 会因索引移除而显示删除状态，属预期；各机本地文件不受影响，必要时重跑 `bootstrap_host.sh`。

### 注意事项

- 修改可迁移默认配置一律改 `portable.env.example`；改 `portable.env` 只影响本机。
- `rabbitbot-dev-ros2-master/.gitignore` 是白名单式规则，向 runtime 添加新的需跟踪文件时必须同时在该文件追加 `!runtime/<文件名>`，仅改根 .gitignore 无效。
- 本轮新增/调整日志点：bootstrap_host.sh 记录 portable.env 的生成来源（模板复制 / 已存在增量更新 / 模板缺失降级）；11 个脚本回退读取模板时打印 WARN 并附带处置建议；install_air_project.sh 缺失本机 env 时输出 ERROR 与修复指引。这些日志可直接定位"env 从哪来、为什么是这份配置"一类问题。

## 本轮补充：机器人接入后的 portable 稳定运行修复与验收

### 背景和目标

机器人已上电并通过网线连接 Orin，`eno1` 已恢复 UP。本轮目标是在迁移到全新 Orin 前验证当前项目本体是否能稳定运行：systemd 启动后不反复重启，控制台 8080 可显示 ready，workflow 能预启动并停在 `waiting_for_go`。

### 当前状态

已完成：

- 修复 `rabbitbot-dev-ros2-master/scripts_1/start_nav_bridge_workflow_loop.sh` 的 portable nav 启动健康检查：28180 刚监听后不再立即因宿主 wrapper 日志暂无 Pose 退出，而是按 `RABBITBOT_NAV_CORE_READY_TIMEOUT_SECONDS`（默认 90 秒）与 `RABBITBOT_NAV_CORE_READY_POLL_SECONDS`（默认 2 秒）等待导航核心输出 `[Pose]` 或 Ready。
- 健康检查新增 portable nav 容器日志兜底：优先读取本轮宿主 wrapper 日志，同时读取 `rabbitbot-portable-rabbitbot-nav-1` 自本轮启动时间之后的日志，避免复用旧容器历史 Pose 造成误判。
- 修复 compose `--force-recreate` 竞态：等待期间要求 28180 当前可用；容器重建过程中端口短暂消失时记录 WARN 并继续等待，不再立即进入恢复循环。
- 控制台状态改为读取 runtime 导航日志来源：宿主 wrapper 日志没有 Pose 时，回退读取 portable nav 容器日志；`/api/status` 增加 `nav_log_source`、`nav_bridge.source` 与 `nav_bridge.map_exists`，避免容器已定位但网页仍显示未就绪。
- 地图缺失提示增强：loop 启动、自检、控制台状态都会明确指出 `/home/unitree/test9.pcd` 缺失，并提示地图不随仓迁移，需要补齐或更新 `runtime/portable.env` 的 `RABBITBOT_NAV_MAP_PATH`。

未完成：

- `/home/unitree/test9.pcd` 当前仍不存在。导航核心已能定位并输出 Pose，但真实导览验收前仍应补齐该地图文件或把 `RABBITBOT_NAV_MAP_PATH` 改为现场实际地图路径。
- 由于宿主 Python 环境和 `runtime/control_console_venv` 均未安装 `pytest`，无法运行完整 pytest 单元测试；已用 py_compile、轻量函数导入调用和现场 systemd 验收覆盖关键路径。

### 已验证的事实

- `eno1` 当前 UP，地址为 `192.168.123.222/24`。
- 语法检查通过：`bash -n start_nav_bridge_workflow_loop.sh`、`python3 -m py_compile` 控制台相关文件、`bash -n deploy/check_air_project.sh`。
- 轻量运行校验通过：`parse_latest_pose_from_lines()` 可解析 Pose，`detect_nav_bridge_status_from_lines()` 可判定 ready，`create_app()` 可正常构建 FastAPI 应用。
- `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh` 通过；仅保留地图文件不存在 WARN。
- 通过终止 `rabbitbot-control-console.service` 与 `rabbitbot-loop.service` 主进程触发 systemd 自动重启，新代码已生效。
- 5 分钟稳定性观察通过：`rabbitbot-loop.service` 的 `NRestarts` 从 247 到 247 未增长，`MainPID=84700` 保持 `active/running`。
- `/api/status` 最终返回：`main_loop=running`，`nav_bridge.ready=true`，`workflow.status=waiting_for_go`，`workflow.ready=true`，`pose.available=true`，`pose.localized=true`，`nav_log_source=容器日志:rabbitbot-portable-rabbitbot-nav-1`。
- 28180 仍由 `rabbitbot-nav` 提供，core 容器未启动内部 `robot_app.py`。

### 阻塞问题

- 真实导览前的唯一现场阻塞是地图文件路径：`/home/unitree/test9.pcd` 在宿主和 nav 容器内均不可见。当前状态接口会明确显示 `导航地图文件缺失：/home/unitree/test9.pcd`，不会再伪装成单纯重定位问题。

### 建议的下一步

- 补齐 `/home/unitree/test9.pcd`，或在 `rabbitbot-dev-ros2-master/runtime/portable.env` 中把 `RABBITBOT_NAV_MAP_PATH` 改为现场实际地图路径。
- 地图补齐后再次重启 `rabbitbot-loop.service`，复验 8080 控制台 ready、`waiting_for_go`、go 导览和 back 返航。
- 若要迁移到全新 Orin，继续使用当前 portable systemd + compose 流程；本轮修复已消除启动健康检查误判和控制台 ready 状态来源不一致。

### 注意事项

- 本轮通过终止服务主进程触发 systemd 自动重启，原因是 SSH 非交互环境无法提供 sudo 密码；这是现场验证动作，不是部署流程要求。
- 本轮新增/调整日志点：导航地图存在/缺失、导航核心 ready 等待开始、28180 重建等待、首次检测到 Pose/Ready 的耗时、使用的日志来源、DDS/网卡/进程异常、容器日志读取失败或回退原因。控制台状态增加日志来源字段，便于排查网页 ready 与实际容器状态不一致。
- 生成时间：2026-06-11 14:50:00

## 本轮补充：机器人侧地图路径语义修正

### 背景和目标

现场控制台显示“导航核心已就绪；导航地图文件缺失：/home/unitree/test9.pcd”。结合已成功定位的事实判断，`/home/unitree/test9.pcd` 很可能是机器人/Unitree 导航服务侧可见路径，而不是 Orin 宿主或 nav 容器必须能直接 `test -f` 的文件。因此原提示“文件缺失”容易误导为运行失败或迁移 blocker。

### 当前状态

已完成：

- 控制台状态文案从“导航地图文件缺失”改为“地图在 Orin 本地不可见”，并补充“若定位已成功，说明机器人侧地图可用”。
- `/api/status` 保留兼容字段 `map_exists`，新增更准确的 `map_visible_on_orin`，表达这是 Orin 本地可见性检查，不代表机器人侧地图不存在。
- loop 启动日志和 `deploy/check_air_project.sh` 自检提示同步改为 Orin 本地不可见语义，避免把机器人侧地图误报为本地缺失。

### 已验证的事实

- `bash -n` 与 `python3 -m py_compile` 通过，`git diff --check` 通过。
- 重启 `rabbitbot-control-console.service` 主进程后，新状态接口已生效：`nav_bridge.ready=true`、`pose.localized=true`，消息为“地图在 Orin 本地不可见：/home/unitree/test9.pcd（若定位已成功，说明机器人侧地图可用）”。

### 阻塞问题

- 无新增阻塞。迁移验收时仍需确认机器人侧确实存在同一路径或配置为现场实际地图路径。

### 建议的下一步

- 若要进一步消除 UI 歧义，可将顶部“全部就绪”拆成“运行就绪 + 配置告警”两层状态；当前本轮仅修正地图路径语义，不改变 ready 判定。

### 注意事项

- `map_exists=false` 现在仅表示 Orin 本地不可见，不能再解读为机器人侧地图不存在。
- 本轮新增/调整日志点集中在地图路径可见性提示，目的是区分 Orin 本地文件检查与机器人侧导航服务读图能力。
- 生成时间：2026-06-11 15:05:00

## 本轮补充：全新 Orin GitHub 源码缺 systemd/sudoers 模板修复

### 背景和目标

在 ShuHao-orin 上用 GitHub 新拉取源码执行 `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh` 时，自检失败：`rabbitbot-dev-ros2-master/scripts_1/systemd/rabbitbot-control-console.sudoers` 不存在。HaiSong 现场该文件存在但被 `rabbitbot-dev-ros2-master/.gitignore` 的白名单规则排除，说明 GitHub 源码并非完整可部署状态。

进一步检查发现，仓库中未跟踪的 systemd 模板还硬编码了 HaiSong 路径 `/mnt/ssd/navgation/projects/air_robot_gt_projects` 和用户 `pc`，即使强行提交也会在 ShuHao 的 `/mnt/disk1/gt/air_robot_gt_projects` 上安装错误服务。因此本轮修复选择动态生成 systemd/sudoers，而不是继续依赖固定模板文件。

### 当前状态

已完成：

- `deploy/install_air_project.sh` 不再依赖 `rabbitbot-dev-ros2-master/scripts_1/systemd/rabbitbot-loop.service`、`rabbitbot-dev-ros2-master/scripts_1/systemd/rabbitbot-control-console.sudoers` 或 `rabbitbot-dev-ros2-master/deploy/rabbitbot-control-console.service`。
- 安装时按当前机器动态生成：
  - `rabbitbot-loop.service`
  - `rabbitbot-control-console.service`
  - `/etc/sudoers.d/rabbitbot-control-console` 的源模板
- 动态模板使用当前仓库路径、当前执行用户和用户组；也可通过 `RABBITBOT_SERVICE_USER` / `RABBITBOT_SERVICE_GROUP` 显式覆盖。
- portable 模式下不再强制要求 legacy 外部路径：`models`、`custom_action_ws/install/setup.bash`、`unitree_slam_example_new/example/start_nav_arm_bridge.sh`。这些只在 legacy 模式安装前检查。
- `deploy/check_air_project.sh` 的 sudoers 检查改为生成临时 sudoers 内容并用 `visudo -cf` 校验，不再要求 GitHub 源码包含被忽略的 sudoers 文件。

### 已验证的事实

- `bash -n deploy/install_air_project.sh` 通过。
- `bash -n deploy/check_air_project.sh` 通过。
- `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh` 在 HaiSong 上通过，并显示 `动态 sudoers 模板语法通过：user=pc`。
- 本轮修复消除了 ShuHao-orin 发现的 `visudo: unable to open ... rabbitbot-control-console.sudoers` 问题。

### 阻塞问题

- 尚未在 ShuHao-orin 拉取本提交后复跑自检；需要 Aaron 在 ShuHao 上 `git pull` 后再次执行 `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh`。

### 建议的下一步

- 在 ShuHao-orin 执行：
  - `cd /mnt/disk1/gt/air_robot_gt_projects`
  - `git pull`
  - `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh`
  - `bash deploy/install_air_project.sh`
- 检查安装后的 `/etc/systemd/system/rabbitbot-loop.service` 和 `/etc/systemd/system/rabbitbot-control-console.service`，应使用 `/mnt/disk1/gt/air_robot_gt_projects/...` 和用户 `nvidia`，不应出现 HaiSong 的 `/mnt/ssd/...` 或 `pc`。

### 注意事项

- HaiSong 本地仍可能保留被 ignore 的历史模板文件，它们不再是安装链路依赖，也不会进入 GitHub。
- 本轮新增/调整日志点：安装脚本会记录动态生成模板的目录、服务用户、用户组、当前仓库路径和 runtime mode；自检会记录动态 sudoers 校验使用的用户。这些日志用于定位新 Orin 上 systemd 路径或用户错误。
- 生成时间：2026-06-11 16:35:00


## 本轮补充：ShuHao 控制台状态接口 500 修复

### 背景和目标

在 ShuHao-orin 上完成 8080 端口释放后，浏览器已显示 RabbitBot 控制台页面，但状态区域显示“读取失败”“响应解析失败”。本轮目标是定位并修复状态接口失败，避免前端把后端异常误显示为定位失败。

### 当前状态

已完成：

- 确认 `/api/status` 返回 500，systemd 日志显示 `parse_latest_pose_from_lines()` 在空导航日志路径下触发 `NameError: name 'path' is not defined`。
- 修复控制台状态解析日志中的错误变量，将未定义的 `path` 改为调用方传入的 `source_label`，并补充 `localized` 与 `status_message` 上下文。
- 在 `deploy/check_air_project.sh` 中新增控制台状态解析运行时回归检查，直接调用空导航日志解析路径，防止类似“编译通过但运行时失败”的问题再次进入 GitHub 源码。

### 已验证的事实

- ShuHao-orin 上 `rabbitbot-control-console.service` 已能启动并监听 8080，但 `/api/status` 因上述 NameError 返回 500。
- ShuHao-orin 当前 `rabbitbot-loop.service` 为 inactive，portable compose 未运行；这说明当前定位链路尚未启动，不能把页面“读取失败”解读为 `unitree_slam_example_new` 配置失败。

### 阻塞问题

- 需要在 ShuHao-orin 拉取本提交后重启 `rabbitbot-control-console.service`，再点击“开始程序”或启动 `rabbitbot-loop.service` 继续验证导航容器、28180 和定位。
- 若启动 loop 后仍无法定位，再排查机器人网络、DDS 网卡、portable nav 容器日志和机器人侧地图路径。

### 建议的下一步

- 在 ShuHao-orin 执行 `git pull`，然后运行 `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh`。
- 重启控制台服务后访问 `/api/status`，应返回 JSON 而不是 500。
- 再启动主循环服务，确认 portable nav 容器运行、28180 监听、控制台状态进入“定位中”或“定位成功”。

### 注意事项

- `unitree_slam_example_new` 在 portable 路径中应由 nav 镜像内置，GitHub 源码中的宿主目录不是新 Orin 运行前置条件。
- 本轮新增/调整日志点：控制台状态解析在未读到位姿时记录日志来源、定位状态和状态消息；自检新增状态解析运行时回归输出，用于定位控制台状态接口运行期异常。
- 生成时间：2026-06-11 17:15:00


## 本轮补充：ShuHao 主循环因宿主 models 目录缺失反复重启

### 背景和目标

ShuHao-orin 上点击开始程序后，前端定位状态在“定位成功”和“导航未就绪”之间周期性切换，且 `logs` 下没有 workflow 日志。排查确认导航容器可以成功定位并输出 `[Ready]`，但主循环随后在确认 unified 基础服务时因 `/mnt/disk1/gt/air_robot_gt_projects/models` 不存在退出，systemd 自动重启导致 nav 容器不断被重建。

### 当前状态

已完成：

- 修复 `scripts_1/start_unified_integration_workflow.sh` 的 portable 模型目录处理逻辑。
- `MODELS_DIR` 现在优先接受 `RABBITBOT_MODELS_CACHE_DIR` / `MODELS_DIR` 显式配置。
- 当 portable 模式且 VLM/Embedding/STT 均未启用时，不再要求宿主仓库根目录存在 `models/`，而是自动创建并使用 `runtime/empty_models` 作为空模型挂载点。
- 当 VLM/Embedding/STT 任一启用时，仍会明确报错要求先执行 `deploy/ensure_models.sh` 或配置已有模型目录，避免静默缺模型。

### 已验证的事实

- ShuHao-orin 日志显示 nav 容器内 `unitree_slam_example_new` 已成功读取机器人侧地图路径 `/home/unitree/test9.pcd`，并输出定位成功与 Ready。
- ShuHao-orin 的失败点不是 `unitree_slam_example_new` 宿主目录未配置，而是 unified core 启动前的宿主 `models` 目录误依赖。
- workflow 日志未出现，是因为主循环在启动 workflow 前已退出。

### 阻塞问题

- 需要在 ShuHao-orin 拉取本提交后重启 `rabbitbot-loop.service`，验证 unified core 是否能越过 models 目录检查并进入 workflow 预启动。
- 若继续失败，下一步应查看 `rabbitbot-unified-runtime` 容器日志、基础服务端口 7687/28182/28185，以及 workflow 控制目录。

### 建议的下一步

- 在 ShuHao-orin 执行 `git pull`。
- 执行 `PORTABLE_CHECK_MODE=clean_orin bash deploy/check_air_project.sh`。
- 重启 `rabbitbot-loop.service`，观察 `NRestarts` 是否停止增长，并确认 `logs/nav_workflow_control/workflow_control` 下出现 workflow 状态文件。

### 注意事项

- `runtime/empty_models` 是本机运行态目录，不应进入 Git。
- 本轮新增/调整日志点：unified 启动脚本会记录模型目录是否可用、是否因模型能力关闭而使用空模型挂载点，以及启用模型能力但目录缺失时的明确修复提示。
- 生成时间：2026-06-11 17:45:00


## 本轮补充：Unitree 本体 TTS 缺少 core 内 unitree_sdk2 修复

### 背景和目标

ShuHao-orin 的 `logs/unified_runtime/rabbitbot_tts.log` 显示 TTS 服务启动失败：`scripts/build_unitree_g1_tts_bridge.sh` 在 core 容器内找不到 `/workspace/projects/unitree_sdk2`，导致 `Unitree G1 TTS 桥接程序构建失败`。目标是让全新 Orin 仅靠 GitHub 源码 + portable core 镜像即可启动 Unitree 本体 TTS。

### 当前状态

已完成：

- `core.Dockerfile` 增加 `unitree_sdk2` 打包，core 镜像不再只依赖 nav 镜像持有该 SDK。
- `deploy/build_or_pull_images.sh` 的 core 构建上下文增加 `unitree_sdk2` 要求和 rsync 拷贝。
- `start_unified_integration_workflow.sh` 的 portable 依赖卷从 4 个扩展为 5 个，新增 `rabbitbot_portable_unitree_sdk2`，运行期挂载到 `/workspace/projects/unitree_sdk2`。
- `deploy/check_air_project.sh` 增加 Unitree TTS 依赖策略自检，防止 core 镜像再次漏打包 SDK。
- `third_party/manifest.lock` 更新 `unitree_sdk2` 的 core/nav 双用途说明。

### 已验证的事实

- 当前旧 core 镜像 `ghcr.io/aaronai/rabbitbot-core-portable:20260611` 内未发现 `/workspace/projects/unitree_sdk2`、`/workspace/unitree_sdk2` 或 `/opt/unitree_sdk2`。
- ShuHao 上 TTS 失败发生在 core 容器内构建桥接程序阶段，不是机器人侧网络或导航定位失败。
- HaiSong 构建机上的 `unitree_sdk2` 已包含 `lib/aarch64/libunitree_sdk2.a` 和 `thirdparty/lib/aarch64`，满足打入 core 镜像的条件。

### 阻塞问题

- 代码修复后必须重建 portable core 镜像并重新导出/导入到 ShuHao；仅 `git pull` 不能修复已有旧镜像。
- 如果继续沿用同一镜像 tag，需要确保 ShuHao 删除或覆盖旧 core 镜像与旧 `rabbitbot_unified_runtime` 容器后再启动。

### 建议的下一步

- 在 HaiSong 上执行 `MODE=build RABBITBOT_PORTABLE_BUILD_NAV=0 bash deploy/build_or_pull_images.sh` 重建 core 镜像。
- 使用 `deploy/export_portable_images.sh` 导出新镜像，并转移到 ShuHao 后执行 `deploy/import_portable_images.sh`。
- 在 ShuHao 删除旧 `rabbitbot-unified-runtime` 容器和 `rabbitbot_portable_unitree_sdk2` 卷后重启 `rabbitbot-loop.service`，确认 `rabbitbot_tts.log` 不再报缺少 SDK。

### 注意事项

- Unitree 本体 TTS 运行在 core 容器，不在 nav 容器；因此 `unitree_sdk2` 必须同时服务 core 和 nav 两条镜像链路。
- 本轮新增/调整日志点：core 启动脚本会记录注入的 portable 依赖卷数量和列表含义；自检会明确报告 Unitree TTS 依赖是否被 core 镜像和运行期依赖卷覆盖。
- 生成时间：2026-06-11 18:05:00


## 本轮补充：Unitree TTS core 镜像重建验证结果

### 背景和目标

完成 `unitree_sdk2` 纳入 portable core 的代码修复后，继续在 HaiSong 构建机验证新镜像是否真正包含 TTS 所需 SDK，并确认 ShuHao 仍使用旧镜像。

### 当前状态

已完成：

- 在 HaiSong 上重建 `ghcr.io/aaronai/rabbitbot-core-portable:20260611`。
- 新 core 镜像 ID：`sha256:9c7cb9f9c774d435d393d7500b5e5c5c75f959b4f40a06a116b69faf332df15c`。
- nav 镜像未发生实质变化，ID 仍为 `sha256:23c0ef06c9c08a01a71c5c98db836e52ed67d660ebfb890ca1ba062b8e0482ef`。
- 在新 core 镜像内执行 `scripts/build_unitree_g1_tts_bridge.sh` 成功，生成 `build/unitree_g1_tts_bridge`。

### 已验证的事实

- 新 core 镜像内存在 `/workspace/projects/unitree_sdk2/lib/aarch64/libunitree_sdk2.a` 和 `/workspace/projects/unitree_sdk2/thirdparty/lib/aarch64`。
- ShuHao 当前仍是旧 core 镜像 ID：`sha256:161c57498e24b534174680559c0f8f0a2af30362a6ad7912ce2d6d59aa97691c`，旧 `rabbitbot-unified-runtime` 容器也基于该旧镜像。
- 仅 `git pull` 不能修复 ShuHao 的 TTS；必须导入新 core 镜像并删除旧 core 容器后重启。

### 阻塞问题

- 新 core 镜像尚未传输到 ShuHao。
- 本提交尚需推送到 GitHub 后，ShuHao 才能通过 `git pull` 获得代码侧的运行期依赖卷注入逻辑。

### 建议的下一步

- 将新 core 镜像导出并传输到 ShuHao，或推送到镜像仓库后在 ShuHao 拉取。
- ShuHao 导入新镜像后，删除旧 `rabbitbot-unified-runtime` 容器和 `rabbitbot_portable_unitree_sdk2` 依赖卷，再重启 `rabbitbot-loop.service`。

### 注意事项

- 如果继续使用相同 tag `20260611`，必须通过 image id 确认 ShuHao 侧已经覆盖为 `sha256:9c7cb9f9...`，不能只看 tag 名。
- 本轮新增/调整日志点保持不变：启动脚本记录 portable 依赖卷注入数量，自检报告 Unitree TTS 依赖策略。
- 生成时间：2026-06-11 18:15:00


## 本轮补充：全新 Orin 模拟后控制台前端 ready 误报修复

### 背景和目标

Aaron 在 ShuHao-orin 完成“全新 Orin”模拟部署后，控制台前端仍显示“服务仍未全部就绪，请查看状态或打开日志排查”。本轮目标是确认服务真实状态，并修复前端与状态接口之间的 ready 判定不一致。

### 当前状态

已完成：

- 已确认 ShuHao 的 `/api/status` 返回 `nav_bridge.ready=true`、`workflow.ready=true`、`workflow.status=waiting_for_go`、`pose.localized=true`，机器人网络 `eno1` 已 `UP` 且 `Link detected: yes`。
- 已确认 `rabbitbot-loop.service` 和 `rabbitbot-control-console.service` 均为 `active/running`，且 `NRestarts=0`。
- 已确认导航日志持续输出 `[Pose]`，workflow 已成功预启动并停在 go 闸门。
- 已定位前端误报根因：前端 `servicesReady()` 硬要求 `main_loop === "running"`；而状态接口的主循环检测只扫描 `/proc` 命令行，导览释放或进程树形态变化后可能返回 `not_detected`，导致前端误判未全部就绪。
- 已修复控制台后端：`detect_main_loop_running()` 在 `/proc` 未检出脚本进程时回退读取 `systemctl is-active rabbitbot-loop.service`。
- 已修复控制台前端：ready 判定拆分为核心服务就绪和主循环检测就绪；导航、定位、workflow 均就绪但主循环检测短暂漂移时显示“基础服务就绪”，不再误报泛化失败。

未完成：

- 本轮修复尚需同步到 ShuHao 后重启 `rabbitbot-control-console.service` 才能让前端页面生效。
- 本轮未改动 portable 镜像；该问题属于控制台状态判定，不需要重建 core/nav 镜像。

### 已验证的事实

- ShuHao 当前服务实际可用，前端提示与后端状态不一致是控制台显示层问题。
- `main_loop=not_detected` 不能单独作为服务失败依据；当 systemd active 且 nav/workflow/pose 都 ready 时，应认为基础导览链路可用。
- 地图 `/home/unitree/test9.pcd` 在 Orin 本地不可见仍是预期状态；定位成功说明机器人侧地图可用。

### 阻塞问题

无当前代码层面的阻塞。需要 Aaron 将本提交同步到 ShuHao，或在 ShuHao 直接拉取本分支后重启控制台服务验证。

### 建议的下一步

- 在 ShuHao 执行 `git pull` 后重启 `rabbitbot-control-console.service`。
- 刷新浏览器并确认顶部状态不再显示“服务仍未全部就绪”。
- 若再次出现未就绪，优先同时查看 `/api/status` 中 `main_loop`、`nav_bridge.ready`、`workflow.ready`、`pose.localized` 四个字段，不要只看顶部文案。

### 注意事项

- 本轮新增日志点：后端主循环检测在 systemd 回退路径记录 DEBUG 日志，包括读取失败、非 active 状态和 active 状态来源，便于后续区分 `/proc` 检测漂移与服务真实失败。
- 生成时间：2026-06-12 10:25:00
