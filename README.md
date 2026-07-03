# 兰石导览现场快速启动

本文只说明如何在现场启动、停止和排查兰石企业原地导览流程。当前仓库应位于：

```bash
/mnt/disk1/gt/air_robot_gt_projects
```

当前分支应为 `lanshi`。该分支默认启动兰石模式：机器人站在原地循环介绍产品，逐句 TTS 播报，并穿插手臂动作；默认不启动 VLM、Embedding、STT、Memory。

## 现场启动前检查

```bash
cd /mnt/disk1/gt/air_robot_gt_projects
git branch --show-current
git log -1 --oneline
```

预期分支为：

```text
lanshi
```

如果刚更新过代码，先重启控制台服务，让前端加载最新“关闭程序”逻辑：

```bash
sudo systemctl restart rabbitbot-control-console.service
```

如果控制台还没启动：

```bash
sudo systemctl start rabbitbot-control-console.service
```

## 方式一：前端启动（推荐现场使用）

1. 在浏览器打开控制台：

```text
http://<orin的ip>:8080
```

2. 点击 **开始程序**。

这会启动兰石原地导览：

- 启动 TTS 容器 `rabbitbot-audio`
- 启动 workflow 宿主 `rabbitbot-workflow`
- 启动动作桥接 `rabbitbot-navbridge`
- 不启动 VLM、Embedding、STT、Memory
- 简介词播完后等待 5 秒，继续循环播报

3. 不要用 **开始程序（无机器人模式）** 做正式导览。

无机器人模式也会进入兰石流程，但会跳过 28180 动作桥接，只适合临时测试 TTS 循环播报，不适合现场展示动作。

4. 停止导览时点击 **关闭程序**。

在 `lanshi` 分支最新代码下，关闭程序只会重启兰石相关容器：

```text
rabbitbot-audio
rabbitbot-workflow
rabbitbot-navbridge
```

不会重启 `neo4j`、`rabbitbot-vlm`、`rabbitbot-memory`。

## 方式二：终端启动

启动兰石导览：

```bash
sudo systemctl start rabbitbot-loop.service
```

如果服务已经在运行，想重新进入最新流程：

```bash
sudo systemctl restart rabbitbot-loop.service
```

停止兰石导览：

```bash
sudo systemctl stop rabbitbot-loop.service
```

查看服务状态：

```bash
systemctl status rabbitbot-loop.service --no-pager -l
systemctl status rabbitbot-control-console.service --no-pager -l
```

## 查看日志

当前运行日志：

```bash
tail -f /mnt/disk1/gt/air_robot_gt_projects/logs/current_runtime.log
```

兰石 workflow 日志：

```bash
ls -lt /mnt/disk1/gt/air_robot_gt_projects/logs/nav_workflow_control/rabbitbot_workflow_*.log | head
tail -f /mnt/disk1/gt/air_robot_gt_projects/logs/nav_workflow_control/rabbitbot_workflow_latest.log
```

TTS 日志：

```bash
tail -f /mnt/disk1/gt/air_robot_gt_projects/logs/unified_runtime/rabbitbot_tts.log
```

导航/动作桥接日志：

```bash
ls -lt /mnt/disk1/gt/air_robot_gt_projects/logs/nav_workflow_control/nav_bridge_*.log | head
```

## 常用确认命令

查看兰石相关容器：

```bash
docker ps --format 'table {{.Names}}	{{.Status}}' | grep -E 'rabbitbot-audio|rabbitbot-workflow|rabbitbot-navbridge'
```

确认 TTS 服务：

```bash
curl -sf http://127.0.0.1:28185/docs >/dev/null && echo TTS_OK
```

确认动作桥接端口：

```bash
curl --max-time 5 -sS -X POST http://127.0.0.1:28180/go_to_status --form-string 'task='
```

## 现场注意事项

- 正式展示请使用 **开始程序** 或 `sudo systemctl start rabbitbot-loop.service`。
- 如果前端“关闭程序”仍然重启很多容器，说明控制台服务还在跑旧代码，请执行：

```bash
sudo systemctl restart rabbitbot-control-console.service
```

- 如果没有声音，优先看 `rabbitbot-audio` 是否 healthy，以及 `rabbitbot_tts.log` 中选择了哪个输出设备。
- 如果没有动作，优先看 `rabbitbot-navbridge` 是否运行，以及 28180 动作桥接日志是否有 `/do_arm_async` 请求。
- 如需调整动作序列，可在启动环境中设置 `RABBITBOT_LANSHI_ACTIONS`，逗号分隔，例如：

```bash
RABBITBOT_LANSHI_ACTIONS=face_wave,right_hand_up,high_wave
```
