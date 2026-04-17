"""C1-1 智慧船舶比赛模拟程序。

默认模拟初赛 3 个引导门，输出每一步的船体状态、目标门预测和过门结果。
仅使用标准库，适合直接在仓库中运行：

    C:/Users/lfgbf/AppData/Local/Programs/Python/Python313/python.exe tools/race_simulation.py

可通过参数调整门数量、时间步长和随机扰动。
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import math
import random
from typing import List, Optional


@dataclass(frozen=True)
class Gate:
    gate_id: int
    x: float
    y: float
    width: float = 1.0
    height: float = 0.4
    angle_deg: float = 0.0


@dataclass
class BoatState:
    x: float = 0.0
    y: float = 0.0
    heading_deg: float = 90.0
    speed: float = 1.45


@dataclass
class GatePrediction:
    gate_id: int
    distance: float
    time_to_gate: float
    lateral_error: float
    will_pass: bool


@dataclass(frozen=True)
class GateResult:
    gate_id: int
    status: str
    time_s: float
    x: float
    y: float
    lateral_error: float


class RaceSimulator:
    def __init__(self, gates: List[Gate], dt: float = 0.2, seed: Optional[int] = 7) -> None:
        self.gates = gates
        self.dt = dt
        self.rng = random.Random(seed)
        self.reset()

    def reset(self, gates: Optional[List[Gate]] = None) -> None:
        if gates is not None:
            self.gates = gates
        self.state = BoatState()
        self.prev_state = BoatState()
        self.time_s = 0.0
        self.current_gate_index = 0
        self.pass_count = 0
        self.history: List[str] = []
        self.gate_results: List[GateResult] = []

    def set_gates(self, gates: List[Gate]) -> None:
        self.gates = gates
        self.reset(gates)

    def current_gate(self) -> Optional[Gate]:
        if self.current_gate_index >= len(self.gates):
            return None
        return self.gates[self.current_gate_index]

    def is_finished(self) -> bool:
        return self.current_gate_index >= len(self.gates)

    def run(self, duration_s: float = 60.0) -> None:
        self._log_header()
        while self.time_s <= duration_s and not self.is_finished():
            self.step(log=True)
        self._log_summary(duration_s)

    def step(self, log: bool = False) -> tuple[Optional[GatePrediction], List[str]]:
        gate = self.current_gate()
        if gate is None:
            return None, []

        prediction = self.predict_gate(gate)
        if log:
            self._log_step(gate, prediction)

        self.prev_state = BoatState(
            x=self.state.x,
            y=self.state.y,
            heading_deg=self.state.heading_deg,
            speed=self.state.speed,
        )
        self._step_toward_gate(gate)
        events = self._check_gate_crossing(gate)
        self.time_s += self.dt
        return prediction, events

    def predict_gate(self, gate: Gate) -> GatePrediction:
        dx = gate.x - self.state.x
        dy = gate.y - self.state.y
        distance = math.hypot(dx, dy)
        gate_dx, gate_dy = self._gate_direction(gate)
        normal_dx, normal_dy = -gate_dy, gate_dx
        projection_along_gate = dx * gate_dx + dy * gate_dy
        lateral_error = dx * normal_dx + dy * normal_dy
        target_heading = math.degrees(math.atan2(dy, dx))
        heading_error = self._wrap_angle(target_heading - self.state.heading_deg)

        forward_speed = max(self.state.speed * math.cos(math.radians(heading_error)), 0.2)
        time_to_gate = distance / forward_speed if forward_speed > 0 else float("inf")

        will_pass = abs(projection_along_gate) <= gate.width / 2 and -80 < heading_error < 80
        return GatePrediction(
            gate_id=gate.gate_id,
            distance=distance,
            time_to_gate=time_to_gate,
            lateral_error=abs(lateral_error),
            will_pass=will_pass,
        )

    def _step_toward_gate(self, gate: Gate) -> None:
        dx = gate.x - self.state.x
        dy = gate.y - self.state.y
        target_heading = math.degrees(math.atan2(dy, dx))
        heading_error = self._wrap_angle(target_heading - self.state.heading_deg)

        steer_gain = 0.22
        turn_rate = max(-18.0, min(18.0, heading_error * steer_gain))
        wobble = self.rng.uniform(-1.2, 1.2)
        self.state.heading_deg = self._wrap_angle(self.state.heading_deg + turn_rate * self.dt + wobble * 0.02)

        heading_rad = math.radians(self.state.heading_deg)
        speed_noise = 1.0 + self.rng.uniform(-0.03, 0.03)
        self.state.x += math.cos(heading_rad) * self.state.speed * speed_noise * self.dt
        self.state.y += math.sin(heading_rad) * self.state.speed * speed_noise * self.dt

    def _check_gate_crossing(self, gate: Gate) -> List[str]:
        events: List[str] = []
        if self.current_gate_index >= len(self.gates):
            return events

        gate = self.gates[self.current_gate_index]
        crossed_gate, crossing_error = self._crossed_gate_line(gate)
        lateral_error = crossing_error

        if crossed_gate and lateral_error <= gate.width / 2:
            event = (
                f"t={self.time_s:05.1f}s  过门成功: 第{gate.gate_id}门 位置=({self.state.x:.2f}, {self.state.y:.2f})"
            )
            self.pass_count += 1
            self.history.append(event)
            self.gate_results.append(
                GateResult(
                    gate_id=gate.gate_id,
                    status="success",
                    time_s=self.time_s,
                    x=self.state.x,
                    y=self.state.y,
                    lateral_error=lateral_error,
                )
            )
            events.append(event)
            self.current_gate_index += 1
            if self.current_gate_index < len(self.gates):
                next_event = f"         下一目标: 第{self.gates[self.current_gate_index].gate_id}门"
                self.history.append(next_event)
                events.append(next_event)
        elif self.time_s > 0.5 and self._has_passed_gate_line(gate) and lateral_error > gate.width / 2:
            event = f"t={self.time_s:05.1f}s  过门失败: 第{gate.gate_id}门 横向偏差={lateral_error:.2f}m"
            self.history.append(event)
            self.gate_results.append(
                GateResult(
                    gate_id=gate.gate_id,
                    status="failed",
                    time_s=self.time_s,
                    x=self.state.x,
                    y=self.state.y,
                    lateral_error=lateral_error,
                )
            )
            events.append(event)
            self.current_gate_index += 1

        return events

    def _crossed_gate_line(self, gate: Gate) -> tuple[bool, float]:
        prev_x, prev_y = self.prev_state.x - gate.x, self.prev_state.y - gate.y
        curr_x, curr_y = self.state.x - gate.x, self.state.y - gate.y
        gate_dx, gate_dy = self._gate_direction(gate)
        normal_dx, normal_dy = -gate_dy, gate_dx

        prev_lateral = prev_x * gate_dx + prev_y * gate_dy
        curr_lateral = curr_x * gate_dx + curr_y * gate_dy
        prev_normal = prev_x * normal_dx + prev_y * normal_dy
        curr_normal = curr_x * normal_dx + curr_y * normal_dy

        if prev_normal == curr_normal:
            return False, abs(curr_lateral)

        if prev_normal <= 0 <= curr_normal or curr_normal <= 0 <= prev_normal:
            ratio = (-prev_normal) / (curr_normal - prev_normal)
            ratio = max(0.0, min(1.0, ratio))
            crossing_lateral = prev_lateral + (curr_lateral - prev_lateral) * ratio
            return abs(crossing_lateral) <= gate.width / 2, abs(crossing_lateral)
        return False, abs(curr_lateral)

    def _cross_track_error(self, gate: Gate) -> float:
        dx = gate.x - self.state.x
        dy = gate.y - self.state.y
        target_heading = math.degrees(math.atan2(dy, dx))
        heading_error = self._wrap_angle(target_heading - self.state.heading_deg)
        distance = math.hypot(dx, dy)
        return distance * math.sin(math.radians(heading_error))

    def _has_passed_gate_line(self, gate: Gate) -> bool:
        _, crossing_error = self._crossed_gate_line(gate)
        return crossing_error > gate.width / 2

    def _log_header(self) -> None:
        print("C1-1 智慧船舶比赛模拟")
        print(f"初赛门数: {len(self.gates)}")
        print("-" * 78)
        print("时间(s)   位置(x,y)         航向(deg)  目标门  预测过门  距离(m)  预计到门(s)")
        print("-" * 78)

    def _log_step(self, gate: Gate, prediction: GatePrediction) -> None:
        print(
            f"{self.time_s:6.1f}  "
            f"({self.state.x:6.2f},{self.state.y:6.2f})  "
            f"{self.state.heading_deg:9.2f}  "
            f"{gate.gate_id:6d}  "
            f"{'是' if prediction.will_pass else '否':>6}  "
            f"{prediction.distance:7.2f}  "
            f"{prediction.time_to_gate:10.2f}"
        )

    def _log_summary(self, duration_s: float) -> None:
        print("-" * 78)
        if self.current_gate_index >= len(self.gates):
            print(f"模拟结束: 已完成全部 {len(self.gates)} 个门的通过预测。")
        else:
            current_gate = self.gates[self.current_gate_index]
            print(
                f"模拟结束: 在 {duration_s:.1f} 秒内完成 {self.pass_count}/{len(self.gates)} 个门，"
                f"当前仍在第 {current_gate.gate_id} 门附近。"
            )
        print(f"通过记录: {self.pass_count} 门")
        if self.history:
            print("记录:")
            for item in self.history:
                print(item)

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        while angle <= -180:
            angle += 360
        while angle > 180:
            angle -= 360
        return angle

    @staticmethod
    def _gate_direction(gate: Gate) -> tuple[float, float]:
        angle_rad = math.radians(gate.angle_deg)
        return math.cos(angle_rad), math.sin(angle_rad)

    def export_snapshot(self) -> dict:
        return {
            "version": 1,
            "dt": self.dt,
            "time_s": self.time_s,
            "current_gate_index": self.current_gate_index,
            "pass_count": self.pass_count,
            "gates": [asdict(gate) for gate in self.gates],
            "state": asdict(self.state),
            "prev_state": asdict(self.prev_state),
            "history": list(self.history),
            "gate_results": [asdict(result) for result in self.gate_results],
            "rng_state": repr(self.rng.getstate()),
        }

    def load_snapshot(self, snapshot: dict) -> None:
        self.dt = float(snapshot.get("dt", self.dt))
        self.gates = [Gate(**gate_data) for gate_data in snapshot.get("gates", [])]
        self.state = BoatState(**snapshot.get("state", {}))
        self.prev_state = BoatState(**snapshot.get("prev_state", snapshot.get("state", {})))
        self.time_s = float(snapshot.get("time_s", 0.0))
        self.current_gate_index = int(snapshot.get("current_gate_index", 0))
        self.pass_count = int(snapshot.get("pass_count", 0))
        self.history = list(snapshot.get("history", []))
        self.gate_results = [GateResult(**result) for result in snapshot.get("gate_results", [])]
        rng_state_text = snapshot.get("rng_state")
        if rng_state_text:
            self.rng.setstate(ast.literal_eval(rng_state_text))


def build_preliminary_gates(gate_count: int) -> List[Gate]:
    gates: List[Gate] = []
    x_offsets = [-0.18, 0.06, -0.03]
    y_gap = 7.5
    for index in range(gate_count):
        x = x_offsets[index % len(x_offsets)] * (1 + index * 0.1)
        y = (index + 1) * y_gap
        gates.append(Gate(gate_id=index + 1, x=x, y=y, width=1.0, height=0.4, angle_deg=0.0))
    return gates


def build_final_gates() -> List[Gate]:
    gates: List[Gate] = []
    x_offsets = [-0.10, 0.08, -0.06, 0.12, -0.04, 0.05, -0.08, 0.04, -0.02, 0.00]
    y_gap = 10.0
    for index in range(10):
        x = x_offsets[index]
        y = 8.0 + index * y_gap
        gates.append(Gate(gate_id=index + 1, x=x, y=y, width=1.0, height=0.4, angle_deg=0.0))
    return gates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="C1-1 比赛情况与过门预测模拟程序")
    parser.add_argument("--gates", type=int, default=3, help="初赛门数量，默认 3")
    parser.add_argument("--duration", type=float, default=60.0, help="模拟总时长（秒）")
    parser.add_argument("--dt", type=float, default=0.2, help="时间步长（秒）")
    parser.add_argument("--seed", type=int, default=7, help="随机种子")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gate_count = max(1, args.gates)
    gates = build_preliminary_gates(gate_count)
    simulator = RaceSimulator(gates=gates, dt=max(0.05, args.dt), seed=args.seed)
    simulator.run(duration_s=max(1.0, args.duration))


if __name__ == "__main__":
    main()
