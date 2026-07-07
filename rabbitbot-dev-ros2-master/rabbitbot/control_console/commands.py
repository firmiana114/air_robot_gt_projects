from __future__ import annotations

from pathlib import Path
import logging
import os
import subprocess
import time


logger = logging.getLogger(__name__)

ALLOWED_COMMANDS = {"go", "back", "arrive"}
TASK_LABELS = {"guide": "导览", "dialogue": "对话", "vision": "视觉导航"}
PLACEHOLDER_TASKS = {"dialogue", "vision"}
LOOP_SERVICE_NAME = "rabbitbot-loop.service"
RUNTIME_CONTAINER_NAME = "rabbitbot-unified-runtime"
MAP_ENV_KEY = "NAV_PCD_PATH"
NO_ROBOT_ENV_KEY = "RABBITBOT_NAV_WORKFLOW_NO_ROBOT"
WORKFLOW_MANUAL_ENV_KEY = "RABBITBOT_WORKFLOW_NON_INTEGRATION"
LANSHI_GUIDE_ENV_KEY = "RABBITBOT_LANSHI_GUIDE_MODE"

COMPOSE_PROJECT_CONTAINER_ENVS = [
    ("RABBITBOT_NEO4J_CONTAINER_NAME", "neo4j"),
    ("RABBITBOT_VLM_CONTAINER_NAME", "rabbitbot-vlm"),
    ("RABBITBOT_AUDIO_CONTAINER_NAME", "rabbitbot-audio"),
    ("RABBITBOT_MEMORY_CONTAINER_NAME", "rabbitbot-memory"),
    ("RABBITBOT_WORKFLOW_CONTAINER_NAME", "rabbitbot-workflow"),
    ("RABBITBOT_NAV_BRIDGE_CONTAINER_NAME", "rabbitbot-navbridge"),
]

LANSHI_PROJECT_CONTAINER_ENVS = [
    ("RABBITBOT_AUDIO_CONTAINER_NAME", "rabbitbot-audio"),
    ("RABBITBOT_WORKFLOW_CONTAINER_NAME", "rabbitbot-workflow"),
    ("RABBITBOT_NAV_BRIDGE_CONTAINER_NAME", "rabbitbot-navbridge"),
]


class CommandError(RuntimeError):
    """控制台命令无法发送时抛出的异常。"""


def validate_map_path(map_path: str) -> str:
    value = map_path.strip()
    if not value:
        raise CommandError("地图路径不能为空")
    if "\n" in value or "\r" in value or "\x00" in value:
        raise CommandError("地图路径包含非法字符")
    if not value.startswith("/"):
        raise CommandError("地图路径必须是绝对路径")
    return value


def _unquote_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
        return value.replace('\\"', '"').replace('\\\\', '\\')
    return value


def read_map_path(map_env_file: Path, default_map_path: str) -> str:
    try:
        lines = map_env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return default_map_path

    current = default_map_path
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == MAP_ENV_KEY:
            current = _unquote_env_value(value) or default_map_path
    return current


def _quote_env_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _read_env_lines(env_file: Path) -> list[str]:
    try:
        return env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _write_loop_env_values(env_file: Path, updates: dict[str, str]) -> None:
    lines = _read_env_lines(env_file)
    written: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in updates:
            output.append(f'{key}="{_quote_env_value(updates[key])}"')
            written.add(key)
        else:
            output.append(line)
    for key, value in updates.items():
        if key not in written:
            output.append(f'{key}="{_quote_env_value(value)}"')
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def write_map_path(map_env_file: Path, map_path: str) -> str:
    value = validate_map_path(map_path)
    _write_loop_env_values(map_env_file, {MAP_ENV_KEY: value})
    logger.info("已写入控制台地图环境文件：env_file=%s, map_path=%s", map_env_file, value)
    return value


def read_loop_no_robot_mode(map_env_file: Path) -> bool:
    for line in _read_env_lines(map_env_file):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != NO_ROBOT_ENV_KEY:
            continue
        return _unquote_env_value(value).strip().lower() in {"1", "true", "yes", "on"}
    return False


def write_loop_mode(map_env_file: Path, no_robot_mode: bool) -> bool:
    value = "1" if no_robot_mode else "0"
    updates = {
        NO_ROBOT_ENV_KEY: value,
        WORKFLOW_MANUAL_ENV_KEY: value,
    }
    _write_loop_env_values(map_env_file, updates)
    logger.info(
        "已写入控制台启动模式环境文件：env_file=%s, no_robot_mode=%s, workflow_manual=%s",
        map_env_file,
        no_robot_mode,
        value,
    )
    return no_robot_mode


def send_workflow_command(command: str, script: Path, extra_args: list[str] | None = None) -> dict:
    if command not in ALLOWED_COMMANDS:
        raise CommandError(f"不支持的命令：{command}")
    if not script.exists():
        raise CommandError(f"命令脚本不存在：{script}")

    args = ["bash", str(script), command]
    if extra_args:
        args.extend(extra_args)

    logger.info("准备发送 workflow 控制命令：command=%s, script=%s", command, script)
    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error("workflow 控制命令执行失败：command=%s, script=%s, returncode=%s, output=%s", command, script, result.returncode, output)
        raise CommandError(output or f"命令执行失败，退出码：{result.returncode}")

    logger.info("workflow 控制命令执行完成：command=%s, returncode=%s", command, result.returncode)
    return {"ok": True, "command": command, "message": output or f"已发送命令：{command}"}


def start_task(task: str, script: Path, extra_args: list[str] | None = None) -> dict:
    if task not in TASK_LABELS:
        raise CommandError(f"不支持的任务：{task}")

    label = TASK_LABELS[task]
    if task in PLACEHOLDER_TASKS:
        return {"ok": True, "task": task, "task_label": label, "placeholder": True, "message": f"{label}任务暂未接入"}

    result = send_workflow_command("go", script, extra_args=extra_args)
    return {
        "ok": True,
        "task": task,
        "task_label": label,
        "placeholder": False,
        "command": result["command"],
        "message": f"{label}任务已启动",
    }


def _restart_runtime_container(container_name: str, docker_path: Path) -> str:
    if not container_name.strip():
        raise CommandError("Docker 容器名不能为空")
    if not docker_path.exists():
        raise CommandError(f"docker 不存在：{docker_path}")

    args = [str(docker_path), "restart", container_name]
    logger.info("准备重启 Docker 容器：container=%s, docker=%s", container_name, docker_path)
    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error(
            "Docker 容器重启失败：container=%s, returncode=%s, output=%s",
            container_name,
            result.returncode,
            output,
        )
        raise CommandError(output or f"Docker 容器重启失败，退出码：{result.returncode}")
    logger.info("Docker 容器重启完成：container=%s", container_name)
    return output


def _dedupe_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        name = value.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _effective_base_runtime() -> str:
    base_runtime = os.environ.get("RABBITBOT_BASE_RUNTIME", "").strip().lower()
    if base_runtime:
        return base_runtime
    runtime_mode = os.environ.get("RABBITBOT_RUNTIME_MODE", "").strip().lower()
    nav_runtime = os.environ.get("RABBITBOT_NAV_RUNTIME", "").strip().lower()
    if runtime_mode == "portable" and nav_runtime == "compose":
        return "compose"
    return "compose"


def _env_flag_enabled(name: str, default: str = "0") -> bool:
    value = os.environ.get(name, default).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _effective_lanshi_guide_mode() -> bool:
    # lanshi 分支专用：控制台进程未显式设置时，也与 start_loop_entry.sh 保持默认开启。
    return _env_flag_enabled(LANSHI_GUIDE_ENV_KEY, default="1")


def resolve_project_service_containers(runtime_container_name: str = RUNTIME_CONTAINER_NAME) -> list[str]:
    if _effective_base_runtime() == "compose":
        if _effective_lanshi_guide_mode():
            containers = _dedupe_non_empty([os.environ.get(key, default) for key, default in LANSHI_PROJECT_CONTAINER_ENVS])
            logger.info("兰石导览模式关闭程序容器范围：containers=%s", containers)
            return containers
        return _dedupe_non_empty([os.environ.get(key, default) for key, default in COMPOSE_PROJECT_CONTAINER_ENVS])
    return _dedupe_non_empty([runtime_container_name])


def _list_docker_container_names(docker_path: Path) -> set[str]:
    args = [str(docker_path), "ps", "-a", "--format", "{{.Names}}"]
    logger.debug("准备枚举 Docker 容器：docker=%s", docker_path)
    result = subprocess.run(args, check=False, text=True, capture_output=True, timeout=10)
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error("枚举 Docker 容器失败：returncode=%s, output=%s", result.returncode, output)
        raise CommandError(output or f"枚举 Docker 容器失败，退出码：{result.returncode}")
    names = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    logger.debug("Docker 容器枚举完成：count=%s", len(names))
    return names


def _restart_project_service_containers(container_names: list[str], docker_path: Path, timeout: float = 180.0) -> dict:
    if not docker_path.exists():
        raise CommandError(f"docker 不存在：{docker_path}")
    requested = _dedupe_non_empty(container_names)
    if not requested:
        raise CommandError("项目服务容器列表为空")
    existing = _list_docker_container_names(docker_path)
    selected = [name for name in requested if name in existing]
    missing = [name for name in requested if name not in existing]
    logger.info(
        "准备重启项目服务相关 Docker 容器：requested=%s, selected=%s, missing=%s, docker=%s, timeout=%s",
        requested,
        selected,
        missing,
        docker_path,
        timeout,
    )
    if not selected:
        raise CommandError(f"未找到需要重启的项目服务 Docker 容器：{', '.join(requested)}")

    args = [str(docker_path), "restart", "-t", "20", *selected]
    start_time = time.perf_counter()
    try:
        result = subprocess.run(args, check=False, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start_time
        logger.error("重启项目服务相关 Docker 容器超时：selected=%s, timeout=%s, elapsed=%.2fs", selected, timeout, elapsed)
        raise CommandError(f"重启项目服务容器超时（{timeout:.0f}s）：{', '.join(selected)}") from exc
    elapsed = time.perf_counter() - start_time
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error(
            "重启项目服务相关 Docker 容器失败：selected=%s, returncode=%s, elapsed=%.2fs, output=%s",
            selected,
            result.returncode,
            elapsed,
            output,
        )
        raise CommandError(output or f"重启项目服务容器失败，退出码：{result.returncode}")
    logger.info("重启项目服务相关 Docker 容器完成：selected=%s, missing=%s, elapsed=%.2fs", selected, missing, elapsed)
    return {"containers": selected, "missing": missing, "output": output}


def restart_service_container(container_name: str, docker_path: Path = Path("/usr/bin/docker"), timeout: float = 90.0) -> str:
    # 重启单个服务所在容器（解耦栈下即重启该容器内对应服务；nvidia 在 docker 组，免 sudo）。
    if not container_name.strip():
        raise CommandError("Docker 容器名不能为空")
    if not docker_path.exists():
        raise CommandError(f"docker 不存在：{docker_path}")
    args = [str(docker_path), "restart", "-t", "20", container_name]
    logger.info("准备重启服务容器：container=%s, docker=%s, timeout=%s", container_name, docker_path, timeout)
    try:
        result = subprocess.run(args, check=False, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        logger.error("重启服务容器超时：container=%s, timeout=%s", container_name, timeout)
        raise CommandError(f"重启容器 {container_name} 超时（{timeout:.0f}s）") from exc
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error("重启服务容器失败：container=%s, returncode=%s, output=%s", container_name, result.returncode, output)
        raise CommandError(output or f"重启容器 {container_name} 失败，退出码：{result.returncode}")
    logger.info("重启服务容器完成：container=%s", container_name)
    return output


def _run_loop_service_action(
    action: str,
    service_name: str,
    systemctl_path: Path,
    sudo_path: Path | None,
    failure_label: str,
) -> str:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持操作的服务：{service_name}")
    if action not in {"start", "restart", "stop", "enable", "disable"}:
        raise CommandError(f"不支持的服务操作：{action}")
    if not systemctl_path.exists():
        raise CommandError(f"systemctl 不存在：{systemctl_path}")
    if sudo_path is not None and not sudo_path.exists():
        raise CommandError(f"sudo 不存在：{sudo_path}")

    args: list[str] = []
    if sudo_path is not None:
        args.extend([str(sudo_path), "-n"])
    args.extend([str(systemctl_path), action, service_name])

    logger.info(
        "准备执行主循环服务操作：action=%s, service=%s, systemctl=%s, use_sudo=%s",
        action,
        service_name,
        systemctl_path,
        sudo_path is not None,
    )
    result = subprocess.run(
        args,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        logger.error(
            "主循环服务操作失败：action=%s, service=%s, returncode=%s, output=%s",
            action,
            service_name,
            result.returncode,
            output,
        )
        raise CommandError(output or f"{failure_label}失败，退出码：{result.returncode}")
    logger.info("主循环服务操作完成：action=%s, service=%s", action, service_name)
    return output


def start_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    map_env_file: Path | None = None,
    no_robot_mode: bool = False,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持启动的服务：{service_name}")
    if map_env_file is not None:
        write_loop_mode(map_env_file, no_robot_mode)
    action = "restart" if no_robot_mode else "start"
    output = _run_loop_service_action(action, service_name, systemctl_path, sudo_path, "启动")
    message = "已启动无机器人模式，导览到点时请点击到达下一个点位" if no_robot_mode else "已启动导航主程序"
    return {"ok": True, "service": service_name, "no_robot_mode": no_robot_mode, "message": output or message}


def restart_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    map_path: str | None = None,
    map_env_file: Path | None = None,
    no_robot_mode: bool | None = None,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持重启的服务：{service_name}")

    active_map_path = None
    if map_path is not None:
        if map_env_file is None:
            raise CommandError("缺少地图配置文件路径")
        active_map_path = write_map_path(map_env_file, map_path)
    if no_robot_mode is not None:
        if map_env_file is None:
            raise CommandError("缺少启动模式配置文件路径")
        write_loop_mode(map_env_file, no_robot_mode)

    output = _run_loop_service_action("restart", service_name, systemctl_path, sudo_path, "重启")

    response = {"ok": True, "service": service_name, "message": output or "已重新启动导航主程序"}
    if active_map_path is not None:
        response["map_path"] = active_map_path
        response["message"] = f"已使用地图 {active_map_path} 重新启动导航主程序"
    return response


def stop_loop_service(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
    docker_path: Path = Path("/usr/bin/docker"),
    runtime_container_name: str = RUNTIME_CONTAINER_NAME,
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持关闭的服务：{service_name}")
    service_output = _run_loop_service_action("stop", service_name, systemctl_path, sudo_path, "关闭")
    container_names = resolve_project_service_containers(runtime_container_name)
    restart_result = _restart_project_service_containers(container_names, docker_path)
    restarted_containers = restart_result["containers"]
    if len(restarted_containers) == 1:
        restart_message = f"已重启项目服务容器 {restarted_containers[0]}"
    else:
        restart_message = f"已重启项目服务相关容器：{', '.join(restarted_containers)}"
    message_parts = [service_output or "已关闭导航主程序", restart_message]
    return {
        "ok": True,
        "service": service_name,
        "container": restarted_containers[0],
        "containers": restarted_containers,
        "missing_containers": restart_result["missing"],
        "container_restarted": True,
        "message": "；".join(message_parts),
        "docker_output": restart_result["output"],
    }


def loop_service_autostart_enabled(
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
) -> bool:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持查询的服务：{service_name}")
    if not systemctl_path.exists():
        raise CommandError(f"systemctl 不存在：{systemctl_path}")
    if sudo_path is not None and not sudo_path.exists():
        raise CommandError(f"sudo 不存在：{sudo_path}")

    args: list[str] = []
    if sudo_path is not None:
        args.extend([str(sudo_path), "-n"])
    args.extend([str(systemctl_path), "is-enabled", service_name])

    logger.info(
        "准备查询主循环服务开机自启动：service=%s, systemctl=%s, use_sudo=%s",
        service_name,
        systemctl_path,
        sudo_path is not None,
    )
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    output = (result.stdout or result.stderr or "").strip().lower()
    if result.returncode == 0:
        enabled = output == "enabled"
        logger.info("主循环服务开机自启动查询完成：service=%s, enabled=%s", service_name, enabled)
        return enabled
    state = output.splitlines()[-1].strip() if output else ""
    if state in {"disabled", "static", "indirect", "masked"}:
        logger.info("主循环服务开机自启动查询完成：service=%s, state=%s", service_name, output)
        return False
    logger.error(
        "主循环服务开机自启动查询失败：service=%s, returncode=%s, output=%s",
        service_name,
        result.returncode,
        output,
    )
    raise CommandError(output or f"查询开机自启动失败，退出码：{result.returncode}")


def set_loop_service_autostart(
    enabled: bool,
    service_name: str = LOOP_SERVICE_NAME,
    systemctl_path: Path = Path("/usr/bin/systemctl"),
    sudo_path: Path | None = Path("/usr/bin/sudo"),
) -> dict:
    if service_name != LOOP_SERVICE_NAME:
        raise CommandError(f"不支持设置开机自启动的服务：{service_name}")
    action = "enable" if enabled else "disable"
    failure_label = "启用开机自启动" if enabled else "关闭开机自启动"
    logger.info("准备设置主循环服务开机自启动：service=%s, enabled=%s", service_name, enabled)
    output = _run_loop_service_action(action, service_name, systemctl_path, sudo_path, failure_label)
    message = output or ("已启用开机自启动" if enabled else "已关闭开机自启动")
    logger.info("主循环服务开机自启动设置完成：service=%s, enabled=%s", service_name, enabled)
    return {"ok": True, "service": service_name, "enabled": enabled, "message": message}
