#!/usr/bin/env bash
# 启动导航桥接并用外部命令控制 DOCX workflow 循环。
#
# 主终端运行本脚本后，会先拉起导航桥接，持续显示导航输出；其它终端通过：
#   bash scripts_1/send_nav_workflow_command.sh go
#   bash scripts_1/send_nav_workflow_command.sh back
#   bash scripts_1/send_nav_workflow_command.sh arrive
# 控制 workflow 开始、无机器人模式点位到达确认和剧本结束后的返航。
#
# 为降低 go 后开场延迟，本脚本会在等待 go 前预启动 workflow，让 Python 和 AppContext
# 初始化完成后默认进入 QA 状态，听到“开始导览”后再释放剧本导览；如需恢复旧外部 go 闸门，
# 设置 RABBITBOT_NAV_WORKFLOW_VOICE_START=0。相关可调变量：
#   RABBITBOT_NAV_WORKFLOW_VOICE_START：默认 1，启动后先进入 QA 并等待“开始导览”语音口令。
#   RABBITBOT_NAV_WORKFLOW_START_VLM：默认 1，loop QA 状态需要 VLM 模型服务；显式设 0 才跳过。
#   RABBITBOT_NAV_WORKFLOW_START_EMBEDDING：默认 1，QA 记忆/语义检索链路需要 Embedding 服务；显式设 0 才跳过。
#   RABBITBOT_NAV_WORKFLOW_NO_ROBOT：默认 0；设为 1 时进入无机器人模式，跳过真实导航桥接，点位到达由 arrive 命令确认。
#   RABBITBOT_NAV_WORKFLOW_GATE_READY_TIMEOUT_SECONDS：旧外部 go 模式下等待 workflow 预启动就绪的超时秒数。
#   RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS：workflow 内部等待 go 闸门文件的轮询间隔。
#   RABBITBOT_NAV_WORKFLOW_STATUS_POLL_SECONDS：workflow 运行期间检查状态和预接收 back 的轮询间隔。
#   RABBITBOT_TTS_STRICT_FAILURE：TTS 失败是否终止 workflow，默认 0，即记录错误并继续。
#   RABBITBOT_NAV_WORKFLOW_HEALTH_CHECK_INTERVAL_SECONDS：等待命令和运行期间的健康检查间隔秒数。
#   RABBITBOT_NAV_WORKFLOW_LOST_PROCESS_GRACE_SECONDS：workflow 进程丢失后等待状态文件落盘的宽限秒数。
#   RABBITBOT_NAV_WORKFLOW_BACK_RETRY_LIMIT：返航失败后自动恢复导航桥接并重试的次数，默认 1。
#   RABBITBOT_NAV_CORE_READY_TIMEOUT_SECONDS：启动导航桥接后等待导航核心输出 Pose/Ready 的秒数，默认 90。
#   RABBITBOT_NAV_CORE_READY_POLL_SECONDS：等待导航核心就绪时的轮询间隔秒数，默认 2。
#   RABBITBOT_DIALOGUE_INDEX：选择 conf/dialogue_<序号>.json，未设置时默认 0。
#   RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX：旧版台词序号变量，仅在 RABBITBOT_DIALOGUE_INDEX 未设置时兜底。
#   RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE：直接指定台词 JSON 文件完整路径，优先级高于序号。
#   NAV_PCD_PATH：显式指定导航桥接地图；未设置时优先读取当前台词 JSON 的 map_file。
#   NAV_MAP_BASE_DIR：台词 map_file 为相对文件名时拼接的地图目录，默认 /home/unitree。
#   back_points：可在当前台词 JSON 顶层配置返航点位；未配置时按 go 点位序列反序返航。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECTS_DIR="${RABBITBOT_PROJECTS_DIR:-$(cd "${PROJECT_DIR}/.." && pwd)}"
MODELS_DIR="${MODELS_DIR:-${RABBITBOT_MODELS_CACHE_DIR:-${PROJECTS_DIR}/models}}"
MODEL_ENSURE_SCRIPT="${MODEL_ENSURE_SCRIPT:-${PROJECTS_DIR}/deploy/ensure_models.sh}"
NAV_EXAMPLE_DIR="${NAV_EXAMPLE_DIR:-${PROJECTS_DIR}/unitree_slam_example_new/example}"
NAV_BRIDGE_RUNTIME="${RABBITBOT_NAV_RUNTIME:-host}"
NAV_BRIDGE_SCRIPT_DEFAULT="${NAV_EXAMPLE_DIR}/start_nav_arm_bridge.sh"
if [ "${NAV_BRIDGE_RUNTIME}" = "compose" ]; then
    NAV_BRIDGE_SCRIPT_DEFAULT="${PROJECT_DIR}/scripts_1/start_nav_bridge_portable.sh"
fi
NAV_BRIDGE_SCRIPT="${NAV_BRIDGE_SCRIPT:-${NAV_BRIDGE_SCRIPT_DEFAULT}}"
NAV_INTERFACE="${NAV_INTERFACE:-${RABBITBOT_DDS_INTERFACE:-eno1}}"
NAV_PCD_PATH_WAS_EXPLICIT=0
if [ -n "${NAV_PCD_PATH+x}" ] && [ -n "${NAV_PCD_PATH}" ]; then
    NAV_PCD_PATH_WAS_EXPLICIT=1
else
    NAV_PCD_PATH=""
fi
DEFAULT_NAV_PCD_PATH="${DEFAULT_NAV_PCD_PATH:-${RABBITBOT_NAV_MAP_PATH:-/home/unitree/test1.pcd}}"
NAV_MAP_BASE_DIR="${NAV_MAP_BASE_DIR:-/home/unitree}"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
WS_SETUP="${WS_SETUP:-${PROJECTS_DIR}/custom_action_ws/install/setup.bash}"
CONTAINER_NAME="${CONTAINER_NAME:-rabbitbot-unified-runtime}"

# 基础服务运行方式：unified=单容器(旧，默认)；compose=解耦多容器(docker/portable/docker-compose.decoupled.yaml)。
RABBITBOT_BASE_RUNTIME="${RABBITBOT_BASE_RUNTIME:-unified}"
RABBITBOT_DECOUPLED_COMPOSE_FILE="${RABBITBOT_DECOUPLED_COMPOSE_FILE:-${PROJECT_DIR}/docker/portable/docker-compose.decoupled.yaml}"
RABBITBOT_WORKFLOW_CONTAINER_NAME="${RABBITBOT_WORKFLOW_CONTAINER_NAME:-rabbitbot-workflow}"
if [ "${RABBITBOT_BASE_RUNTIME}" = "compose" ]; then
    # 解耦模式：导览 workflow 跑在专用 rabbitbot-workflow 容器内，所有 docker exec 都指向它。
    CONTAINER_NAME="${RABBITBOT_WORKFLOW_CONTAINER_NAME}"
    # nav 也归解耦 compose 管理：运行方式视为 compose，容器名/服务名对齐 rabbitbot-navbridge，
    # 真实机器人模式下由解耦栈唯一提供 28180，避免与旧 host/portable nav 冲突。
    NAV_BRIDGE_RUNTIME="compose"
    RABBITBOT_NAV_BRIDGE_CONTAINER_NAME="${RABBITBOT_NAV_BRIDGE_CONTAINER_NAME:-rabbitbot-navbridge}"
    RABBITBOT_NAVBRIDGE_SERVICE="${RABBITBOT_NAVBRIDGE_SERVICE:-rabbitbot-navbridge}"
fi
CONTAINER_RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR:-/workspace/projects/rabbitbot-dev-ros2-master}"
CONTAINER_LOG_DIR="${CONTAINER_LOG_DIR:-${CONTAINER_RABBITBOT_DIR%/*}/logs/unified_runtime}"
HOST_LOG_DIR="${HOST_LOG_DIR:-${PROJECTS_DIR}/logs}"
CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTROL_DIR:-/tmp/rabbitbot_nav_workflow_control}"
COMMAND_FILE="${RABBITBOT_NAV_WORKFLOW_COMMAND_FILE:-${CONTROL_DIR}/command}"
RUN_DIR="${HOST_LOG_DIR}/nav_workflow_control"
POINT_1_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_1:-(1.9105, -1.6180, -0.0029, 0.0265, -0.2046, 0.9785)}"
POINT_1_TO_2_TRANSITION_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_1_TO_2_TRANSITION:-(8.6465, -2.5763, 0.0547, 0.0907, 0.5347, 0.8384)}"
POINT_2_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_2:-(10.1203, 0.8162, 0.0904, 0.0373, 0.9074, 0.4087)}"
POINT_3_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_3:-(11.1090, 4.3229, 0.0937, 0.0170, 0.9717, 0.2162)}"
POINT_3_TO_5_TRANSITION_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_3_TO_5_TRANSITION:-(5.5507, 14.4097, 0.0779, 0.0578, 0.7806, 0.6174)}"
POINT_5_TASK="${RABBITBOT_NAV_WORKFLOW_POINT_5:-(4.7039, 20.4749, 0.0876, -0.0269, 0.9076, -0.4096)}"
BACK_POINT_1_TASK="${RABBITBOT_NAV_WORKFLOW_BACK_POINT_1:-(6.4327, 8.2585, 0.0505, 0.0827, 0.5996, -0.7944)}"
BACK_POINT_2_TASK="${RABBITBOT_NAV_WORKFLOW_BACK_POINT_2:-(9.8023, -3.1366, -0.0442, 0.0674, 0.9944, 0.0684)}"
START_POINT_TASK="${RABBITBOT_NAV_WORKFLOW_START_POINT:-${POINT_1_TASK}}"
BACK_TIMEOUT_SECONDS="${RABBITBOT_NAV_WORKFLOW_BACK_TIMEOUT_SECONDS:-240}"
COMMAND_POLL_SECONDS="${RABBITBOT_NAV_WORKFLOW_COMMAND_POLL_SECONDS:-0.2}"
WORKFLOW_STATUS_POLL_SECONDS="${RABBITBOT_NAV_WORKFLOW_STATUS_POLL_SECONDS:-0.2}"
WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS:-420}"
WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS:-600}"
RABBITBOT_NAV_WORKFLOW_NO_ROBOT="${RABBITBOT_NAV_WORKFLOW_NO_ROBOT:-0}"
RABBITBOT_LANSHI_GUIDE_MODE="${RABBITBOT_LANSHI_GUIDE_MODE:-0}"
RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION:-0}"
if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" = "1" ]; then
    RABBITBOT_WORKFLOW_NON_INTEGRATION="1"
    RABBITBOT_UNIFIED_START_ROBOT_AGENT="0"
fi
RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE:-0}"
RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN:-0}"
RABBITBOT_NAV_WORKFLOW_START_VLM="${RABBITBOT_NAV_WORKFLOW_START_VLM:-1}"
RABBITBOT_NAV_WORKFLOW_START_EMBEDDING="${RABBITBOT_NAV_WORKFLOW_START_EMBEDDING:-1}"
RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM:-${RABBITBOT_NAV_WORKFLOW_START_VLM}}"
RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING:-${RABBITBOT_NAV_WORKFLOW_START_EMBEDDING}}"
RABBITBOT_TTS_STRICT_FAILURE="${RABBITBOT_TTS_STRICT_FAILURE:-0}"
RABBITBOT_NAV_WORKFLOW_VOICE_START="${RABBITBOT_NAV_WORKFLOW_VOICE_START:-1}"
RABBITBOT_NAV_WORKFLOW_GO_TEXT="${RABBITBOT_NAV_WORKFLOW_GO_TEXT:-开始导览}"
RABBITBOT_NAV_WORKFLOW_BACK_TEXT="${RABBITBOT_NAV_WORKFLOW_BACK_TEXT:-返回起点}"
RABBITBOT_STT_EXEC_URL="${RABBITBOT_STT_EXEC_URL:-http://127.0.0.1:28184/exec}"
if [ "${RABBITBOT_NAV_WORKFLOW_VOICE_START}" = "1" ]; then
    # 语音启动导览必须依赖 STT 常驻；即使 portable.env 默认关闭 STT，这里也要为 loop 场景打开。
    RABBITBOT_UNIFIED_START_STT="1"
else
    RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT:-0}"
fi
RABBITBOT_DIALOGUE_INDEX="${RABBITBOT_DIALOGUE_INDEX:-}"
RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX="${RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX:-}"
RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE="${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE:-}"
HOST_WORKFLOW_RUN_DIR="${RABBITBOT_NAV_WORKFLOW_HOST_RUN_DIR:-${RUN_DIR}}"
CONTAINER_WORKFLOW_RUN_DIR="${RABBITBOT_NAV_WORKFLOW_CONTAINER_RUN_DIR:-${CONTAINER_RABBITBOT_DIR%/*}/logs/nav_workflow_control}"
HOST_WORKFLOW_CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_HOST_CONTROL_DIR:-${HOST_WORKFLOW_RUN_DIR}/workflow_control}"
CONTAINER_WORKFLOW_CONTROL_DIR="${RABBITBOT_NAV_WORKFLOW_CONTAINER_CONTROL_DIR:-${CONTAINER_WORKFLOW_RUN_DIR}/workflow_control}"
WORKFLOW_GATE_READY_TIMEOUT_SECONDS="${RABBITBOT_NAV_WORKFLOW_GATE_READY_TIMEOUT_SECONDS:-30}"
WORKFLOW_GATE_POLL_SECONDS="${RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS:-0.05}"
HEALTH_CHECK_INTERVAL_SECONDS="${RABBITBOT_NAV_WORKFLOW_HEALTH_CHECK_INTERVAL_SECONDS:-5}"
WORKFLOW_LOST_PROCESS_GRACE_SECONDS="${RABBITBOT_NAV_WORKFLOW_LOST_PROCESS_GRACE_SECONDS:-5}"
NAV_BRIDGE_RESTART_WAIT_SECONDS="${RABBITBOT_NAV_WORKFLOW_NAV_RESTART_WAIT_SECONDS:-3}"
BACK_RETRY_LIMIT="${RABBITBOT_NAV_WORKFLOW_BACK_RETRY_LIMIT:-1}"
RETURN_FAILURE_WAIT_SECONDS="${RABBITBOT_NAV_WORKFLOW_RETURN_FAILURE_WAIT_SECONDS:-2}"
NAV_CORE_READY_TIMEOUT_SECONDS="${RABBITBOT_NAV_CORE_READY_TIMEOUT_SECONDS:-90}"
NAV_CORE_READY_POLL_SECONDS="${RABBITBOT_NAV_CORE_READY_POLL_SECONDS:-2}"
NAV_BRIDGE_CONTAINER_NAME="${RABBITBOT_NAV_BRIDGE_CONTAINER_NAME:-${RABBITBOT_PORTABLE_COMPOSE_PROJECT:-rabbitbot-portable}-rabbitbot-nav-1}"

nav_group_pid=""
workflow_tail_pid=""
queued_back_after_workflow=0
current_run_id=""
current_control_dir=""
current_host_control_dir=""
current_workflow_log=""
current_host_workflow_log=""
current_status_file=""
current_exit_code_file=""
current_pid_file=""
current_finished_at_file=""
current_gate_file=""
current_gate_ready_file=""
current_host_gate_file=""
current_host_gate_ready_file=""
current_return_request_file=""
current_host_return_request_file=""
current_manual_arrival_file=""
current_host_manual_arrival_file=""
current_nav_log=""
current_nav_start_epoch="0"
last_runtime_health_check_ms=0
nav_core_last_health_reason="not_checked"
nav_core_last_health_source="无"
nav_core_recent_log=""

log_info() {
    echo -e "\033[32m[INFO]\033[0m $1"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $1"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $1" >&2
}

now_ms() {
    date +%s%3N
}

elapsed_ms_since() {
    local start_ms="$1"
    echo $(( $(now_ms) - start_ms ))
}

require_path() {
    if [ ! -e "$1" ]; then
        log_error "缺少必要路径：$1"
        exit 1
    fi
}

dialogue_path_for_nav_map() {
    if [ -n "${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}" ]; then
        if [[ "${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}" == "${CONTAINER_RABBITBOT_DIR}"/* ]]; then
            echo "${PROJECT_DIR}${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE#${CONTAINER_RABBITBOT_DIR}}"
        else
            echo "${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}"
        fi
        return
    fi

    local dialogue_index="${RABBITBOT_DIALOGUE_INDEX:-${RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX:-0}}"
    echo "${PROJECT_DIR}/conf/dialogue_${dialogue_index}.json"
}

read_dialogue_map_file() {
    local dialogue_path="$1"
    python3 - "$dialogue_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(2)
data = json.loads(path.read_text(encoding="utf-8"))
print(str(data.get("map_file") or "").strip())
PY
}

read_dialogue_back_route() {
    local dialogue_path="$1"
    python3 - "$dialogue_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(2)
data = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("台词 JSON 根节点必须是对象")
points = data.get("points") or {}
if not isinstance(points, dict):
    raise SystemExit("台词 JSON points 必须是对象")

def point_name(key, point):
    if isinstance(point, dict):
        return str(point.get("name") or point.get("summary") or key).strip() or str(key)
    return str(key)

def first_location(point, context):
    if not isinstance(point, dict):
        raise SystemExit(f"{context} 必须是对象")
    locations = point.get("location")
    if not isinstance(locations, list) or not locations:
        raise SystemExit(f"{context}.location 必须是非空数组")
    item = locations[0]
    if not isinstance(item, dict):
        raise SystemExit(f"{context}.location[0] 必须是对象")
    missing = [field for field in ("x", "y", "ox", "oy", "oz", "ow") if field not in item]
    if missing:
        raise SystemExit(f"{context}.location[0] 缺少 28180 坐标字段: {missing}")
    values = []
    for field in ("x", "y", "ox", "oy", "oz", "ow"):
        try:
            values.append(float(item[field]))
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"{context}.location[0].{field} 必须是数字") from exc
    return "(" + ", ".join(f"{value:.10g}" for value in values) + ")"

def resolve_item(item, index, source):
    if isinstance(item, str):
        key = item.strip()
        if not key:
            raise SystemExit(f"{source}[{index}] 不能为空字符串")
        if key not in points:
            raise SystemExit(f"{source}[{index}] 指向未知 points key: {key}")
        point = points[key]
        return point_name(key, point), first_location(point, f"points.{key}")
    if isinstance(item, dict):
        key = str(item.get("point_key") or item.get("entity_key") or "").strip()
        if key:
            if key not in points:
                raise SystemExit(f"{source}[{index}] 指向未知 points key: {key}")
            point = points[key]
            return point_name(key, point), first_location(point, f"points.{key}")
        label = str(item.get("name") or item.get("summary") or f"返航点{index + 1}").strip()
        return label, first_location(item, f"{source}[{index}]")
    raise SystemExit(f"{source}[{index}] 必须是字符串或对象")

back_points = data.get("back_points")
route = []
source = "dialogue_back_points"
if back_points is not None and not isinstance(back_points, list):
    raise SystemExit("台词 JSON back_points 必须是数组")
if isinstance(back_points, list) and back_points:
    for index, item in enumerate(back_points):
        route.append(resolve_item(item, index, "back_points"))
else:
    source = "reverse_go_points"
    go_keys = []
    for step in data.get("steps") or []:
        if not isinstance(step, dict):
            continue
        key = str(step.get("entity_key") or "").strip()
        if not key or key not in points:
            continue
        if go_keys and go_keys[-1] == key:
            continue
        go_keys.append(key)
    if "point_1" in points and (not go_keys or go_keys[0] != "point_1"):
        go_keys.insert(0, "point_1")
    seen = set()
    reverse_keys = []
    for key in reversed(go_keys):
        if key in seen:
            continue
        seen.add(key)
        reverse_keys.append(key)
    for index, key in enumerate(reverse_keys):
        route.append(resolve_item(key, index, "reverse_go_points"))

if not route:
    raise SystemExit("无法从台词 JSON 生成 back 返航点位")
print(f"__SOURCE__\t{source}")
for label, payload in route:
    safe_label = label.replace("\t", " ").replace("\n", " ")
    print(f"{safe_label}\t{payload}")
PY
}

resolve_nav_pcd_path() {
    if [ "${NAV_PCD_PATH_WAS_EXPLICIT}" -eq 1 ]; then
        log_info "使用显式导航地图：NAV_PCD_PATH=${NAV_PCD_PATH}"
        return
    fi

    local dialogue_path
    local map_file
    dialogue_path="$(dialogue_path_for_nav_map)"
    if map_file="$(read_dialogue_map_file "${dialogue_path}" 2>/dev/null)" && [ -n "${map_file}" ]; then
        if [[ "${map_file}" = /* ]]; then
            NAV_PCD_PATH="${map_file}"
        else
            NAV_PCD_PATH="${NAV_MAP_BASE_DIR%/}/${map_file}"
        fi
        log_info "根据台词文件设置导航地图：dialogue=${dialogue_path}, map_file=${map_file}, NAV_PCD_PATH=${NAV_PCD_PATH}"
    else
        NAV_PCD_PATH="${DEFAULT_NAV_PCD_PATH}"
        log_warn "未能从台词文件读取 map_file，使用默认导航地图：dialogue=${dialogue_path}, NAV_PCD_PATH=${NAV_PCD_PATH}"
    fi
}

port_open() {
    local port="$1"
    timeout 2 bash -lc "</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1
}

http_ok() {
    local url="$1"
    local code
    code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "${url}" 2>/dev/null || true)"
    [ "${code}" = "200" ]
}

container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${CONTAINER_NAME}"
}

nav_bridge_group_alive() {
    [ -n "${nav_group_pid}" ] && kill -0 -- "-${nav_group_pid}" 2>/dev/null
}

collect_nav_core_recent_log() {
    local host_log=""
    local container_log=""
    local sources=()

    if [ -n "${current_nav_log}" ] && [ -f "${current_nav_log}" ]; then
        host_log="$(tail -n 200 "${current_nav_log}" 2>/dev/null || true)"
        if [ -n "${host_log}" ]; then
            sources+=("宿主日志:${current_nav_log}")
        fi
    fi

    if [ "${NAV_BRIDGE_RUNTIME}" = "compose" ] && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${NAV_BRIDGE_CONTAINER_NAME}"; then
        container_log="$(docker logs --since "${current_nav_start_epoch:-0}" --tail 240 "${NAV_BRIDGE_CONTAINER_NAME}" 2>&1 || true)"
        if [ -n "${container_log}" ]; then
            sources+=("容器日志:${NAV_BRIDGE_CONTAINER_NAME}")
        fi
    fi

    if [ "${#sources[@]}" -eq 0 ]; then
        nav_core_last_health_source="无"
    else
        local IFS=','
        nav_core_last_health_source="${sources[*]}"
    fi
    nav_core_recent_log="$(printf '%s\n%s\n' "${host_log}" "${container_log}")"
}

nav_core_log_healthy() {
    local recent_log
    nav_core_last_health_reason="not_ready"
    collect_nav_core_recent_log
    recent_log="${nav_core_recent_log}"

    if [ -z "$(printf '%s' "${recent_log}" | tr -d '[:space:]')" ]; then
        log_warn "导航核心日志尚不可读：host_log=${current_nav_log:-未设置}, container=${NAV_BRIDGE_CONTAINER_NAME}, source=${nav_core_last_health_source}"
        return 1
    fi

    if printf '%s' "${recent_log}" | grep -Eq '\[Ready\] Navigation system ready for commands!|\[Pose\]'; then
        nav_core_last_health_reason="ready"
        return 0
    fi

    if printf '%s' "${recent_log}" | grep -Eq 'does not match an available interface|DdsException|Failed to create domain|Aborted'; then
        nav_core_last_health_reason="fatal"
        log_warn "导航核心健康检查失败：检测到 DDS/网卡/进程异常，source=${nav_core_last_health_source}"
        return 1
    fi

    log_warn "导航核心尚未完成定位或未输出位姿：source=${nav_core_last_health_source}"
    return 1
}

wait_nav_core_ready() {
    local start_ms
    local elapsed_ms
    start_ms="$(now_ms)"
    log_info "等待导航核心输出 Pose/Ready：timeout=${NAV_CORE_READY_TIMEOUT_SECONDS}s, poll=${NAV_CORE_READY_POLL_SECONDS}s, host_log=${current_nav_log}, container=${NAV_BRIDGE_CONTAINER_NAME}, since=${current_nav_start_epoch}"
    while true; do
        if ! nav_bridge_group_alive; then
            elapsed_ms="$(elapsed_ms_since "${start_ms}")"
            log_error "导航桥接进程组已退出，无法继续等待核心就绪：elapsed_ms=${elapsed_ms}, pgid=${nav_group_pid:-未设置}"
            return 1
        fi
        if ! port_open 28180; then
            elapsed_ms="$(elapsed_ms_since "${start_ms}")"
            if [ "${elapsed_ms}" -ge $((NAV_CORE_READY_TIMEOUT_SECONDS * 1000)) ]; then
                log_warn "等待 28180 端口重新就绪超时：elapsed_ms=${elapsed_ms}, timeout=${NAV_CORE_READY_TIMEOUT_SECONDS}s"
                return 1
            fi
            log_warn "28180 端口暂未就绪，继续等待导航容器重建：elapsed_ms=${elapsed_ms}"
            sleep "${NAV_CORE_READY_POLL_SECONDS}"
            continue
        fi
        if nav_core_log_healthy; then
            elapsed_ms="$(elapsed_ms_since "${start_ms}")"
            log_info "导航核心已就绪：elapsed_ms=${elapsed_ms}, source=${nav_core_last_health_source}"
            return 0
        fi
        if [ "${nav_core_last_health_reason}" = "fatal" ]; then
            elapsed_ms="$(elapsed_ms_since "${start_ms}")"
            log_error "导航核心出现不可恢复异常：elapsed_ms=${elapsed_ms}, source=${nav_core_last_health_source}"
            return 1
        fi
        elapsed_ms="$(elapsed_ms_since "${start_ms}")"
        if [ "${elapsed_ms}" -ge $((NAV_CORE_READY_TIMEOUT_SECONDS * 1000)) ]; then
            log_warn "等待导航核心就绪超时：elapsed_ms=${elapsed_ms}, timeout=${NAV_CORE_READY_TIMEOUT_SECONDS}s, source=${nav_core_last_health_source}"
            return 1
        fi
        sleep "${NAV_CORE_READY_POLL_SECONDS}"
    done
}

nav_bridge_health_ok() {
    local problems=()
    if ! nav_bridge_group_alive; then
        problems+=("导航桥接进程组未运行")
    fi
    if ! port_open 28180; then
        problems+=("28180端口未监听")
    else
        local status_response=""
        status_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_status --form-string 'task=' 2>&1 || true)"
        if [ -z "${status_response}" ]; then
            problems+=("28180状态接口无响应")
        fi
    fi
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" != "1" ] && ! nav_core_log_healthy; then
        problems+=("导航核心未就绪")
    fi
    if [ "${#problems[@]}" -gt 0 ]; then
        log_warn "导航桥接健康检查失败：$(IFS='；'; echo "${problems[*]}")"
        return 1
    fi
    return 0
}

base_services_health_ok() {
    local problems=()
    if ! container_running; then
        problems+=("统一容器未运行")
    fi
    if ! http_ok http://127.0.0.1:28185/docs; then
        problems+=("TTS(28185)")
    fi
    if [ "${RABBITBOT_UNIFIED_START_STT}" = "1" ] && ! http_ok http://127.0.0.1:28184/docs; then
        problems+=("STT(28184)")
    fi
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" != "1" ]; then
        if ! port_open 7687; then
            problems+=("Neo4j(7687)")
        fi
        if ! http_ok http://127.0.0.1:28182/docs; then
            problems+=("Memory(28182)")
        fi
    fi
    if [ "${#problems[@]}" -gt 0 ]; then
        log_warn "统一基础服务健康检查失败：$(IFS='；'; echo "${problems[*]}")"
        return 1
    fi
    return 0
}

runtime_health_ok() {
    local stage="${1:-未知阶段}"
    local failed=0
    if ! base_services_health_ok; then
        failed=1
    fi
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" != "1" ] && ! nav_bridge_health_ok; then
        failed=1
    fi
    if [ "${failed}" = "1" ]; then
        log_warn "运行时健康检查未通过：stage=${stage}"
        return 1
    fi
    return 0
}

check_runtime_health_periodic() {
    local stage="$1"
    local now
    now="$(now_ms)"
    if [ "${last_runtime_health_check_ms}" = "0" ] || [ $((now - last_runtime_health_check_ms)) -ge $((HEALTH_CHECK_INTERVAL_SECONDS * 1000)) ]; then
        last_runtime_health_check_ms="${now}"
        runtime_health_ok "${stage}"
        return $?
    fi
    return 0
}

wait_port() {
    local port="$1"
    local seconds="$2"
    local count=0
    echo -n "等待端口 ${port} 就绪"
    until port_open "${port}"; do
        sleep 1
        count=$((count + 1))
        echo -n "."
        if [ "${count}" -ge "${seconds}" ]; then
            echo ""
            log_error "端口 ${port} 等待超时 (${seconds} 秒)"
            return 1
        fi
    done
    echo ""
    log_info "端口 ${port} 已就绪"
}

json_field() {
    local field="$1"
    python3 -c 'import json, sys
field = sys.argv[1]
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
else:
    print(data.get(field, ""))
' "${field}"
}

normalize_go_to_task() {
    local task="$1"
    python3 - "${task}" <<'PY'
import ast
import sys

def convert_pose(value):
    if isinstance(value, tuple) and len(value) == 7:
        # 28180 直接 go_to_async 接口使用 (x, y, ox, oy, oz, ow)，不包含 z。
        return (value[0], value[1], value[3], value[4], value[5], value[6])
    return value

raw = sys.argv[1]
try:
    parsed = ast.literal_eval(raw)
except Exception:
    print(raw)
    raise SystemExit(0)

if isinstance(parsed, list):
    parsed = [convert_pose(item) for item in parsed]
else:
    parsed = convert_pose(parsed)
print(repr(parsed))
PY
}

workflow_running() {
    docker exec "${CONTAINER_NAME}" bash -lc 'pgrep -f "[e]xamples/run_kuavo_agno.py" >/dev/null || pgrep -f "[s]cripts/run_kuavo_agno_workflow.py" >/dev/null || pgrep -f "[s]cripts/start_kuavo_agno_workflow.bash" >/dev/null || pgrep -f "[s]cripts_1/start_lanshi_product_guide.py" >/dev/null' >/dev/null 2>&1
}

current_workflow_process_active() {
    if [ -z "${current_pid_file}" ] || [ ! -s "${current_pid_file}" ]; then
        return 1
    fi
    local workflow_pid=""
    workflow_pid="$(cat "${current_pid_file}" 2>/dev/null || true)"
    if [ -z "${workflow_pid}" ]; then
        return 1
    fi
    docker exec "${CONTAINER_NAME}" bash -lc "kill -0 '${workflow_pid}' 2>/dev/null" >/dev/null 2>&1
}

stop_workflow_tail() {
    if [ -n "${workflow_tail_pid}" ] && kill -0 "${workflow_tail_pid}" 2>/dev/null; then
        kill "${workflow_tail_pid}" 2>/dev/null || true
        workflow_tail_pid=""
    fi
}

stop_current_workflow() {
    if [ -z "${current_run_id}" ] || [ -z "${current_pid_file}" ] || [ ! -s "${current_pid_file}" ]; then
        return 0
    fi
    local status=""
    status="$(cat "${current_status_file}" 2>/dev/null || true)"
    if [ "${status}" = "finished" ]; then
        return 0
    fi
    local workflow_pid=""
    workflow_pid="$(cat "${current_pid_file}" 2>/dev/null || true)"
    if [ -z "${workflow_pid}" ]; then
        return 0
    fi
    log_info "正在停止当前 workflow 进程组：run_id=${current_run_id}, pgid=${workflow_pid}"
    docker exec "${CONTAINER_NAME}" bash -lc "if kill -0 '${workflow_pid}' 2>/dev/null; then kill -TERM -- -'${workflow_pid}' 2>/dev/null || kill -TERM '${workflow_pid}' 2>/dev/null || true; sleep 2; kill -KILL -- -'${workflow_pid}' 2>/dev/null || kill -KILL '${workflow_pid}' 2>/dev/null || true; fi" >/dev/null 2>&1 || true
}

cleanup() {
    local reason="${1:-EXIT}"
    trap - INT TERM EXIT
    stop_workflow_tail
    stop_current_workflow
    stop_nav_bridge "${reason}"
}

trap 'cleanup INT; exit 130' INT
trap 'cleanup TERM; exit 143' TERM
trap 'cleanup EXIT' EXIT

prepare_runtime() {
    mkdir -p "${CONTROL_DIR}" "${RUN_DIR}" "${HOST_LOG_DIR}" "${HOST_WORKFLOW_RUN_DIR}" "${HOST_WORKFLOW_CONTROL_DIR}"
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" = "1" ]; then
        log_info "无机器人模式已启用：跳过导航桥接启动和地图可见性检查，workflow 导航点由 arrive 命令确认。"
    else
        resolve_nav_pcd_path
        if [ -e "${NAV_PCD_PATH}" ]; then
            log_info "导航地图文件存在：NAV_PCD_PATH=${NAV_PCD_PATH}"
        else
            log_warn "导航地图在 Orin 本地不可见：NAV_PCD_PATH=${NAV_PCD_PATH}；若地图由机器人/Unitree 导航服务侧读取且定位成功，这是可接受状态。迁移到新 Orin 时仍需确认该路径在机器人侧存在，或更新 runtime/portable.env 的 RABBITBOT_NAV_MAP_PATH。"
        fi
        require_path "${NAV_BRIDGE_SCRIPT}"
        if [ "${NAV_BRIDGE_RUNTIME}" != "compose" ]; then
            require_path "${ROS_SETUP}"
            require_path "${WS_SETUP}"
        fi
    fi
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
        require_path "${PROJECT_DIR}/scripts_1/start_lanshi_product_guide.py"
    else
        require_path "${PROJECT_DIR}/scripts_1/start_unified_integration_workflow.sh"
    fi
    rm -f "${COMMAND_FILE}"
    cleanup_stale_workflow_control_files
    log_info "控制命令文件：${COMMAND_FILE}"
    log_info "其它终端发送 go：bash ${PROJECT_DIR}/scripts_1/send_nav_workflow_command.sh go"
    log_info "其它终端发送 back：bash ${PROJECT_DIR}/scripts_1/send_nav_workflow_command.sh back"
    log_info "无机器人模式确认到达：bash ${PROJECT_DIR}/scripts_1/send_nav_workflow_command.sh arrive"
}

cleanup_stale_workflow_control_files() {
    local deleted_output find_status deleted_count
    set +e
    deleted_output="$(find "${HOST_WORKFLOW_CONTROL_DIR}" -maxdepth 1 -type f \( \
        -name "*.status" -o -name "*.pid" -o -name "*.ready" -o -name "*.exit_code" -o \
        -name "*.finished_at" -o -name "*.go" -o -name "*.arrive" -o -name "workflow_runner_*.sh" \) -print -delete 2>&1)"
    find_status=$?
    set -e

    if [ "${find_status}" -ne 0 ]; then
        log_warn "清理历史 workflow 控制文件失败：dir=${HOST_WORKFLOW_CONTROL_DIR}, error=${deleted_output}"
        return 0
    fi

    deleted_count="$(printf '%s\n' "${deleted_output}" | sed '/^$/d' | wc -l | tr -d ' ')"
    log_info "已清理历史 workflow 控制文件：dir=${HOST_WORKFLOW_CONTROL_DIR}, count=${deleted_count}"
}

stop_nav_bridge() {
    local reason="${1:-未知原因}"
    if nav_bridge_group_alive; then
        log_info "正在停止导航桥接进程组：pgid=${nav_group_pid}, reason=${reason}"
        kill -TERM -- "-${nav_group_pid}" 2>/dev/null || true
        sleep 2
        kill -KILL -- "-${nav_group_pid}" 2>/dev/null || true
    fi
    nav_group_pid=""
}

identify_port_28180_holder() {
    # 识别 28180 占用者：core_robot_app（统一容器内 robot_app.py）、
    # nav_bridge_container（已有 portable nav 容器，compose 可直接重建接管）、unknown。
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${CONTAINER_NAME}" \
        && docker exec "${CONTAINER_NAME}" bash -lc 'pgrep -f "[u]vicorn robot_app:app" >/dev/null' >/dev/null 2>&1; then
        echo "core_robot_app"
        return 0
    fi
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -Eq 'rabbitbot-nav'; then
        echo "nav_bridge_container"
        return 0
    fi
    echo "unknown"
}

start_nav_bridge() {
    if port_open 28180; then
        # 只拒绝“非本次 nav bridge 管理的占用”：已有 portable nav 容器可被 compose 重建接管。
        local port_holder
        port_holder="$(identify_port_28180_holder)"
        case "${port_holder}" in
            core_robot_app)
                log_error "28180 已被统一容器内 robot_app.py 占用：portable 模式下 core 不应启动 Robot Agent，28180 应由 nav bridge 的 humble_robot_agent_bridge 提供。"
                log_error "处理方法：确认 runtime/portable.env 中 RABBITBOT_UNIFIED_START_ROBOT_AGENT=0，然后重建统一容器（RECREATE_CONTAINER=1 或 docker rm -f ${CONTAINER_NAME} 后重启主循环）。"
                return 1
                ;;
            nav_bridge_container)
                if [ "${NAV_BRIDGE_RUNTIME}" = "compose" ]; then
                    log_warn "28180 当前由已有 portable nav 容器占用；compose 启动会重建该容器并接管端口，继续。"
                else
                    log_error "28180 被 portable nav 容器占用，但当前导航运行方式为 host。请先停止 portable nav 容器（docker compose down）或切换 RABBITBOT_NAV_RUNTIME=compose。"
                    return 1
                fi
                ;;
            *)
                log_error "28180 端口已被未知进程占用，无法由本脚本统一拉起导航桥接。请先排查并停止占用进程：ss -ltnp | grep 28180 或 lsof -i :28180。"
                return 1
                ;;
        esac
    fi

    local nav_log="${RUN_DIR}/nav_bridge_$(date +%Y%m%d_%H%M%S).log"
    current_nav_log="${nav_log}"
    current_nav_start_epoch="$(date +%s)"
    log_info "启动导航桥接：runtime=${NAV_BRIDGE_RUNTIME}, script=${NAV_BRIDGE_SCRIPT}, interface=${NAV_INTERFACE}, map=${NAV_PCD_PATH}"
    log_info "导航桥接日志：${nav_log}"
    if [ "${RABBITBOT_BASE_RUNTIME}" = "compose" ]; then
        # 解耦栈：nav 由 docker-compose.decoupled.yaml 的 rabbitbot-navbridge 提供；前台 compose up 作为进程组，
        # 复用既有 nav 生命周期（停止进程组=停止该容器），就绪由 wait_nav_core_ready 读取该容器日志判断。
        setsid bash -lc 'RABBITBOT_DDS_INTERFACE="$1" RABBITBOT_NAV_MAP_PATH="$2" docker compose -f "$5" up --force-recreate "$3" 2>&1 | tee -a "$4"' bash "${NAV_INTERFACE}" "${NAV_PCD_PATH}" "${RABBITBOT_NAVBRIDGE_SERVICE:-rabbitbot-navbridge}" "${nav_log}" "${RABBITBOT_DECOUPLED_COMPOSE_FILE}" &
    elif [ "${NAV_BRIDGE_RUNTIME}" = "compose" ]; then
        setsid bash -lc '"$1" "$2" "$3" 2>&1 | tee -a "$4"' bash "${NAV_BRIDGE_SCRIPT}" "${NAV_INTERFACE}" "${NAV_PCD_PATH}" "${nav_log}" &
    else
        setsid bash -lc 'source "$1" && source "$2" && "$3" "$4" "$5" 2>&1 | tee -a "$6"' bash "${ROS_SETUP}" "${WS_SETUP}" "${NAV_BRIDGE_SCRIPT}" "${NAV_INTERFACE}" "${NAV_PCD_PATH}" "${nav_log}" &
    fi
    nav_group_pid=$!
    log_info "导航桥接进程组已启动：pgid=${nav_group_pid}"
    wait_port 28180 60
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
        log_info "兰石原地导览不执行导航移动，跳过导航核心 Pose/Ready 等待，仅保留 28180 动作桥接。"
    else
        wait_nav_core_ready
    fi
}

restart_nav_bridge() {
    local reason="${1:-健康检查失败}"
    log_warn "准备重启导航桥接：reason=${reason}"
    stop_nav_bridge "${reason}"
    sleep "${NAV_BRIDGE_RESTART_WAIT_SECONDS}"
    start_nav_bridge
}

restart_unified_services() {
    local reason="${1:-健康检查失败}"
    log_warn "准备恢复 unified 基础服务：reason=${reason}"
    if [ "${RABBITBOT_BASE_RUNTIME}" = "compose" ]; then
        ensure_decoupled_services
        return
    fi
    if container_running; then
        log_warn "基础服务不健康，重启统一容器：${CONTAINER_NAME}"
        docker restart "${CONTAINER_NAME}" >/dev/null
    fi
    ensure_unified_services
}

recover_runtime_services() {
    local reason="${1:-健康检查失败}"
    local recovered=0
    log_warn "开始运行时恢复：reason=${reason}"
    if ! base_services_health_ok; then
        restart_unified_services "${reason}"
        recovered=1
    fi
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" = "1" ]; then
        log_info "无机器人模式跳过导航桥接恢复：reason=${reason}"
    elif ! nav_bridge_health_ok; then
        restart_nav_bridge "${reason}"
        recovered=1
    fi
    if runtime_health_ok "恢复后复查"; then
        log_info "运行时恢复完成：reason=${reason}, recovered=${recovered}"
        last_runtime_health_check_ms="$(now_ms)"
        return 0
    fi
    log_error "运行时恢复后健康检查仍失败：reason=${reason}"
    return 1
}

ensure_decoupled_services() {
    # 解耦模式：用 docker-compose 拉起基础服务与 workflow 宿主，替代创建 unified 单容器。
    require_path "${RABBITBOT_DECOUPLED_COMPOSE_FILE}"
    ensure_enabled_models
    log_info "确保解耦基础服务就绪（compose）：file=${RABBITBOT_DECOUPLED_COMPOSE_FILE}, workflow_container=${CONTAINER_NAME}"
    # 解耦栈与旧 unified 单容器互斥：若旧容器仍在运行，先停止以释放端口。
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "rabbitbot-unified-runtime"; then
        log_warn "解耦模式：停止仍在运行的旧 unified 容器以释放端口：rabbitbot-unified-runtime"
        docker stop rabbitbot-unified-runtime >/dev/null 2>&1 || true
    fi
    # 仅拉起基础服务与 workflow 宿主；nav 在无机器人模式下被 main 跳过，这里不动 navbridge。
    local compose_dir
    compose_dir="$(dirname "${RABBITBOT_DECOUPLED_COMPOSE_FILE}")"
    local compose_services=(neo4j rabbitbot-vlm rabbitbot-audio rabbitbot-memory rabbitbot-workflow)
    local compose_up_args=(up -d)
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
        compose_services=(rabbitbot-audio rabbitbot-workflow)
        compose_up_args=(up -d --force-recreate)
        log_info "兰石原地导览模式：停止 VLM/Embedding/STT/Memory 相关容器，仅拉起 audio(TTS-only) 与 workflow 宿主。"
        ( cd "${compose_dir}" && docker compose -f "${RABBITBOT_DECOUPLED_COMPOSE_FILE}" stop neo4j rabbitbot-vlm rabbitbot-memory >/dev/null 2>&1 || true )
    fi
    ( cd "${compose_dir}" && RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT}" docker compose -f "${RABBITBOT_DECOUPLED_COMPOSE_FILE}" "${compose_up_args[@]}" "${compose_services[@]}" )
    log_info "解耦基础服务已就绪：services=${compose_services[*]}, workflow_host=${CONTAINER_NAME}, stt=${RABBITBOT_UNIFIED_START_STT}"
}

ensure_enabled_models() {
    if [ "${RABBITBOT_AUTO_DOWNLOAD_MODELS:-1}" != "1" ]; then
        log_warn "已禁用按需模型自动下载：RABBITBOT_AUTO_DOWNLOAD_MODELS=${RABBITBOT_AUTO_DOWNLOAD_MODELS:-0}"
        return 0
    fi
    if [ ! -x "${MODEL_ENSURE_SCRIPT}" ]; then
        log_error "模型下载脚本不存在或不可执行：${MODEL_ENSURE_SCRIPT}"
        return 1
    fi

    local targets=()
    if [ "${RABBITBOT_UNIFIED_START_VLM}" = "1" ]; then
        targets+=(qwen_vlm)
    fi
    if [ "${RABBITBOT_UNIFIED_START_EMBEDDING}" = "1" ]; then
        targets+=(qwen_embedding)
    fi
    if [ "${RABBITBOT_UNIFIED_START_STT}" = "1" ]; then
        targets+=(sensevoice)
    fi
    if [ "${#targets[@]}" -eq 0 ]; then
        log_info "模型能力均未启用，跳过按需模型下载检查"
        return 0
    fi

    mkdir -p "${MODELS_DIR}"
    local start_ts elapsed
    start_ts="$(date +%s)"
    log_info "开始按需模型检查/下载：targets=${targets[*]}, models_dir=${MODELS_DIR}, script=${MODEL_ENSURE_SCRIPT}"
    RABBITBOT_MODELS_CACHE_DIR="${MODELS_DIR}" bash "${MODEL_ENSURE_SCRIPT}" "${targets[@]}"
    elapsed=$(( $(date +%s) - start_ts ))
    log_info "按需模型检查/下载完成：targets=${#targets[@]}, models_dir=${MODELS_DIR}, elapsed=${elapsed}s"
}

ensure_unified_services() {
    if [ "${RABBITBOT_BASE_RUNTIME}" = "compose" ]; then
        ensure_decoupled_services
        return
    fi
    log_info "确认 unified 基础服务就绪；本步骤不会启动 workflow：vlm=${RABBITBOT_UNIFIED_START_VLM}, embedding=${RABBITBOT_UNIFIED_START_EMBEDDING}, stt=${RABBITBOT_UNIFIED_START_STT}"
    (
        cd "${PROJECT_DIR}"
        RUN_WORKFLOW_AFTER_START=0 \
        RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        RABBITBOT_UNIFIED_ATTACH_STDIN="${RABBITBOT_UNIFIED_ATTACH_STDIN}" \
        RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM}" \
        RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING}" \
        RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT}" \
        RABBITBOT_UNIFIED_START_ROBOT_AGENT="${RABBITBOT_UNIFIED_START_ROBOT_AGENT:-}" \
        WAIT_DEFAULT_SECONDS="${WAIT_DEFAULT_SECONDS}" \
        WAIT_VLM_SECONDS="${WAIT_VLM_SECONDS}" \
        bash scripts_1/start_unified_integration_workflow.sh
    )
}

read_pending_command() {
    if [ ! -s "${COMMAND_FILE}" ]; then
        return 1
    fi
    local command
    command="$(head -n 1 "${COMMAND_FILE}" | tr -d $'\r' | xargs || true)"
    rm -f "${COMMAND_FILE}"
    if [ -z "${command}" ]; then
        return 1
    fi
    printf '%s\n' "${command}"
}

handle_unexpected_command() {
    local command="$1"
    local expected="$2"
    case "${command}" in
        quit|exit)
            log_info "收到退出命令：${command}"
            exit 0
            ;;
        "")
            ;;
        *)
            log_warn "当前阶段需要 ${expected}，忽略命令：${command}"
            ;;
    esac
}

wait_command() {
    local expected="$1"
    local label="$2"
    log_info "等待命令：${label}"
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        if [ -n "${command}" ]; then
            if [ "${command}" = "${expected}" ]; then
                log_info "收到命令：${command}"
                return 0
            fi
            handle_unexpected_command "${command}" "${expected}"
        fi
        if ! check_runtime_health_periodic "等待命令:${label}"; then
            log_warn "等待命令阶段运行时健康检查失败，尝试恢复服务：label=${label}"
            recover_runtime_services "等待命令阶段健康检查失败：${label}" || sleep "${RETURN_FAILURE_WAIT_SECONDS}"
        fi
        sleep "${COMMAND_POLL_SECONDS}"
    done
}
kill_stale_workflow() {
    # 清理容器内任何残留的 workflow 进程（按进程特征 pkill，不依赖本轮 loop 的 pid 记录）。
    # 用于：上一轮 loop 以 docker exec -d 启动、systemctl stop loop 未能杀掉的 detached workflow。
    if ! workflow_running; then
        return 0
    fi
    log_warn "清理残留 workflow 进程：container=${CONTAINER_NAME}"
    docker exec "${CONTAINER_NAME}" bash -lc '
        for pat in "[e]xamples/run_kuavo_agno.py" "[s]cripts/run_kuavo_agno_workflow.py" "[s]cripts/start_kuavo_agno_workflow.bash" "[s]cripts_1/start_lanshi_product_guide.py"; do
            pkill -TERM -f "$pat" 2>/dev/null || true
        done
        sleep 2
        for pat in "[e]xamples/run_kuavo_agno.py" "[s]cripts/run_kuavo_agno_workflow.py" "[s]cripts/start_kuavo_agno_workflow.bash" "[s]cripts_1/start_lanshi_product_guide.py"; do
            pkill -KILL -f "$pat" 2>/dev/null || true
        done
    ' >/dev/null 2>&1 || true
    local waited=0
    while workflow_running && [ "${waited}" -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if workflow_running; then
        log_error "残留 workflow 进程清理失败，仍在运行：container=${CONTAINER_NAME}"
        return 1
    fi
    log_info "残留 workflow 进程已清理：container=${CONTAINER_NAME}"
    return 0
}

launch_workflow_detached() {
    if workflow_running; then
        # 可能是上一轮 loop 以 docker exec -d 启动、systemctl stop 杀不掉的残留 workflow；
        # 先按进程特征清理再启动，避免反复“拒绝重复启动”死循环。
        log_warn "检测到已有 workflow 进程，先清理残留再预启动。"
        if ! kill_stale_workflow; then
            log_error "残留 workflow 进程清理失败，拒绝重复启动。"
            return 1
        fi
    fi

    current_run_id="$(date +%Y%m%d_%H%M%S)"
    current_control_dir="${CONTAINER_WORKFLOW_CONTROL_DIR}"
    current_host_control_dir="${HOST_WORKFLOW_CONTROL_DIR}"
    current_workflow_log="${CONTAINER_WORKFLOW_RUN_DIR}/rabbitbot_workflow_${current_run_id}.log"
    current_host_workflow_log="${HOST_WORKFLOW_RUN_DIR}/rabbitbot_workflow_${current_run_id}.log"
    current_status_file="${current_host_control_dir}/${current_run_id}.status"
    current_exit_code_file="${current_host_control_dir}/${current_run_id}.exit_code"
    current_pid_file="${current_host_control_dir}/${current_run_id}.pid"
    current_finished_at_file="${current_host_control_dir}/${current_run_id}.finished_at"
    current_gate_file="${current_control_dir}/${current_run_id}.go"
    current_gate_ready_file="${current_control_dir}/${current_run_id}.ready"
    current_host_gate_file="${current_host_control_dir}/${current_run_id}.go"
    current_host_gate_ready_file="${current_host_control_dir}/${current_run_id}.ready"
    current_return_request_file="${current_control_dir}/${current_run_id}.return_to_start"
    current_host_return_request_file="${current_host_control_dir}/${current_run_id}.return_to_start"
    current_manual_arrival_file="${current_control_dir}/${current_run_id}.arrive"
    current_host_manual_arrival_file="${current_host_control_dir}/${current_run_id}.arrive"

    mkdir -p "${current_host_control_dir}" "$(dirname "${current_host_workflow_log}")"
    rm -f "${current_status_file}" "${current_exit_code_file}" "${current_pid_file}" "${current_finished_at_file}" "${current_host_gate_file}" "${current_host_gate_ready_file}" "${current_host_return_request_file}" "${current_host_manual_arrival_file}"
    if ! : >"${current_host_workflow_log}"; then
        log_error "无法创建 workflow 宿主日志：${current_host_workflow_log}，请检查目录权限"
        return 1
    fi
    docker exec "${CONTAINER_NAME}" bash -lc "mkdir -p '${current_control_dir}' '$(dirname "${current_workflow_log}")' && rm -f '${current_control_dir}/${current_run_id}.status' '${current_control_dir}/${current_run_id}.exit_code' '${current_control_dir}/${current_run_id}.pid' '${current_control_dir}/${current_run_id}.finished_at' '${current_gate_file}' '${current_gate_ready_file}' '${current_return_request_file}' '${current_manual_arrival_file}'" >/dev/null

    local start_ms
    local dialogue_config
    start_ms="$(now_ms)"
    if [ -n "${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}" ]; then
        dialogue_config="文件=${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}"
    elif [ -n "${RABBITBOT_DIALOGUE_INDEX}" ]; then
        dialogue_config="序号=${RABBITBOT_DIALOGUE_INDEX}"
    elif [ -n "${RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX}" ]; then
        dialogue_config="旧变量序号=${RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX}"
    else
        dialogue_config="序号=0（默认）"
    fi
    if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
        log_info "启动兰石原地产品介绍循环：run_id=${current_run_id}"
    elif [ "${RABBITBOT_NAV_WORKFLOW_VOICE_START}" = "1" ]; then
        log_info "启动 workflow 默认 QA 状态，等待语音口令开始导览：run_id=${current_run_id}"
    else
        log_info "预启动 workflow 并等待 go 闸门：run_id=${current_run_id}"
    fi
    log_info "workflow 台词配置：${dialogue_config}"
    docker exec -d \
        -e RABBITBOT_WORKFLOW_NON_INTEGRATION="${RABBITBOT_WORKFLOW_NON_INTEGRATION}" \
        -e RABBITBOT_LANSHI_GUIDE_MODE="${RABBITBOT_LANSHI_GUIDE_MODE}" \
        -e RABBITBOT_WORKFLOW_VERBOSE="${RABBITBOT_WORKFLOW_VERBOSE}" \
        -e RABBITBOT_TTS_STRICT_FAILURE="${RABBITBOT_TTS_STRICT_FAILURE}" \
        -e RABBITBOT_GUIDE_START_BY_VOICE="${RABBITBOT_NAV_WORKFLOW_VOICE_START}" \
        -e RABBITBOT_DIALOGUE_INDEX="${RABBITBOT_DIALOGUE_INDEX}" \
        -e RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX="${RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX}" \
        -e RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE="${RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE}" \
        -e RABBITBOT_DIR="${CONTAINER_RABBITBOT_DIR}" \
        -e RABBITBOT_LOG_DIR="${CONTAINER_WORKFLOW_RUN_DIR}" \
        -e RABBITBOT_WORKFLOW_RUN_ID="${current_run_id}" \
        -e RABBITBOT_WORKFLOW_START_GATE_FILE="${current_gate_file}" \
        -e RABBITBOT_WORKFLOW_START_GATE_READY_FILE="${current_gate_ready_file}" \
        -e RABBITBOT_WORKFLOW_RETURN_REQUEST_FILE="${current_return_request_file}" \
        -e RABBITBOT_WORKFLOW_MANUAL_ARRIVAL_FILE="${current_manual_arrival_file}" \
        -e RABBITBOT_WORKFLOW_START_GATE_POLL_SECONDS="${WORKFLOW_GATE_POLL_SECONDS}" \
        -e PYTHONUNBUFFERED=1 \
        "${CONTAINER_NAME}" bash -lc '
set -euo pipefail
cd "${RABBITBOT_DIR}"
log_dir="${RABBITBOT_LOG_DIR:-${RABBITBOT_DIR}/logs/unified_runtime}"
control_dir="${log_dir}/workflow_control"
run_id="${RABBITBOT_WORKFLOW_RUN_ID}"
mkdir -p "${log_dir}" "${control_dir}"
log_path="${log_dir}/rabbitbot_workflow_${run_id}.log"
ln -sf "${log_path}" "${log_dir}/rabbitbot_workflow_latest.log"
runner="${control_dir}/workflow_runner_${run_id}.sh"
cat >"${runner}" <<RUNNER
#!/usr/bin/env bash
set +e
cd "${RABBITBOT_DIR}"
echo running >"${control_dir}/${run_id}.status"
echo "Workflow容器日志: ${log_path}" >>"${log_path}"
echo "Workflow启动闸门文件: ${RABBITBOT_WORKFLOW_START_GATE_FILE}" >>"${log_path}"
if [ "${RABBITBOT_LANSHI_GUIDE_MODE:-0}" = "1" ]; then
    PYTHONUNBUFFERED=1 py310/bin/python scripts_1/start_lanshi_product_guide.py >>"${log_path}" 2>&1
else
    PYTHONUNBUFFERED=1 bash scripts/start_kuavo_agno_workflow.bash >>"${log_path}" 2>&1
fi
status=\$?
echo "\${status}" >"${control_dir}/${run_id}.exit_code"
date "+%Y-%m-%d %H:%M:%S" >"${control_dir}/${run_id}.finished_at"
echo finished >"${control_dir}/${run_id}.status"
exit "\${status}"
RUNNER
chmod +x "${runner}"
setsid "${runner}" >/dev/null 2>&1 &
echo "$!" >"${control_dir}/${run_id}.pid"
'

    log_info "workflow 预启动命令已发送：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
    log_info "workflow 日志：${current_workflow_log}"
    tail -n +1 -F "${current_host_workflow_log}" &
    workflow_tail_pid=$!
}

wait_workflow_gate_ready() {
    local attempts=$(( WORKFLOW_GATE_READY_TIMEOUT_SECONDS * 10 ))
    local start_ms
    start_ms="$(now_ms)"
    log_info "等待 workflow 预启动完成：run_id=${current_run_id}, timeout=${WORKFLOW_GATE_READY_TIMEOUT_SECONDS}s"
    local i
    for ((i = 0; i < attempts; i++)); do
        local status=""
        status="$(cat "${current_status_file}" 2>/dev/null || true)"
        if [ "${status}" = "finished" ]; then
            local exit_code="unknown"
            exit_code="$(cat "${current_exit_code_file}" 2>/dev/null || true)"
            log_error "workflow 在等待 go 前已退出：run_id=${current_run_id}, exit_code=${exit_code:-unknown}"
            return 1
        fi
        if [ -s "${current_host_gate_ready_file}" ]; then
            if current_workflow_process_active; then
                log_info "workflow 已完成预启动并停在 go 闸门：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
                return 0
            fi
            log_warn "workflow ready 文件存在但进程不在，准备重新预启动：run_id=${current_run_id}"
            return 1
        fi
        sleep 0.1
    done
    log_error "workflow 预启动等待超时：run_id=${current_run_id}, timeout=${WORKFLOW_GATE_READY_TIMEOUT_SECONDS}s"
    return 1
}

inject_stt_text_command() {
    local command_name="$1"
    local command_text="$2"
    local payload
    local response
    payload="$(python3 -c 'import json,sys; print(json.dumps({"task":"inject_text_async","lang":"zh","text":sys.argv[1],"timeout":30}, ensure_ascii=False))' "${command_text}")"
    log_info "将 ${command_name} 命令转换为 STT 注入口令：text_len=${#command_text}, stt_url=${RABBITBOT_STT_EXEC_URL}"
    response="$(curl --max-time 5 -sS -X POST "${RABBITBOT_STT_EXEC_URL}" --form-string "task=${payload}" 2>&1 || true)"
    local response_len=${#response}
    if printf '%s' "${response}" | grep -q '"out_text"'; then
        log_info "${command_name} 口令已注入 STT：response_len=${response_len}"
        return 0
    fi
    log_warn "${command_name} 口令注入 STT 可能失败：response_len=${response_len}"
    return 1
}

inject_guide_start_command() {
    inject_stt_text_command "开始导览" "${1:-${RABBITBOT_NAV_WORKFLOW_GO_TEXT}}"
}

inject_return_to_start_command() {
    inject_stt_text_command "返回起点" "${1:-${RABBITBOT_NAV_WORKFLOW_BACK_TEXT}}"
}


signal_manual_arrival_command() {
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" != "1" ]; then
        log_warn "收到 arrive 命令但当前不是无机器人模式，已忽略"
        return 1
    fi
    if [ -z "${current_host_manual_arrival_file}" ]; then
        log_warn "收到 arrive 命令但当前 workflow 到达确认文件未初始化，已忽略"
        return 1
    fi
    date "+%Y-%m-%d %H:%M:%S" >"${current_host_manual_arrival_file}"
    log_info "无机器人模式已发送点位到达确认：run_id=${current_run_id}, file=${current_host_manual_arrival_file}"
}

wait_go_or_back() {
    WAITED_COMMAND=""
    log_info "等待命令：go 启动 workflow；此阶段收到 back 将直接返航"
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        case "${command}" in
            go|back)
                WAITED_COMMAND="${command}"
                log_info "收到命令：${command}"
                return 0
                ;;
            "")
                ;;
            *)
                handle_unexpected_command "${command}" "go 或 back"
                ;;
        esac
        if ! check_runtime_health_periodic "等待go/back"; then
            log_warn "等待 go/back 阶段运行时健康检查失败，准备重新恢复服务并预启动 workflow：run_id=${current_run_id}"
            return 1
        fi
        if ! current_workflow_process_active; then
            log_warn "等待 go/back 时发现预启动 workflow 已退出，准备重新预启动：run_id=${current_run_id}"
            return 1
        fi
        sleep "${COMMAND_POLL_SECONDS}"
    done
}

release_workflow_gate() {
    local start_ms
    start_ms="$(now_ms)"
    printf 'go\n' >"${current_host_gate_file}"
    log_info "已释放 workflow go 闸门：run_id=${current_run_id}, elapsed=$(elapsed_ms_since "${start_ms}")ms"
}

monitor_workflow_until_finished() {
    local lost_process_since_ms=""
    while true; do
        local command=""
        command="$(read_pending_command || true)"
        case "${command}" in
            back)
                if [ "${RABBITBOT_NAV_WORKFLOW_VOICE_START}" = "1" ]; then
                    inject_return_to_start_command "${RABBITBOT_NAV_WORKFLOW_BACK_TEXT}" || true
                else
                    queued_back_after_workflow=1
                    log_info "已预接收 back 命令，workflow 结束后自动返航"
                fi
                ;;
            go)
                if [ "${RABBITBOT_NAV_WORKFLOW_VOICE_START}" = "1" ]; then
                    inject_guide_start_command "${RABBITBOT_NAV_WORKFLOW_GO_TEXT}" || true
                else
                    log_warn "workflow 正在运行，忽略重复 go 命令"
                fi
                ;;
            arrive)
                signal_manual_arrival_command || true
                ;;
            "")
                ;;
            *)
                handle_unexpected_command "${command}" "back 或 arrive"
                ;;
        esac

        local status=""
        status="$(cat "${current_status_file}" 2>/dev/null || true)"
        if [ "${status}" = "finished" ]; then
            break
        fi
        if ! check_runtime_health_periodic "workflow运行"; then
            log_warn "workflow 运行期间运行时健康检查失败，等待 workflow 自身收敛：run_id=${current_run_id}"
        fi
        if [ "${status}" = "running" ] && ! current_workflow_process_active; then
            if [ -z "${lost_process_since_ms}" ]; then
                lost_process_since_ms="$(now_ms)"
                log_warn "workflow 进程已不在，但状态文件尚未标记完成，等待状态落盘：run_id=${current_run_id}, grace=${WORKFLOW_LOST_PROCESS_GRACE_SECONDS}s"
            elif [ $(( $(now_ms) - lost_process_since_ms )) -ge $((WORKFLOW_LOST_PROCESS_GRACE_SECONDS * 1000)) ]; then
                log_error "workflow 进程丢失且状态未落盘，标记为异常结束：run_id=${current_run_id}, grace=${WORKFLOW_LOST_PROCESS_GRACE_SECONDS}s"
                printf '127\n' >"${current_exit_code_file}"
                date "+%Y-%m-%d %H:%M:%S" >"${current_finished_at_file}"
                printf 'finished\n' >"${current_status_file}"
                break
            fi
        else
            lost_process_since_ms=""
        fi
        sleep "${WORKFLOW_STATUS_POLL_SECONDS}"
    done

    stop_workflow_tail

    local exit_code="unknown"
    exit_code="$(cat "${current_exit_code_file}" 2>/dev/null || true)"
    if [ -z "${exit_code}" ]; then
        exit_code="unknown"
    fi
    if [ -s "${current_host_return_request_file}" ]; then
        queued_back_after_workflow=1
        log_info "检测到 workflow 返航请求文件，准备按返航点序列返回起点：file=${current_host_return_request_file}"
    fi
    log_info "workflow 已结束：run_id=${current_run_id}, exit_code=${exit_code}"
}

navigate_back_segment() {
    local label="$1"
    local task="$2"
    local segment_index="$3"
    local segment_total="$4"

    local task_payload
    task_payload="$(normalize_go_to_task "${task}")"
    if [ "${task_payload}" != "${task}" ]; then
        log_warn "返航分段 ${segment_index}/${segment_total} 任务格式已兼容转换：label=${label}, original=${task}, payload=${task_payload}"
    fi
    log_info "返航分段 ${segment_index}/${segment_total} 开始：${label}，目标=${task_payload}"
    local reset_response
    reset_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' 2>&1 || true)"
    log_info "返航分段 ${segment_index}/${segment_total} 重置导航状态返回：${reset_response}"

    local response
    response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_async --form-string "task=${task_payload}" 2>&1 || true)"
    log_info "返航分段 ${segment_index}/${segment_total} 命令返回：${response}"
    local success
    success="$(printf '%s' "${response}" | json_field success || true)"
    if [ "${success}" != "True" ] && [ "${success}" != "true" ]; then
        log_error "返航分段 ${segment_index}/${segment_total} 命令未成功发送：label=${label}，请检查 28180 bridge 和导航状态。"
        return 1
    fi

    local waited=0
    local last_status=""
    while [ "${waited}" -lt "${BACK_TIMEOUT_SECONDS}" ]; do
        local status_response status sub
        status_response="$(curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_status --form-string 'task=' 2>&1 || true)"
        status="$(printf '%s' "${status_response}" | json_field status || true)"
        sub="$(printf '%s' "${status_response}" | json_field sub || true)"
        if [ "${status}:${sub}" != "${last_status}" ]; then
            log_info "返航分段 ${segment_index}/${segment_total} 状态：label=${label}, status=${status:-未知}, sub=${sub:-空}, waited=${waited}s"
            last_status="${status}:${sub}"
        fi
        case "${status}" in
            3)
                log_info "返航分段 ${segment_index}/${segment_total} 完成：${label}，耗时=${waited}s"
                curl --max-time 5 -sS -X POST http://127.0.0.1:28180/reset_go_to_status --form-string 'task=' >/dev/null 2>&1 || true
                return 0
                ;;
            2|4)
                log_error "返航分段 ${segment_index}/${segment_total} 失败或被抢占：label=${label}, status=${status}, response=${status_response}"
                return 1
                ;;
        esac
        sleep 1
        waited=$((waited + 1))
    done
    log_error "返航分段 ${segment_index}/${segment_total} 等待超时：label=${label}, timeout=${BACK_TIMEOUT_SECONDS}s"
    return 1
}

return_to_start() {
    local labels=()
    local tasks=()
    local route_source=""
    local dialogue_path
    dialogue_path="$(dialogue_path_for_nav_map)"

    local route_output=""
    if route_output="$(read_dialogue_back_route "${dialogue_path}" 2>&1)"; then
        local line
        while IFS= read -r line; do
            if [[ "${line}" == __SOURCE__* ]]; then
                route_source="${line#*$'\t'}"
                continue
            fi
            [ -z "${line}" ] && continue
            labels+=("${line%%$'\t'*}")
            tasks+=("${line#*$'\t'}")
        done <<<"${route_output}"
    else
        log_warn "读取台词文件 back 返航点位失败，使用环境变量兜底返航点：dialogue=${dialogue_path}, error=${route_output}"
        route_source="env_fallback"
        labels=("原点位5" "返回点1" "返回点2" "点位1")
        tasks=("${POINT_5_TASK}" "${BACK_POINT_1_TASK}" "${BACK_POINT_2_TASK}" "${START_POINT_TASK}")
    fi

    if [ "${#tasks[@]}" -eq 0 ]; then
        log_error "返航点位序列为空：dialogue=${dialogue_path}, source=${route_source:-未知}"
        return 1
    fi

    local segment_total="${#labels[@]}"
    local start_epoch
    start_epoch="$(date +%s)"

    local route_summary=""
    local i
    for i in "${!labels[@]}"; do
        if [ -z "${route_summary}" ]; then
            route_summary="${labels[$i]}"
        else
            route_summary="${route_summary} -> ${labels[$i]}"
        fi
    done
    log_info "收到 back 后按返航点序列导航：source=${route_source:-未知}, dialogue=${dialogue_path}, segments=${segment_total}, route=${route_summary}"
    log_info "返航最终目标：${labels[$((segment_total - 1))]}，${tasks[$((segment_total - 1))]}"

    for i in "${!labels[@]}"; do
        local segment_index=$((i + 1))
        if ! navigate_back_segment "${labels[$i]}" "${tasks[$i]}" "${segment_index}" "${segment_total}"; then
            local elapsed=$(( $(date +%s) - start_epoch ))
            log_error "返航流程中止：失败分段=${labels[$i]}，已耗时=${elapsed}s"
            return 1
        fi
    done

    local elapsed=$(( $(date +%s) - start_epoch ))
    log_info "已按返航点序列完成返航，总耗时=${elapsed}s"
}

return_to_start_with_recovery() {
    local reason="${1:-back返航}"
    local attempt=0
    while true; do
        if ! runtime_health_ok "返航前检查"; then
            recover_runtime_services "返航前健康检查失败：${reason}" || true
        fi
        if return_to_start; then
            return 0
        fi
        if [ "${attempt}" -ge "${BACK_RETRY_LIMIT}" ]; then
            log_error "返航失败已达到自动重试上限：reason=${reason}, retry_limit=${BACK_RETRY_LIMIT}"
            return 1
        fi
        attempt=$((attempt + 1))
        log_warn "返航失败，准备恢复导航桥接后自动重试：reason=${reason}, attempt=${attempt}/${BACK_RETRY_LIMIT}"
        restart_nav_bridge "返航失败自动重试：${reason}" || true
        sleep "${RETURN_FAILURE_WAIT_SECONDS}"
    done
}

complete_return_to_start_or_wait_retry() {
    local reason="${1:-back返航}"
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" = "1" ]; then
        log_info "无机器人模式跳过真实返航导航：reason=${reason}"
        return 0
    fi
    while true; do
        if return_to_start_with_recovery "${reason}"; then
            return 0
        fi
        log_warn "返航未完成，保持返航阶段；请确认现场安全后再次发送 back 重试。"
        wait_command back "back 重试返回起点"
        reason="back重试"
    done
}

main() {
    prepare_runtime
    if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT}" = "1" ]; then
        log_info "无机器人模式启动：不拉起导航桥接。"
    else
        start_nav_bridge
    fi
    ensure_unified_services
    runtime_health_ok "启动完成复查"

    log_info "导航桥接与基础服务已就绪。命令循环开始。"
    while true; do
        queued_back_after_workflow=0
        if ! check_runtime_health_periodic "循环开始"; then
            log_warn "循环开始前健康检查失败，尝试恢复后重新进入循环"
            recover_runtime_services "循环开始健康检查失败" || sleep "${RETURN_FAILURE_WAIT_SECONDS}"
            continue
        fi
        if ! launch_workflow_detached; then
            stop_workflow_tail
            stop_current_workflow
            recover_runtime_services "workflow预启动命令发送失败" || sleep "${RETURN_FAILURE_WAIT_SECONDS}"
            log_warn "workflow 预启动命令发送失败，重新进入循环"
            continue
        fi
        if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
            log_info "兰石原地导览已启动：持续循环介绍产品，不等待 go/back 命令。"
        elif [ "${RABBITBOT_NAV_WORKFLOW_VOICE_START}" = "1" ]; then
            log_info "语音启动导览模式：workflow 已进入 QA 状态，不等待外部 go 命令。"
        else
            if ! wait_workflow_gate_ready; then
                stop_workflow_tail
                stop_current_workflow
                recover_runtime_services "workflow预启动不可用" || sleep "${RETURN_FAILURE_WAIT_SECONDS}"
                log_warn "本轮 workflow 预启动不可用，重新预启动"
                continue
            fi
            if ! wait_go_or_back; then
                stop_workflow_tail
                stop_current_workflow
                recover_runtime_services "等待go/back阶段异常" || sleep "${RETURN_FAILURE_WAIT_SECONDS}"
                log_warn "等待 go/back 阶段检测到预启动 workflow 异常，重新预启动"
                continue
            fi
            if [ "${WAITED_COMMAND}" = "back" ]; then
                log_info "等待 go 阶段收到 back，停止预启动 workflow 后直接返航"
                stop_workflow_tail
                stop_current_workflow
                complete_return_to_start_or_wait_retry "等待go阶段收到back"
                log_info "返航流程结束，继续预启动下一次 workflow。"
                continue
            fi
            release_workflow_gate
        fi
        monitor_workflow_until_finished
        if [ "${queued_back_after_workflow}" = "1" ]; then
            log_info "使用 workflow 运行期间预接收的 back 命令进入返航"
            queued_back_after_workflow=0
        else
            wait_command back "back 返回起点"
        fi
        complete_return_to_start_or_wait_retry "workflow结束后back"
        log_info "返航流程结束，继续预启动下一次 workflow。"
    done
}

main "$@"
