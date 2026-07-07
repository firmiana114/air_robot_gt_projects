from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import logging
import os
import re
import socket
import subprocess
import time
from typing import Iterable


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
FLOAT = r"([-+]?\d+(?:\.\d+)?)"
POSE_RE = re.compile(
    rf"\[Pose\].*?x:\s*{FLOAT}\s+y:\s*{FLOAT}\s+z:\s*{FLOAT}\s+"
    rf"ox:\s*{FLOAT}\s+oy:\s*{FLOAT}\s+oz:\s*{FLOAT}\s+ow:\s*{FLOAT}"
)
POSITION_RE = re.compile(rf"x:\s*{FLOAT}\s+y:\s*{FLOAT}\s+z:\s*{FLOAT}")
ORIENTATION_RE = re.compile(rf"ox:\s*{FLOAT}\s+oy:\s*{FLOAT}\s+oz:\s*{FLOAT}\s+ow:\s*{FLOAT}")
RUN_ID_RE = re.compile(r"^(\d{8}_\d{6})\.(status|pid|ready|exit_code|finished_at)$")
LOCALIZATION_SUCCESS_MESSAGE = "定位成功"
LOCALIZATION_HELP_MESSAGE = "定位未成功：程序会持续重定位，需要遥控机器人的位姿，帮助机器人完成定位"
LOCALIZATION_UNKNOWN_MESSAGE = "当前位姿已读取，定位状态待确认"
LOCALIZATION_STATE_WINDOW_LINES = 300

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoseStatus:
    available: bool
    localized: bool = False
    status_message: str = LOCALIZATION_HELP_MESSAGE
    x: float | None = None
    y: float | None = None
    z: float | None = None
    ox: float | None = None
    oy: float | None = None
    oz: float | None = None
    ow: float | None = None
    source: str | None = None
    message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowStatus:
    run_id: str | None
    status: str
    ready: bool
    pid: str | None = None
    exit_code: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ServiceStatus:
    key: str
    label: str
    host: str
    port: int
    online: bool
    required: bool = True
    message: str | None = None
    state: str = "offline"
    container: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GuideState:
    state: str = "unknown"
    run_id: str = ""
    detail: str = ""
    time: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def read_guide_state(path: Path) -> GuideState:
    raw_text = _read_text(path)
    if not raw_text:
        return GuideState()

    values: dict[str, str] = {}
    for line in raw_text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return GuideState(
        state=values.get("state") or "unknown",
        run_id=values.get("run_id") or "",
        detail=values.get("detail") or "",
        time=values.get("time") or "",
    )


def latest_file(directory: Path, pattern: str) -> Path | None:
    try:
        matches = [path for path in directory.glob(pattern) if path.is_file()]
    except OSError:
        return None
    candidates: list[tuple[float, str, Path]] = []
    for path in matches:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path.name, path))
    if not candidates:
        return None

    now = time.time()
    non_future_candidates = [item for item in candidates if item[0] <= now + 300]
    if non_future_candidates:
        candidates = non_future_candidates
    return max(candidates, key=lambda item: (item[0], item[1]))[2]


def get_tail_lines(path: Path, limit: int = 120) -> list[str]:
    if limit < 1:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [strip_ansi(line) for line in lines[-limit:]]


def _localization_state(lines: list[str]) -> tuple[bool, str]:
    localized = False
    message = LOCALIZATION_UNKNOWN_MESSAGE
    recent_lines = lines[-LOCALIZATION_STATE_WINDOW_LINES:]
    for line in recent_lines:
        if "Waiting for localization" in line or "start relocation with map" in line:
            localized = False
            message = LOCALIZATION_HELP_MESSAGE
        if "[Auto-Relocation] Success! Current pose:" in line:
            localized = True
            message = LOCALIZATION_SUCCESS_MESSAGE
    return localized, message


def parse_latest_pose_from_lines(lines: list[str], source_label: str = "导航日志") -> PoseStatus:
    clean_lines = [strip_ansi(line) for line in lines]
    localized, status_message = _localization_state(clean_lines)
    latest: PoseStatus | None = None

    for line in clean_lines:
        match = POSE_RE.search(line)
        if match:
            values = [float(value) for value in match.groups()]
            latest = PoseStatus(
                available=True,
                localized=localized,
                status_message=status_message,
                x=values[0],
                y=values[1],
                z=values[2],
                ox=values[3],
                oy=values[4],
                oz=values[5],
                ow=values[6],
                source="pose_log",
            )

    if latest is not None:
        return latest

    for index, line in enumerate(clean_lines):
        if "[Auto-Relocation] Success! Current pose:" not in line:
            continue
        if index + 2 >= len(clean_lines):
            continue
        position = POSITION_RE.search(clean_lines[index + 1])
        orientation = ORIENTATION_RE.search(clean_lines[index + 2])
        if not position or not orientation:
            continue
        pos_values = [float(value) for value in position.groups()]
        orient_values = [float(value) for value in orientation.groups()]
        latest = PoseStatus(
            available=True,
            localized=localized,
            status_message=status_message,
            x=pos_values[0],
            y=pos_values[1],
            z=pos_values[2],
            ox=orient_values[0],
            oy=orient_values[1],
            oz=orient_values[2],
            ow=orient_values[3],
            source="relocation_success",
        )

    if latest is None:
        fallback_message = LOCALIZATION_SUCCESS_MESSAGE if localized else LOCALIZATION_HELP_MESSAGE
        if status_message == LOCALIZATION_UNKNOWN_MESSAGE:
            logger.debug("导航日志未解析到位姿，定位状态回退为未成功提示：source=%s, localized=%s, status_message=%s", source_label, localized, status_message)
        return PoseStatus(available=False, localized=localized, status_message=fallback_message, message="暂无定位位姿数据")
    return latest


def parse_latest_pose(path: Path) -> PoseStatus:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.debug("读取导航位姿日志失败：path=%s, error=%s", path, exc)
        return PoseStatus(available=False, localized=False, status_message=LOCALIZATION_HELP_MESSAGE, message="暂无定位位姿数据")
    return parse_latest_pose_from_lines(lines, source_label=str(path))


def read_nav_container_log_lines(container_name: str, limit: int = 240) -> list[str]:
    if not container_name:
        return []
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(limit), container_name],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("读取 portable nav 容器日志失败：container=%s, error=%s", container_name, exc)
        return []
    if result.returncode != 0:
        logger.debug("读取 portable nav 容器日志返回非零：container=%s, code=%s, stderr=%s", container_name, result.returncode, result.stderr[-300:])
        return []
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return [strip_ansi(line) for line in text.splitlines()]


def runtime_nav_log_lines(nav_log: Path | None, nav_container_name: str, limit: int = 240) -> tuple[list[str], str | None]:
    host_lines = get_tail_lines(nav_log, limit) if nav_log else []
    container_lines = read_nav_container_log_lines(nav_container_name, limit)
    container_text = "\n".join(container_lines[-limit:])
    if "[Ready] Navigation system ready for commands!" in container_text or "[Pose]" in container_text:
        logger.debug("导航状态使用 portable nav 容器日志：container=%s, lines=%s", nav_container_name, len(container_lines))
        return container_lines, f"容器日志:{nav_container_name}"
    if host_lines:
        logger.debug("导航状态使用宿主 wrapper 日志：path=%s, lines=%s", nav_log, len(host_lines))
        return host_lines, str(nav_log) if nav_log else None
    if container_lines:
        logger.debug("宿主 wrapper 日志为空，回退使用 portable nav 容器日志：container=%s, lines=%s", nav_container_name, len(container_lines))
        return container_lines, f"容器日志:{nav_container_name}"
    logger.debug("未读取到导航状态日志：host_log=%s, container=%s", nav_log, nav_container_name)
    return [], None


def workflow_log_for_status(workflow_log_dir: Path, workflow: WorkflowStatus) -> Path | None:
    if not workflow.run_id:
        logger.debug("当前 workflow run_id 为空，不回退历史 workflow 日志：dir=%s", workflow_log_dir)
        return None

    exact_path = workflow_log_dir / f"rabbitbot_workflow_{workflow.run_id}.log"
    if exact_path.is_file():
        logger.debug("当前 workflow 日志按 run_id 命中：run_id=%s, path=%s", workflow.run_id, exact_path)
        return exact_path

    logger.debug("当前 workflow 日志按 run_id 未命中，不回退历史 workflow 日志：run_id=%s, path=%s", workflow.run_id, exact_path)
    return None


def get_latest_workflow_status(control_dir: Path) -> WorkflowStatus:
    try:
        files = [path for path in control_dir.iterdir() if path.is_file()]
    except OSError as exc:
        logger.debug("读取 workflow 控制目录失败：control_dir=%s, error=%s", control_dir, exc)
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    candidates: list[tuple[float, str, str]] = []
    for path in files:
        match = RUN_ID_RE.match(path.name)
        if not match or match.group(2) != "status":
            continue
        run_id = match.group(1)
        status = _read_text(path) or "unknown"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((mtime, run_id, status))

    if not candidates:
        logger.debug("workflow 控制目录没有状态文件：control_dir=%s", control_dir)
        return WorkflowStatus(run_id=None, status="unknown", ready=False)

    now = time.time()
    non_future_candidates = [item for item in candidates if item[0] <= now + 300]
    if non_future_candidates:
        candidates = non_future_candidates

    _, run_id, status = max(candidates, key=lambda item: (item[0], item[1]))
    ready_file = control_dir / f"{run_id}.ready"
    exit_code = _read_text(control_dir / f"{run_id}.exit_code")
    finished_at = _read_text(control_dir / f"{run_id}.finished_at")
    raw_ready = ready_file.exists()
    ready = status == "running" and raw_ready and not exit_code and not finished_at
    display_status = "waiting_for_go" if ready else status
    if raw_ready and not ready:
        logger.debug(
            "忽略非活动 workflow ready 文件：run_id=%s, status=%s, exit_code=%s, finished_at=%s",
            run_id,
            status,
            exit_code,
            finished_at,
        )

    return WorkflowStatus(
        run_id=run_id,
        status=display_status,
        ready=ready,
        pid=_read_text(control_dir / f"{run_id}.pid"),
        exit_code=exit_code,
        finished_at=finished_at,
    )


def detect_nav_bridge_status_from_lines(lines: list[str], port_ready: bool, source: str | None = None) -> dict:
    status = {"ready": False, "port": None, "core_ready": False, "message": "导航桥接未就绪", "source": source}
    if not port_ready:
        status["message"] = "28180 端口未就绪"
        return status
    status["message"] = "28180 就绪，等待导航核心定位"
    if not lines:
        status["message"] = "28180 就绪，但未找到导航日志"
        logger.debug("28180 已监听但没有可读导航日志：source=%s", source)
        return status

    clean_lines = [strip_ansi(line) for line in lines]
    recent_text = "\n".join(clean_lines[-200:])
    if "does not match an available interface" in recent_text:
        status["message"] = "导航核心未启动：Unitree DDS 网卡不可用，请检查 eno1 链路"
        logger.debug("导航核心网卡不可用：source=%s", source)
        return status
    if "DdsException" in recent_text or "Failed to create domain" in recent_text or "Aborted" in recent_text:
        status["message"] = "导航核心异常退出，请查看导航日志"
        logger.debug("导航核心异常退出：source=%s", source)
        return status
    if "[Ready] Navigation system ready for commands!" in recent_text or "[Pose]" in recent_text:
        status["ready"] = True
        status["core_ready"] = True
        status["message"] = "导航核心已就绪"
        return status

    status["message"] = "28180 就绪，导航核心仍在重定位"
    return status


def detect_nav_bridge_status(nav_log: Path | None, port_ready: bool) -> dict:
    lines = get_tail_lines(nav_log, 240) if nav_log else []
    source = str(nav_log) if nav_log else None
    return detect_nav_bridge_status_from_lines(lines, port_ready, source)


def is_port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_systemd_journal_lines(unit: str, limit: int = 120) -> list[str]:
    safe_limit = max(1, min(limit, 400))
    try:
        result = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(safe_limit), "--no-pager", "--output", "short-iso"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("读取 systemd 日志失败：unit=%s, error_type=%s, error=%s", unit, type(exc).__name__, exc)
        return [f"无法读取 {unit} 日志：{type(exc).__name__}"]
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    lines = [strip_ansi(line) for line in text.splitlines()]
    if result.returncode != 0:
        logger.warning("读取 systemd 日志返回非零：unit=%s, returncode=%s, lines=%s", unit, result.returncode, len(lines))
    else:
        logger.debug("读取 systemd 日志完成：unit=%s, lines=%s", unit, len(lines))
    return lines[-safe_limit:]


SERVICE_STARTUP_GRACE_SECONDS = 180.0

# 重启发起后的“强制启动中”窗口(秒)：覆盖 docker stop 的优雅停止时长，
# 这期间即使旧进程端口仍开着，也强制把该容器的服务显示为“启动中”，让前端点击重启后立即得到反馈。
SERVICE_RESTART_FORCE_STARTING_SECONDS = 22.0


# 服务 -> 角色容器组：同组服务共享一个容器，重启该容器会一并重启同组所有服务。
SERVICE_CONTAINER_GROUP = {
    "neo4j": "neo4j",
    "tts": "audio",
    "stt": "audio",
    "memory": "memory",
    "vlm": "vlm",
    "embedding": "vlm",
}

# 最近一次“服务容器重启”的时间戳(容器名 -> epoch)，用于在重启宽限期内把该容器的服务显示为“启动中”。
# 控制台为单进程 FastAPI，模块级字典即可；多 worker 部署下不共享(可接受)。
_recent_container_restarts: dict[str, float] = {}

# 控制台进程自身的启动时间戳：用于在控制台刚启动/重启后的宽限期内，把尚未就绪的服务视为
# “启动中”而非“离线”。覆盖主循环(rabbitbot-loop.service)未运行、基础服务容器由 docker
# compose 的 `restart: unless-stopped` 策略自行拉起、模型仍在加载的场景——典型例子是 Orin
# 整机重启后先手动启动控制台：此时 get_main_loop_start_epoch() 探测不到主循环进程、
# _recent_container_restarts 也是空的，此前会被直接误判为“离线”。
_console_process_start_epoch = time.time()
logger.info(
    "控制台服务状态模块已加载：进程启动时间戳=%.0f, 启动宽限期=%.0fs",
    _console_process_start_epoch,
    SERVICE_STARTUP_GRACE_SECONDS,
)


def resolve_service_container(key: str) -> str | None:
    # 把服务 key 解析为其所在容器名：compose 解耦栈下各角色独立容器；unified(旧)下 rabbitbot 服务同在统一容器。
    group = SERVICE_CONTAINER_GROUP.get(key)
    if group is None:
        return None
    if group == "neo4j":
        return os.environ.get("RABBITBOT_NEO4J_CONTAINER_NAME", "neo4j")
    base_runtime = os.environ.get("RABBITBOT_BASE_RUNTIME", "compose").strip().lower()
    if base_runtime == "compose":
        compose_container = {
            "audio": os.environ.get("RABBITBOT_AUDIO_CONTAINER_NAME", "rabbitbot-audio"),
            "memory": os.environ.get("RABBITBOT_MEMORY_CONTAINER_NAME", "rabbitbot-memory"),
            "vlm": os.environ.get("RABBITBOT_VLM_CONTAINER_NAME", "rabbitbot-vlm"),
        }
        return compose_container.get(group)
    # unified(旧)：所有 rabbitbot 服务都在统一容器内，重启任一即重启全部。
    return os.environ.get("RABBITBOT_UNIFIED_CONTAINER_NAME", os.environ.get("CONTAINER_NAME", "rabbitbot-unified-runtime"))


def mark_container_restarted(container_name: str) -> None:
    # 记录容器重启时间，供 get_runtime_service_statuses 在宽限期内把该容器的服务显示为“启动中”。
    if container_name:
        _recent_container_restarts[container_name] = time.time()
        logger.info("记录服务容器重启时间(用于启动中态)：container=%s", container_name)


def _boot_epoch() -> float | None:
    # 读取 /proc/stat 的 btime(系统启动的绝对时间戳，单位秒)，用于换算进程启动时间。
    try:
        with open("/proc/stat", "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except (OSError, ValueError) as exc:
        logger.debug("读取 /proc/stat btime 失败：error_type=%s, error=%s", type(exc).__name__, exc)
    return None


def _proc_start_epoch(pid: int) -> float | None:
    # 由 /proc/<pid>/stat 第22字段(starttime, 时钟tick)换算出进程启动的绝对时间戳。
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="ignore") as handle:
            stat_line = handle.read()
    except OSError as exc:
        logger.debug("读取 /proc/%s/stat 失败：error_type=%s, error=%s", pid, type(exc).__name__, exc)
        return None
    # comm 字段可能含空格或括号，从最后一个 ')' 之后切分，索引0对应第3字段(state)，starttime 为第22字段。
    rparen = stat_line.rfind(")")
    if rparen == -1:
        return None
    fields = stat_line[rparen + 2:].split()
    if len(fields) <= 19:
        return None
    try:
        starttime_ticks = int(fields[19])
        clk_tck = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError, AttributeError) as exc:
        logger.debug("解析进程 starttime 失败：pid=%s, error_type=%s, error=%s", pid, type(exc).__name__, exc)
        return None
    boot_epoch = _boot_epoch()
    if boot_epoch is None or clk_tck <= 0:
        return None
    return boot_epoch + starttime_ticks / clk_tck


def get_main_loop_start_epoch() -> float | None:
    # 扫描 /proc 找到主循环进程并返回其启动时间戳(秒)，用于判断服务是否处于启动窗口内。
    proc_root = Path("/proc")
    try:
        proc_dirs: Iterable[Path] = proc_root.iterdir()
    except OSError:
        return None
    needles = ("start_nav_bridge_workflow_loop.sh", "start_loop_entry.sh")
    for proc_dir in proc_dirs:
        if not proc_dir.name.isdigit():
            continue
        try:
            cmdline = (proc_dir / "cmdline").read_text(encoding="utf-8", errors="ignore").replace("\x00", " ")
        except OSError:
            continue
        if any(needle in cmdline for needle in needles):
            return _proc_start_epoch(int(proc_dir.name))
    return None


def get_runtime_service_statuses() -> list[ServiceStatus]:
    service_specs = [
        ("neo4j", "Neo4j", 7687, True),
        ("tts", "TTS", 28185, True),
        ("stt", "STT", 28184, True),
        ("memory", "Memory", 28182, True),
        ("vlm", "VLM", 8000, True),
        ("embedding", "Embedding", 8005, True),
    ]
    # 主循环刚启动后的一段时间内，未就绪的服务视为“启动中”而非“离线”，便于前端用黄色提示；
    # 控制台进程自身刚启动/重启后的同一宽限期内同样生效，覆盖主循环未运行时的整机重启场景
    # （见 _console_process_start_epoch 定义处说明）。
    loop_start_epoch = get_main_loop_start_epoch()
    now = time.time()
    console_uptime = now - _console_process_start_epoch
    startup_window_active = (
        (loop_start_epoch is not None and 0 <= (now - loop_start_epoch) < SERVICE_STARTUP_GRACE_SECONDS)
        or console_uptime < SERVICE_STARTUP_GRACE_SECONDS
    )
    # 惰性清理过期的容器重启标记，避免无限增长。
    for stale in [c for c, ts in _recent_container_restarts.items() if now - ts >= SERVICE_STARTUP_GRACE_SECONDS]:
        _recent_container_restarts.pop(stale, None)
    statuses: list[ServiceStatus] = []
    for key, label, port, required in service_specs:
        container = resolve_service_container(key)
        online = is_port_open("127.0.0.1", port, timeout=0.12)
        restarted_ago = (
            now - _recent_container_restarts[container]
            if container is not None and container in _recent_container_restarts
            else None
        )
        # 强制窗口：重启刚发起、旧进程可能还没退出(端口仍开)，强制显示“启动中”，优先于“在线”，确保点击后立刻反馈。
        container_force_starting = restarted_ago is not None and restarted_ago < SERVICE_RESTART_FORCE_STARTING_SECONDS
        # 宽限窗口：重启后较长时间内端口未就绪也按“启动中”，直到真正在线或宽限结束。
        container_grace_starting = restarted_ago is not None and restarted_ago < SERVICE_STARTUP_GRACE_SECONDS
        if container_force_starting:
            state, state_text = "starting", "启动中"
        elif online:
            state, state_text = "online", "在线"
        elif startup_window_active or container_grace_starting:
            state, state_text = "starting", "启动中"
        else:
            state, state_text = "offline", "离线"
        statuses.append(
            ServiceStatus(
                key=key,
                label=label,
                host="127.0.0.1",
                port=port,
                online=online,
                required=required,
                state=state,
                container=container,
                message=f"{port} {state_text}",
            )
        )
    online_count = sum(1 for item in statuses if item.online)
    starting_count = sum(1 for item in statuses if item.state == "starting")
    logger.debug(
        "控制台服务状态探测完成：online=%s, starting=%s, total=%s, startup_window=%s, "
        "loop_start_epoch=%s, console_uptime=%.1fs",
        online_count,
        starting_count,
        len(statuses),
        startup_window_active,
        loop_start_epoch,
        console_uptime,
    )
    return statuses


def detect_main_loop_running() -> str:
    proc_root = Path("/proc")
    try:
        proc_dirs: Iterable[Path] = proc_root.iterdir()
    except OSError:
        return "unknown"

    needles = ("start_nav_bridge_workflow_loop.sh", "start_loop_entry.sh")
    for proc_dir in proc_dirs:
        if not proc_dir.name.isdigit():
            continue
        cmdline_path = proc_dir / "cmdline"
        try:
            cmdline = cmdline_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", " ")
        except OSError:
            continue
        if any(needle in cmdline for needle in needles):
            return "running"
    return "not_detected"
