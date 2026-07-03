import pytest

from rabbitbot.control_console.commands import CommandError, read_loop_no_robot_mode, read_map_path, restart_loop_service, send_workflow_command, start_loop_service, start_task, stop_loop_service, write_loop_mode, write_map_path


def test_send_workflow_command_allows_go_and_invokes_script(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("go", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "go"
    assert result["message"] == "已发送命令：go"
    assert record.read_text(encoding="utf-8").strip() == "go"


def test_send_workflow_command_allows_back(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("back", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "back"
    assert record.read_text(encoding="utf-8").strip() == "back"


def test_send_workflow_command_allows_arrive(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = send_workflow_command("arrive", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["command"] == "arrive"
    assert record.read_text(encoding="utf-8").strip() == "arrive"


@pytest.mark.parametrize("command", ["quit", "exit", "restart", "go; rm -rf /", ""])
def test_send_workflow_command_rejects_non_whitelisted_commands(tmp_path, command):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command(command, script)

    assert "不支持的命令" in str(excinfo.value)


def test_send_workflow_command_reports_script_failure(tmp_path):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\necho failure >&2\nexit 7\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        send_workflow_command("go", script)

    assert "failure" in str(excinfo.value)


def test_start_loop_service_invokes_systemctl_start(tmp_path):
    systemctl = tmp_path / "systemctl"
    record = tmp_path / "record.txt"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    result = start_loop_service(systemctl_path=systemctl, sudo_path=None)

    assert result["ok"] is True
    assert result["service"] == "rabbitbot-loop.service"
    assert result["message"] == "已启动导航主程序"
    assert record.read_text(encoding="utf-8").splitlines() == ["start", "rabbitbot-loop.service"]


def test_start_loop_service_rejects_other_services(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        start_loop_service("ssh.service", systemctl_path=systemctl, sudo_path=None)

    assert "不支持启动的服务" in str(excinfo.value)


def test_restart_loop_service_invokes_systemctl_restart(tmp_path):
    systemctl = tmp_path / "systemctl"
    record = tmp_path / "record.txt"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    result = restart_loop_service(systemctl_path=systemctl, sudo_path=None)

    assert result["ok"] is True
    assert result["service"] == "rabbitbot-loop.service"
    assert record.read_text(encoding="utf-8").splitlines() == ["restart", "rabbitbot-loop.service"]


def test_restart_loop_service_rejects_other_services(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        restart_loop_service("ssh.service", systemctl_path=systemctl, sudo_path=None)

    assert "不支持重启的服务" in str(excinfo.value)


def test_restart_loop_service_reports_failure(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\necho restart failed >&2\nexit 9\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        restart_loop_service(systemctl_path=systemctl, sudo_path=None)

    assert "restart failed" in str(excinfo.value)


def test_stop_loop_service_restarts_lanshi_containers_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("RABBITBOT_BASE_RUNTIME", raising=False)
    monkeypatch.delenv("RABBITBOT_LANSHI_GUIDE_MODE", raising=False)
    systemctl = tmp_path / "systemctl"
    docker = tmp_path / "docker"
    systemctl_record = tmp_path / "systemctl_record.txt"
    docker_record = tmp_path / "docker_record.txt"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {systemctl_record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = ps ]; then\n"
        "  printf '%s\\n' neo4j rabbitbot-vlm rabbitbot-audio rabbitbot-memory rabbitbot-workflow rabbitbot-navbridge\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\n' \"$@\" > {docker_record}\n"
        "printf '%s\\n' rabbitbot-audio rabbitbot-workflow rabbitbot-navbridge\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = stop_loop_service(systemctl_path=systemctl, sudo_path=None, docker_path=docker)

    assert result["ok"] is True
    assert result["service"] == "rabbitbot-loop.service"
    assert result["containers"] == ["rabbitbot-audio", "rabbitbot-workflow", "rabbitbot-navbridge"]
    assert result["container_restarted"] is True
    assert "已关闭导航主程序" in result["message"]
    assert "已重启项目服务相关容器" in result["message"]
    assert systemctl_record.read_text(encoding="utf-8").splitlines() == ["stop", "rabbitbot-loop.service"]
    assert docker_record.read_text(encoding="utf-8").splitlines() == ["restart", "-t", "20", "rabbitbot-audio", "rabbitbot-workflow", "rabbitbot-navbridge"]


def test_stop_loop_service_can_restart_all_compose_containers_when_lanshi_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("RABBITBOT_LANSHI_GUIDE_MODE", "0")
    systemctl = tmp_path / "systemctl"
    docker = tmp_path / "docker"
    docker_record = tmp_path / "docker_record.txt"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = ps ]; then\n"
        "  printf '%s\\n' neo4j rabbitbot-vlm rabbitbot-audio rabbitbot-memory rabbitbot-workflow rabbitbot-navbridge\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\n' \"$@\" > {docker_record}\n"
        "printf '%s\\n' rabbitbot-vlm rabbitbot-audio rabbitbot-memory rabbitbot-workflow rabbitbot-navbridge neo4j\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = stop_loop_service(systemctl_path=systemctl, sudo_path=None, docker_path=docker)

    assert result["containers"] == ["neo4j", "rabbitbot-vlm", "rabbitbot-audio", "rabbitbot-memory", "rabbitbot-workflow", "rabbitbot-navbridge"]
    assert docker_record.read_text(encoding="utf-8").splitlines() == ["restart", "-t", "20", "neo4j", "rabbitbot-vlm", "rabbitbot-audio", "rabbitbot-memory", "rabbitbot-workflow", "rabbitbot-navbridge"]


def test_stop_loop_service_can_use_explicit_unified_runtime(tmp_path, monkeypatch):
    # 旧 unified 容器路径只在显式配置时保留兼容，不再作为默认行为。
    monkeypatch.setenv("RABBITBOT_BASE_RUNTIME", "unified")
    systemctl = tmp_path / "systemctl"
    docker = tmp_path / "docker"
    systemctl_record = tmp_path / "systemctl_record.txt"
    docker_record = tmp_path / "docker_record.txt"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {systemctl_record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = ps ]; then printf '%s\\n' rabbitbot-unified-runtime; exit 0; fi\n"
        f"printf '%s\n' \"$@\" > {docker_record}\n"
        "echo rabbitbot-unified-runtime\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)

    result = stop_loop_service(systemctl_path=systemctl, sudo_path=None, docker_path=docker)

    assert result["containers"] == ["rabbitbot-unified-runtime"]
    assert "已重启项目服务容器 rabbitbot-unified-runtime" in result["message"]
    assert docker_record.read_text(encoding="utf-8").splitlines() == ["restart", "-t", "20", "rabbitbot-unified-runtime"]


def test_stop_loop_service_rejects_other_services(tmp_path):
    systemctl = tmp_path / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        stop_loop_service("ssh.service", systemctl_path=systemctl, sudo_path=None)

    assert "不支持关闭的服务" in str(excinfo.value)


def test_start_task_guide_sends_go(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"$1\" > \"$2\"\n"
        "echo \"已发送命令：$1\"\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = start_task("guide", script, extra_args=[str(record)])

    assert result["ok"] is True
    assert result["task"] == "guide"
    assert result["task_label"] == "导览"
    assert result["placeholder"] is False
    assert result["command"] == "go"
    assert result["message"] == "导览任务已启动"
    assert record.read_text(encoding="utf-8").strip() == "go"


def test_start_task_placeholders_do_not_invoke_script(tmp_path):
    script = tmp_path / "send.sh"
    record = tmp_path / "record.txt"
    script.write_text(
        f"#!/usr/bin/env bash\necho called > {record}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    dialogue = start_task("dialogue", script)
    vision = start_task("vision", script)

    assert dialogue["placeholder"] is True
    assert dialogue["message"] == "对话任务暂未接入"
    assert vision["placeholder"] is True
    assert vision["message"] == "视觉导航任务暂未接入"
    assert not record.exists()


def test_start_task_rejects_unknown_task(tmp_path):
    script = tmp_path / "send.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    with pytest.raises(CommandError) as excinfo:
        start_task("bad", script)

    assert "不支持的任务" in str(excinfo.value)


def test_write_and_read_map_path_round_trip(tmp_path):
    env_file = tmp_path / "runtime" / "rabbitbot-loop.env"

    written = write_map_path(env_file, " /home/unitree/test11.pcd ")

    assert written == "/home/unitree/test11.pcd"
    assert env_file.read_text(encoding="utf-8") == 'NAV_PCD_PATH="/home/unitree/test11.pcd"\n'
    assert read_map_path(env_file, "/home/unitree/default.pcd") == "/home/unitree/test11.pcd"


def test_write_loop_mode_preserves_map_path(tmp_path):
    env_file = tmp_path / "runtime" / "rabbitbot-loop.env"
    write_map_path(env_file, "/home/unitree/test11.pcd")

    write_loop_mode(env_file, True)

    content = env_file.read_text(encoding="utf-8")
    assert 'NAV_PCD_PATH="/home/unitree/test11.pcd"' in content
    assert 'RABBITBOT_NAV_WORKFLOW_NO_ROBOT="1"' in content
    assert 'RABBITBOT_WORKFLOW_NON_INTEGRATION="1"' in content
    assert read_loop_no_robot_mode(env_file) is True


def test_read_map_path_returns_default_when_missing(tmp_path):
    assert read_map_path(tmp_path / "missing.env", "/home/unitree/default.pcd") == "/home/unitree/default.pcd"


@pytest.mark.parametrize("map_path", ["", "test.pcd", "/home/unitree/bad\nmap.pcd"])
def test_write_map_path_rejects_invalid_values(tmp_path, map_path):
    with pytest.raises(CommandError):
        write_map_path(tmp_path / "runtime" / "rabbitbot-loop.env", map_path)


def test_start_loop_service_no_robot_writes_mode_and_restarts(tmp_path):
    systemctl = tmp_path / "systemctl"
    record = tmp_path / "record.txt"
    env_file = tmp_path / "runtime" / "rabbitbot-loop.env"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    result = start_loop_service(systemctl_path=systemctl, sudo_path=None, map_env_file=env_file, no_robot_mode=True)

    assert result["no_robot_mode"] is True
    assert read_loop_no_robot_mode(env_file) is True
    assert record.read_text(encoding="utf-8").splitlines() == ["restart", "rabbitbot-loop.service"]


def test_restart_loop_service_writes_map_before_restart(tmp_path):
    systemctl = tmp_path / "systemctl"
    record = tmp_path / "record.txt"
    env_file = tmp_path / "runtime" / "rabbitbot-loop.env"
    systemctl.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\n' \"$@\" > {record}\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)

    result = restart_loop_service(systemctl_path=systemctl, sudo_path=None, map_path="/home/unitree/test12.pcd", map_env_file=env_file)

    assert result["map_path"] == "/home/unitree/test12.pcd"
    assert "test12.pcd" in result["message"]
    assert env_file.read_text(encoding="utf-8") == 'NAV_PCD_PATH="/home/unitree/test12.pcd"\n'
    assert record.read_text(encoding="utf-8").splitlines() == ["restart", "rabbitbot-loop.service"]
