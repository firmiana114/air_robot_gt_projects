#!/usr/bin/env python3
"""兰石企业原地产品介绍循环。

该脚本只依赖 TTS(28185) 和机器人动作桥接(28180)，不初始化 VLM、Embedding、STT、Memory。
播报时按句提交 TTS 并等待上一句播完，保持与原导览一致的逐句流式体验。
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any


INTRO_SENTENCES = [
    "本平台由兰石爱特互联科技联合学院、兰石雅生活智慧服务打造，融合物联网、数字孪生、云计算、AI 等技术。",
    "平台构建孪生校园、能源管理、设备管理、安环管理四大核心模块，推动校园管理从被动维护转向主动防控。",
    "平台实现地下管网三维可视化、宿舍水电智能管控、能耗实时监测分析、无人机智能巡检、智慧绿化灌溉等功能。",
    "它助力节能降耗、安全防控与高效运维，同时赋能教学实践，促进跨学科融合。",
    "平台还助力学院获评节水型高校、绿色学校，打造低碳、智能、高效的现代化校园。",
]

DEFAULT_ACTIONS = ["face_wave", "right_hand_up", "", "right_hand_up", "high_wave"]


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(level: str, message: str) -> None:
    print(f"[{timestamp()}] [{level}] {message}", flush=True)


def env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name, "")
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        log("WARN", f"{name}={raw_value!r} 不是合法数字，使用默认值 {default}")
        return default


def env_list(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name, "")
    if not raw_value:
        return default
    items = [item.strip() for item in raw_value.split(",")]
    return items or default


class LanshiGuide:
    def __init__(self) -> None:
        self.tts_exec_url = os.getenv("RABBITBOT_LANSHI_TTS_EXEC_URL", "http://127.0.0.1:28185/exec")
        robot_base_url = os.getenv("RABBITBOT_ROBOT_AGENT_URL", "http://127.0.0.1:28180").rstrip("/")
        self.robot_arm_url = os.getenv("RABBITBOT_LANSHI_ARM_URL", f"{robot_base_url}/do_arm_async")
        self.repeat_delay = env_float("RABBITBOT_LANSHI_REPEAT_DELAY_SECONDS", 5.0)
        self.sentence_delay = env_float("RABBITBOT_LANSHI_SENTENCE_DELAY_SECONDS", 0.2)
        self.tts_timeout = env_float("RABBITBOT_LANSHI_TTS_TIMEOUT_SECONDS", 60.0)
        self.arm_timeout = env_float("RABBITBOT_LANSHI_ARM_TIMEOUT_SECONDS", 12.0)
        self.actions = env_list("RABBITBOT_LANSHI_ACTIONS", DEFAULT_ACTIONS)
        self.stop_requested = False

    def request_stop(self, signum: int, _frame: Any) -> None:
        self.stop_requested = True
        log("INFO", f"收到停止信号：signal={signum}，本轮句子结束后退出")
        try:
            self.tts_exec({"task": "stop", "lang": "", "text": "soft", "timeout": 10}, timeout=10)
        except Exception as exc:  # noqa: BLE001 - 退出路径只记录诊断，不抛出覆盖原信号语义
            log("WARN", f"停止 TTS 请求失败：error={exc}")

    def post_form(self, url: str, data: dict[str, str], timeout: float) -> str:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"请求 {url} 失败：{exc.reason}") from exc
        return body

    def tts_exec(self, payload: dict[str, Any], timeout: float | None = None) -> str:
        task_json = json.dumps(payload, ensure_ascii=False)
        return self.post_form(self.tts_exec_url, {"task": task_json}, timeout or self.tts_timeout)

    def speak_sentence(self, sentence: str, index: int, total: int) -> None:
        log("INFO", f"提交兰石逐句 TTS：sentence={index}/{total}, chars={len(sentence)}")
        response = self.tts_exec(
            {"task": "text_to_speech", "lang": "zh", "text": sentence, "timeout": int(self.tts_timeout)},
        )
        log("INFO", f"兰石 TTS 已提交：sentence={index}/{total}, response={response.strip()[:120]}")
        wait_response = self.tts_exec(
            {"task": "wait_speech", "lang": "", "text": "", "timeout": int(self.tts_timeout)},
        )
        log("INFO", f"兰石 TTS 播放完成：sentence={index}/{total}, response={wait_response.strip()[:120]}")

    def trigger_action(self, action_name: str, sentence_index: int) -> None:
        if not action_name:
            return
        log("INFO", f"触发兰石穿插动作：sentence={sentence_index}, action={action_name}")
        try:
            response = self.post_form(self.robot_arm_url, {"task": action_name}, timeout=self.arm_timeout)
            log("INFO", f"兰石动作返回：sentence={sentence_index}, action={action_name}, response={response.strip()[:200]}")
        except Exception as exc:  # noqa: BLE001 - 动作失败不应中断持续讲解
            log("WARN", f"兰石动作请求失败：sentence={sentence_index}, action={action_name}, error={exc}")

    def play_once(self, round_index: int) -> None:
        total = len(INTRO_SENTENCES)
        log("INFO", f"开始兰石产品介绍轮次：round={round_index}, sentence_count={total}")
        for index, sentence in enumerate(INTRO_SENTENCES, start=1):
            if self.stop_requested:
                break
            action_name = self.actions[(index - 1) % len(self.actions)] if self.actions else ""
            action_thread: threading.Thread | None = None
            if action_name:
                action_thread = threading.Thread(target=self.trigger_action, args=(action_name, index), daemon=True)
                action_thread.start()
            self.speak_sentence(sentence, index, total)
            if action_thread is not None:
                action_thread.join(timeout=max(self.arm_timeout, 1.0))
            if self.sentence_delay > 0 and index < total and not self.stop_requested:
                time.sleep(self.sentence_delay)
        log("INFO", f"兰石产品介绍轮次结束：round={round_index}")

    def run_forever(self) -> int:
        log(
            "INFO",
            "兰石原地导览启动："
            f"tts_url={self.tts_exec_url}, arm_url={self.robot_arm_url}, "
            f"repeat_delay={self.repeat_delay}s, actions={self.actions}",
        )
        round_index = 1
        while not self.stop_requested:
            self.play_once(round_index)
            round_index += 1
            if self.stop_requested:
                break
            log("INFO", f"兰石产品介绍将在 {self.repeat_delay:.1f}s 后重复")
            time.sleep(self.repeat_delay)
        log("INFO", "兰石原地导览已退出")
        return 0


def main() -> int:
    guide = LanshiGuide()
    signal.signal(signal.SIGTERM, guide.request_stop)
    signal.signal(signal.SIGINT, guide.request_stop)
    return guide.run_forever()


if __name__ == "__main__":
    sys.exit(main())
