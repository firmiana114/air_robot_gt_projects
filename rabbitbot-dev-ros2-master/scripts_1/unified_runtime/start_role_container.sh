#!/usr/bin/env bash
# 解耦容器角色入口。
#
# 设计说明：
#   本脚本复用 start_unified_container.sh 中已有的 helper 与 start_* 服务启动函数，
#   按环境变量 RABBITBOT_CONTAINER_ROLE 只启动本容器负责的服务子集，从而把原本挤在
#   单个 rabbitbot-unified-runtime 容器内的服务拆到多个解耦容器里运行。
#
#   - vlm   ：启动 VLM(8000) + Embedding(8005)
#   - audio ：启动 TTS(28185) + STT(28184)
#   - memory：等待外部 Neo4j(7687) 与 Embedding(8005) 就绪后，启动 Memory Agent(28182)
#
#   Neo4j 单独使用官方 neo4j 镜像容器，不在本脚本范围内；nav bridge 使用其专用镜像容器。
#
# 复用方式：source start_unified_container.sh（其 main 已加“被 source 时不自动执行”守卫），
# 因此只会拿到函数定义与全局变量（PROJECT_DIR/MODELS_DIR/LOG_DIR/各 start_* 等），不会自动启动全部服务。

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 引入统一容器入口的全部函数与全局变量（不触发其 main）。
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/start_unified_container.sh"

ROLE="${RABBITBOT_CONTAINER_ROLE:-}"

log_info "解耦容器角色入口启动：role=${ROLE}, project=${PROJECT_DIR}, models=${MODELS_DIR}, log_dir=${LOG_DIR}"
require_path "${PROJECT_DIR}"
require_path "${MODELS_DIR}"

case "${ROLE}" in
    vlm)
        # 本容器负责 VLM 与 Embedding，强制开启两者。
        export RABBITBOT_UNIFIED_START_VLM=1
        export RABBITBOT_UNIFIED_START_EMBEDDING=1
        RABBITBOT_UNIFIED_START_VLM=1
        RABBITBOT_UNIFIED_START_EMBEDDING=1
        log_info "角色 vlm：启动 VLM(8000) 与 Embedding(8005)"
        start_vlm_and_embedding
        ;;
    audio)
        # 本容器负责音频服务；兰石原地导览只需要 TTS，可通过 RABBITBOT_UNIFIED_START_STT=0 跳过 STT。
        log_info "角色 audio：启动 TTS(28185)，STT=${RABBITBOT_UNIFIED_START_STT:-0}"
        start_tts
        start_stt
        ;;
    memory)
        # Memory Agent 依赖外部 Neo4j 与 Embedding（由其它容器提供），先等待依赖就绪再启动，避免静默失败。
        log_info "角色 memory：等待外部依赖 Neo4j(7687) 与 Embedding(8005) 就绪"
        wait_until "外部 Neo4j Bolt (7687)" "${WAIT_DEFAULT_SECONDS}" port_open 7687
        wait_until "外部 Embedding 服务 (8005)" "${WAIT_VLM_SECONDS}" json_model_ok http://127.0.0.1:8005/v1/models
        log_info "角色 memory：依赖就绪，启动 Memory Agent(28182)"
        start_memory_agent
        ;;
    *)
        log_error "未知角色 RABBITBOT_CONTAINER_ROLE='${ROLE}'。可选值：vlm | audio | memory"
        exit 1
        ;;
esac

log_success "角色 ${ROLE} 的服务已全部就绪，容器进入保活状态（各服务以后台进程运行）"

# 保活：各服务均以后台进程方式启动，主进程在此阻塞以维持容器存活。
exec tail -f /dev/null
