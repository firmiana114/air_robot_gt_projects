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
    "绿色低碳智慧化校园管理服务平台",
    "由兰石集团爱特互联科技有限公司联合兰州现代职业学院及兰石雅生活物业公司共同打造的以工业互联网与智慧校园为核心驱动力，基于“数字孪生”、“设备管理”、“能源管理”、“安环管理”的绿色低碳智慧化校园管理服务平台，",
    "系统融合物联网、数字孪生、云计算、数据分析及人工智能等前沿技术，推动校园管理服务实现从“被动维护”到“主动防控”的战略变革。",
    "兰州现代职业学院和兰州兰石集团校企共建智慧校园体系下最具特色平安校园、绿色校园、科技校园。",
    "核心功能模块包含：",
    "一是数字孪生：虚实映射，实时感知。",
    "通过高精度测绘与三维建模，将校园地下给水管网以直观的三维模型呈现，每一根管道的位置、走向、管径等信息都清晰可查，仿佛为校园地下世界打开了一扇“透明之窗”。",
    "部署在管网二级节点的水泵房传感器和三级节点的智能水表，可实时联动采集流量、压力、水位等数据，并同步传输至平台，使管网状态实时映射。",
    "打破传统依赖人工巡检和经验判断的模式，管理人员可远程监控管网运行状况，提前发现潜在隐患，实现从被动抢修到主动预防的转变，大幅降低管网故障发生率，减少维修成本和因停水、停电等突发情况对校园生活的影响。",
    "二是设备管理：数智统管，高效运维。",
    "设备管理系统可覆盖校园内各类物业设备管理，如供电、供水、喷淋、清扫车等关键设备。",
    "在供电设备场景中，系统能定制化实现宿舍楼宇及单一用户用电智能四时段控制，“人走断闸，人在合闸”为宿舍用电安全保驾护航。",
    "供水设备方面，能精准掌握校园各区域水泵房设备运行状态、水箱水位、管廊最低点液位，保障校园用水稳定。",
    "其中，牡丹园智慧喷淋系统内设的土壤温湿度传感器，如同敏锐的“触角”，能实时精准感知土壤状况。",
    "一旦土壤湿度低于设定阈值，系统即刻启动喷淋；",
    "若湿度达标，则自动停止，避免过度灌溉。",
    "校园清扫车车辆监控系统，可实时定位车辆、追踪行驶轨迹，监测作业进度与总工作时长，助力管理者科学调度，提升校园清洁效率。",
    "同时，系统通过公众号+PC端实现“报修、接单、维修、检修、完工”全流程，形成服务闭环。",
    "三是能源管理：绿色低碳，降本增效。",
    "以“智控-分析-预警”三位一体模式，推动绿色低碳服务迈向精细化、长效化。",
    "智能调控降本增效，通过智能用电控制和节水监控形成“水电双控”节能矩阵，提升水电利用效率；",
    "数据赋能精细管理，依托能耗数据采集与数据分析，系统自动生成用能报告，为能源管理决策提供数据支撑；",
    "预警机制闭环管控，系统支持线上充值、余额提醒及欠费停供功能有效避免资源浪费提升费用收缴效率，助力校园节能管理与财务规范化。",
    "四是安环管理：智守安全，数创未来。",
    "安环管理系统，让风险可量化，让隐患可预见。",
    "部署无人机智能巡检平台，自主规划飞行方案实现高清晰度全面巡检，配合AI算法自动识别服务人员到岗情况、人工湖面异物、路面清扫状态和烟火预警等事件。",
    "雨水收集系统，可储存雨水，用于校园绿化灌溉、道路冲洗、景观补水等非饮用水场景，直接减少自来水使用量，降低用水成本。",
    "有效减少地表径流量，降低暴雨期间校园排水系统压力，缓解内涝风险。",
    "绿色低碳智慧化校园管理服务平台让科技更懂人心，让数据更有温度。",
]

DEFAULT_ACTIONS = ["face_wave", "right_hand_up", "", "right_hand_up", "high_wave"]
DEFAULT_TARGET_ROUND_SECONDS = 315.0
DEFAULT_ESTIMATED_CHARS_PER_SECOND = 5.0
DEFAULT_ESTIMATED_SENTENCE_OVERHEAD_SECONDS = 0.8
DEFAULT_ESTIMATED_SENTENCE_MAX_SECONDS = 30.0


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


def env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "")
    if not raw_value:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name, "")
    if not raw_value:
        return default
    items = [item.strip() for item in raw_value.split(",")]
    return items or default


def visible_char_count(text: str) -> int:
    return len("".join(ch for ch in text if not ch.isspace()))


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
        self.target_round_seconds = env_float("RABBITBOT_LANSHI_TARGET_ROUND_SECONDS", DEFAULT_TARGET_ROUND_SECONDS)
        self.pacing_enabled = env_bool("RABBITBOT_LANSHI_PACING_ENABLED", True)
        self.estimated_chars_per_second = max(
            0.1,
            env_float("RABBITBOT_LANSHI_ESTIMATED_CHARS_PER_SECOND", DEFAULT_ESTIMATED_CHARS_PER_SECOND),
        )
        self.estimated_sentence_overhead = max(
            0.0,
            env_float("RABBITBOT_LANSHI_ESTIMATED_SENTENCE_OVERHEAD_SECONDS", DEFAULT_ESTIMATED_SENTENCE_OVERHEAD_SECONDS),
        )
        self.estimated_sentence_max = max(
            1.0,
            env_float("RABBITBOT_LANSHI_ESTIMATED_SENTENCE_MAX_SECONDS", DEFAULT_ESTIMATED_SENTENCE_MAX_SECONDS),
        )
        self.stop_requested = False

    def estimate_sentence_seconds(self, sentence: str) -> float:
        estimate = visible_char_count(sentence) / self.estimated_chars_per_second + self.estimated_sentence_overhead
        return max(1.0, min(self.estimated_sentence_max, estimate))

    def round_timing_plan(self) -> dict[str, Any]:
        estimates = [self.estimate_sentence_seconds(sentence) for sentence in INTRO_SENTENCES]
        gap_count = max(0, len(INTRO_SENTENCES) - 1)
        base_gap = max(0.0, self.sentence_delay)
        estimated_speech_seconds = sum(estimates)
        base_gap_seconds = base_gap * gap_count
        extra_gap_seconds = 0.0
        if self.pacing_enabled and gap_count > 0:
            extra_gap_seconds = max(0.0, self.target_round_seconds - estimated_speech_seconds - base_gap_seconds)
        planned_gap = base_gap + (extra_gap_seconds / gap_count if gap_count else 0.0)
        planned_total = estimated_speech_seconds + planned_gap * gap_count
        if self.pacing_enabled and planned_total > self.target_round_seconds + 0.001:
            log(
                "WARN",
                "兰石讲解词估算时长已超过目标时长："
                f"target={self.target_round_seconds:.1f}s, estimated={planned_total:.1f}s，无法通过句间补齐缩短播放",
            )
        return {
            "estimates": estimates,
            "estimated_speech_seconds": estimated_speech_seconds,
            "base_gap_seconds": base_gap_seconds,
            "extra_gap_seconds": extra_gap_seconds,
            "planned_gap": planned_gap,
            "planned_total": planned_total,
            "visible_chars": sum(visible_char_count(sentence) for sentence in INTRO_SENTENCES),
        }

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

    def speak_sentence(self, sentence: str, index: int, total: int) -> float:
        start_time = time.perf_counter()
        log("INFO", f"提交兰石逐句 TTS：sentence={index}/{total}, chars={visible_char_count(sentence)}")
        response = self.tts_exec(
            {"task": "text_to_speech", "lang": "zh", "text": sentence, "timeout": int(self.tts_timeout)},
        )
        log("INFO", f"兰石 TTS 已提交：sentence={index}/{total}, response={response.strip()[:120]}")
        wait_response = self.tts_exec(
            {"task": "wait_speech", "lang": "", "text": "", "timeout": int(self.tts_timeout)},
        )
        elapsed = time.perf_counter() - start_time
        log("INFO", f"兰石 TTS 播放完成：sentence={index}/{total}, elapsed={elapsed:.2f}s, response={wait_response.strip()[:120]}")
        return elapsed

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
        timing_plan = self.round_timing_plan()
        round_start = time.perf_counter()
        log(
            "INFO",
            "开始兰石产品介绍轮次："
            f"round={round_index}, sentence_count={total}, visible_chars={timing_plan['visible_chars']}, "
            f"target={self.target_round_seconds:.1f}s, estimated_speech={timing_plan['estimated_speech_seconds']:.1f}s, "
            f"base_gap={timing_plan['base_gap_seconds']:.1f}s, extra_gap={timing_plan['extra_gap_seconds']:.1f}s, "
            f"planned_gap={timing_plan['planned_gap']:.2f}s, planned_total={timing_plan['planned_total']:.1f}s, "
            f"pacing={self.pacing_enabled}",
        )
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
            if index < total and not self.stop_requested:
                if self.pacing_enabled:
                    planned_elapsed_after_gap = sum(timing_plan["estimates"][:index]) + timing_plan["planned_gap"] * index
                    actual_elapsed = time.perf_counter() - round_start
                    wait_seconds = max(0.0, planned_elapsed_after_gap - actual_elapsed)
                    if wait_seconds > 0:
                        log(
                            "DEBUG",
                            "兰石讲解词句间节奏补齐："
                            f"round={round_index}, sentence={index}/{total}, wait={wait_seconds:.2f}s, "
                            f"planned_elapsed={planned_elapsed_after_gap:.2f}s, actual_elapsed={actual_elapsed:.2f}s",
                        )
                        time.sleep(wait_seconds)
                elif self.sentence_delay > 0:
                    time.sleep(self.sentence_delay)
        elapsed_total = time.perf_counter() - round_start
        log(
            "INFO",
            "兰石产品介绍轮次结束："
            f"round={round_index}, elapsed={elapsed_total:.2f}s, target={self.target_round_seconds:.1f}s, "
            f"drift={elapsed_total - self.target_round_seconds:.2f}s",
        )

    def run_forever(self) -> int:
        log(
            "INFO",
            "兰石原地导览启动："
            f"tts_url={self.tts_exec_url}, arm_url={self.robot_arm_url}, "
            f"repeat_delay={self.repeat_delay}s, target_round={self.target_round_seconds}s, "
            f"pacing={self.pacing_enabled}, actions={self.actions}",
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
