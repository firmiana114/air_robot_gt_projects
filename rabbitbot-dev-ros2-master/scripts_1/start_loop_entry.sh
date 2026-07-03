#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORTABLE_ENV_FILE="${RABBITBOT_PORTABLE_ENV_FILE:-${PROJECT_DIR}/runtime/portable.env}"
CURRENT_RUNTIME_LOG="${RABBITBOT_CURRENT_RUNTIME_LOG:-$(cd "${PROJECT_DIR}/.." && pwd)/logs/current_runtime.log}"

mkdir -p "$(dirname "${CURRENT_RUNTIME_LOG}")"
: > "${CURRENT_RUNTIME_LOG}"

if [ -f "${PORTABLE_ENV_FILE}" ]; then
    set -a
    source "${PORTABLE_ENV_FILE}"
    set +a
elif [ -f "${PORTABLE_ENV_FILE}.example" ]; then
    # 本机 portable.env 不进入 Git；不存在时回退读取随仓库迁移的模板，保证只读校验类场景可用。
    echo "[WARN] 未找到本机配置 ${PORTABLE_ENV_FILE}，回退读取模板 ${PORTABLE_ENV_FILE}.example；正式部署请先执行 deploy/bootstrap_host.sh 生成本机 portable.env。"
    set -a
    source "${PORTABLE_ENV_FILE}.example"
    set +a
fi

RUNTIME_MODE="${RABBITBOT_RUNTIME_MODE:-legacy}"
RABBITBOT_LANSHI_GUIDE_MODE="${RABBITBOT_LANSHI_GUIDE_MODE:-1}"
if [ "${RABBITBOT_LANSHI_GUIDE_MODE}" = "1" ]; then
    export RABBITBOT_LANSHI_GUIDE_MODE=1
    export RABBITBOT_RUNTIME_MODE="portable"
    export RABBITBOT_BASE_RUNTIME="compose"
    export RABBITBOT_NAV_RUNTIME="compose"
    export RABBITBOT_NAV_WORKFLOW_START_VLM="${RABBITBOT_NAV_WORKFLOW_START_VLM:-0}"
    export RABBITBOT_NAV_WORKFLOW_START_EMBEDDING="${RABBITBOT_NAV_WORKFLOW_START_EMBEDDING:-0}"
    export RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM:-0}"
    export RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING:-0}"
    export RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT:-0}"
    export RABBITBOT_ENABLE_STT="${RABBITBOT_ENABLE_STT:-0}"
    export RABBITBOT_AUTO_DOWNLOAD_MODELS="${RABBITBOT_AUTO_DOWNLOAD_MODELS:-0}"
    export RABBITBOT_NAV_WORKFLOW_VOICE_START="${RABBITBOT_NAV_WORKFLOW_VOICE_START:-0}"
    RUNTIME_MODE="${RABBITBOT_RUNTIME_MODE}"
    echo "[INFO] 兰石原地导览模式：仅启动 TTS、动作桥接和 workflow 宿主；跳过 VLM/Embedding/STT/Memory。"
fi
if [ "${RABBITBOT_NAV_WORKFLOW_NO_ROBOT:-0}" = "1" ]; then
    export RABBITBOT_WORKFLOW_NON_INTEGRATION=1
    export RABBITBOT_UNIFIED_START_ROBOT_AGENT=0
    echo "[INFO] 使用无机器人模式启动主循环：跳过真实导航桥接，导航到点由前端按钮确认"
fi

if [ "${RUNTIME_MODE}" = "portable" ]; then
    export RABBITBOT_NAV_RUNTIME="${RABBITBOT_NAV_RUNTIME:-compose}"
    export RABBITBOT_BASE_RUNTIME="${RABBITBOT_BASE_RUNTIME:-compose}"
    export NAV_INTERFACE="${NAV_INTERFACE:-${RABBITBOT_DDS_INTERFACE:-eno1}}"
    export NAV_PCD_PATH="${NAV_PCD_PATH:-${RABBITBOT_NAV_MAP_PATH:-/home/unitree/test9.pcd}}"
    export IMAGE_NAME="${IMAGE_NAME:-${RABBITBOT_PORTABLE_CORE_IMAGE:-ghcr.io/aaronai/rabbitbot-core-portable:20260611}}"
    export CONTAINER_NAME="${CONTAINER_NAME:-${RABBITBOT_PORTABLE_CORE_CONTAINER_NAME:-rabbitbot-unified-runtime}}"
    # loop 默认先进入 QA 状态；QA 依赖 VLM，记忆/检索链路依赖 Embedding，因此主循环默认启用两者。
    # 如需现场临时跳过，可显式设置 RABBITBOT_UNIFIED_START_VLM=0 / RABBITBOT_UNIFIED_START_EMBEDDING=0，
    # 或设置对应的 RABBITBOT_NAV_WORKFLOW_START_* 开关为 0。
    RABBITBOT_NAV_WORKFLOW_START_VLM="${RABBITBOT_NAV_WORKFLOW_START_VLM:-1}"
    RABBITBOT_NAV_WORKFLOW_START_EMBEDDING="${RABBITBOT_NAV_WORKFLOW_START_EMBEDDING:-1}"
    export RABBITBOT_UNIFIED_START_VLM="${RABBITBOT_UNIFIED_START_VLM:-${RABBITBOT_NAV_WORKFLOW_START_VLM}}"
    export RABBITBOT_UNIFIED_START_EMBEDDING="${RABBITBOT_UNIFIED_START_EMBEDDING:-${RABBITBOT_NAV_WORKFLOW_START_EMBEDDING}}"
    export RABBITBOT_UNIFIED_START_STT="${RABBITBOT_UNIFIED_START_STT:-${RABBITBOT_ENABLE_STT:-0}}"
    # portable 端口拓扑：core 不启动 robot_app.py；28180 由 nav bridge 提供（主循环先启动 nav bridge，再复用/启动 core，最后预启动 workflow）。
    export RABBITBOT_UNIFIED_START_ROBOT_AGENT="${RABBITBOT_UNIFIED_START_ROBOT_AGENT:-0}"
    export RABBITBOT_ROBOT_AGENT_URL="${RABBITBOT_ROBOT_AGENT_URL:-http://127.0.0.1:28180}"
    export NAV_BRIDGE_SCRIPT="${NAV_BRIDGE_SCRIPT:-${PROJECT_DIR}/scripts_1/start_nav_bridge_portable.sh}"
    echo "[INFO] 使用 portable 模式启动主循环：image=${IMAGE_NAME}, nav_script=${NAV_BRIDGE_SCRIPT}, interface=${NAV_INTERFACE}, map=${NAV_PCD_PATH}, core_robot_agent=${RABBITBOT_UNIFIED_START_ROBOT_AGENT}, vlm=${RABBITBOT_UNIFIED_START_VLM}, embedding=${RABBITBOT_UNIFIED_START_EMBEDDING}"
else
    echo "[INFO] 使用 legacy 模式启动主循环"
fi

echo "[INFO] 当前运行日志：${CURRENT_RUNTIME_LOG}" | tee -a "${CURRENT_RUNTIME_LOG}"
set +e
"${PROJECT_DIR}/scripts_1/start_nav_bridge_workflow_loop.sh" 2>&1 | tee -a "${CURRENT_RUNTIME_LOG}"
loop_exit_code=${PIPESTATUS[0]}
exit "${loop_exit_code}"
