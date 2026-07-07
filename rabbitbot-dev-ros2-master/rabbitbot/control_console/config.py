from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ConsoleConfig:
    project_root: Path
    host: str
    port: int
    nav_port: int
    map_path: str
    command_script: Path
    workflow_control_dir: Path
    nav_log_dir: Path
    nav_container_name: str
    runtime_container_name: str
    docker_path: Path
    workflow_log_dir: Path
    current_runtime_log: Path
    guide_state_file: Path
    loop_service_name: str
    systemctl_path: Path
    sudo_path: Path | None
    map_env_file: Path
    dialogue_dir: Path
    dialogue_index: str
    dialogue_file: Path | None

    @classmethod
    def from_env(cls) -> "ConsoleConfig":
        project_root = Path(os.environ.get("RABBITBOT_PROJECT_ROOT", str(PROJECT_ROOT)))
        sudo_path_value = os.environ.get("RABBITBOT_CONSOLE_SUDO_PATH", "/usr/bin/sudo")
        sudo_path = None if sudo_path_value.lower() in {"", "none", "0"} else Path(sudo_path_value)
        dialogue_file_value = os.environ.get("RABBITBOT_DOCX_GUIDE_DIALOGUE_FILE", "").strip()
        dialogue_file = Path(dialogue_file_value) if dialogue_file_value else None
        # 基础服务运行方式：compose 解耦栈下 workflow 跑在 rabbitbot-workflow 容器、nav 由 rabbitbot-navbridge 提供；
        # unified 单容器(旧)下沿用原容器名。据此决定“关闭程序”重启哪个运行容器、nav 日志读哪个容器。
        base_runtime = os.environ.get("RABBITBOT_BASE_RUNTIME", "compose").strip().lower()
        if base_runtime == "compose":
            default_runtime_container = os.environ.get("RABBITBOT_WORKFLOW_CONTAINER_NAME", "rabbitbot-workflow")
            default_nav_container = os.environ.get("RABBITBOT_NAV_BRIDGE_CONTAINER_NAME", "rabbitbot-navbridge")
        else:
            default_runtime_container = "rabbitbot-unified-runtime"
            default_nav_container = os.environ.get(
                "RABBITBOT_NAV_BRIDGE_CONTAINER_NAME",
                f"{os.environ.get('RABBITBOT_PORTABLE_COMPOSE_PROJECT', 'rabbitbot-portable')}-rabbitbot-nav-1",
            )
        return cls(
            project_root=project_root,
            host=os.environ.get("RABBITBOT_CONSOLE_HOST", "0.0.0.0"),
            port=int(os.environ.get("RABBITBOT_CONSOLE_PORT", "8080")),
            nav_port=int(os.environ.get("RABBITBOT_NAV_PORT", "28180")),
            map_path=os.environ.get("NAV_PCD_PATH", os.environ.get("RABBITBOT_NAV_MAP_PATH", "/home/unitree/test9.pcd")),
            command_script=project_root / "scripts_1" / "send_nav_workflow_command.sh",
            workflow_control_dir=project_root.parent / "logs" / "nav_workflow_control" / "workflow_control",
            nav_log_dir=project_root.parent / "logs" / "nav_workflow_control",
            nav_container_name=default_nav_container,
            runtime_container_name=os.environ.get("RABBITBOT_UNIFIED_CONTAINER_NAME", os.environ.get("CONTAINER_NAME", default_runtime_container)),
            docker_path=Path(os.environ.get("RABBITBOT_CONSOLE_DOCKER_PATH", "/usr/bin/docker")),
            workflow_log_dir=project_root.parent / "logs" / "nav_workflow_control",
            current_runtime_log=Path(os.environ.get("RABBITBOT_CURRENT_RUNTIME_LOG", str(project_root.parent / "logs" / "current_runtime.log"))),
            guide_state_file=Path(os.environ.get(
                "RABBITBOT_NAV_WORKFLOW_GUIDE_STATE_FILE",
                str(project_root / "runtime" / "nav_workflow_control" / "guide_state"),
            )),
            loop_service_name=os.environ.get("RABBITBOT_LOOP_SERVICE", "rabbitbot-loop.service"),
            systemctl_path=Path(os.environ.get("RABBITBOT_CONSOLE_SYSTEMCTL_PATH", "/usr/bin/systemctl")),
            sudo_path=sudo_path,
            map_env_file=Path(os.environ.get("RABBITBOT_LOOP_ENV_FILE", str(project_root / "runtime" / "rabbitbot-loop.env"))),
            dialogue_dir=project_root / "conf",
            dialogue_index=os.environ.get("RABBITBOT_DIALOGUE_INDEX", os.environ.get("RABBITBOT_DOCX_GUIDE_DIALOGUE_INDEX", "0")),
            dialogue_file=dialogue_file,
        )
