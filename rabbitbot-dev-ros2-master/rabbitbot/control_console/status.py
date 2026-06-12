from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import logging
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


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


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


def _detect_main_loop_from_systemd(service_name: str = "rabbitbot-loop.service") -> str | None:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("systemd 主循环状态读取失败：service=%s, error=%s", service_name, exc)
        return None
    state = result.stdout.strip()
    if state == "active":
        logger.debug("主循环 systemd 状态为 active：service=%s", service_name)
        return "systemd_running"
    if state in {"inactive", "failed", "activating", "deactivating"}:
        logger.debug("主循环 systemd 状态非 active：service=%s, state=%s", service_name, state)
        return None
    if result.returncode != 0:
        logger.debug(
            "主循环 systemd 状态不可用：service=%s, code=%s, stdout=%s, stderr=%s",
            service_name,
            result.returncode,
            state,
            result.stderr.strip()[-300:],
        )
    return None


def detect_main_loop_running(service_name: str = "rabbitbot-loop.service") -> str:
    proc_root = Path("/proc")
    try:
        proc_dirs: Iterable[Path] = proc_root.iterdir()
    except OSError as exc:
        logger.debug("读取 /proc 失败，回退 systemd 主循环检测：error=%s", exc)
        return _detect_main_loop_from_systemd(service_name) or "unknown"

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
    return _detect_main_loop_from_systemd(service_name) or "not_detected"
