"""C1-1 比赛图形化仿真界面。

功能：
- 在画布上放置/拖动光电门
- 以图形方式显示船模运动轨迹
- 实时预测当前目标门是否可通过
- 支持初赛 3 门和决赛 10 门两套预设
- 赛道长度可调，最大 150 米
- 赛道宽度可调，范围 0 - 150 米
- 支持窗口全屏与自由缩放
- 红外发射圆锥可显示或隐藏
- 船载红外感应可显示或隐藏

运行方式：
    C:/Users/lfgbf/AppData/Local/Programs/Python/Python313/python.exe tools/race_simulation_gui.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
import tkinter as tk
from dataclasses import asdict, dataclass
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

try:
    from PIL import ImageGrab
except ImportError:  # pragma: no cover - optional dependency fallback
    ImageGrab = None

from race_simulation import BoatState, Gate, RaceSimulator, build_final_gates, build_preliminary_gates


@dataclass
class CanvasObjectIds:
    boat: Optional[int] = None
    boat_heading: Optional[int] = None
    target_line: Optional[int] = None
    path: Optional[int] = None


class RaceSimulationApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("C1-1 比赛图形化仿真")
        self.root.geometry("1280x780")
        self.root.minsize(1100, 700)
        self.root.resizable(True, True)
        self.root.attributes("-fullscreen", False)

        self.canvas_width = 940
        self.canvas_height = 720
        self.track_width_m = 12
        self.track_length_m = 120
        self.pixels_per_meter_x = 1.0
        self.pixels_per_meter_y = 5.0
        self.origin_x = self.canvas_width / 2
        self.origin_y = self.canvas_height - 50
        self.gate_standard_width = 1.0
        self.gate_standard_height = 0.4
        self.logbook_root = Path(__file__).resolve().parents[1] / "logbook"
        self.logbook_root.mkdir(parents=True, exist_ok=True)

        self.gates: List[Gate] = build_preliminary_gates(3)
        self.simulator = RaceSimulator(self.gates, dt=0.1, seed=7)
        self.running = False
        self.edit_mode = True
        self.selected_gate_index: Optional[int] = None
        self.gate_dragging = False
        self.boat_trail: List[tuple[float, float]] = []
        self.canvas_ids = CanvasObjectIds()
        self.after_id: Optional[str] = None

        self.status_var = tk.StringVar(value="编辑模式：可拖动或点击放置光电门")
        self.time_var = tk.StringVar(value="时间：0.0 s")
        self.gate_var = tk.StringVar(value="当前目标：无")
        self.predict_var = tk.StringVar(value="预测：-")
        self.result_var = tk.StringVar(value="结果：等待开始")
        self.layout_var = tk.StringVar(value="布局：初赛 3 门")
        self.mode_var = tk.StringVar(value="初赛 3 门")
        self.track_length_var = tk.IntVar(value=self.track_length_m)
        self.track_length_text = tk.StringVar(value=f"赛道长度：{self.track_length_m} 米")
        self.track_width_var = tk.IntVar(value=self.track_width_m)
        self.track_width_text = tk.StringVar(value=f"赛道宽度：{self.track_width_m} 米")
        self.gate_check_text = tk.StringVar(value="引导门标准：1.0m × 0.4m，已符合")
        self.gate_angle_text = tk.StringVar(value="门角度：当前未选中")
        self.show_cone_var = tk.BooleanVar(value=True)
        self.cone_status_text = tk.StringVar(value="发射圆锥：显示，约90°，轴线垂直门框且平行水面")
        self.show_boat_sensor_var = tk.BooleanVar(value=True)
        self.boat_sensor_status_text = tk.StringVar(value="船载感应：显示，朝向当前目标门")

        self._build_ui()
        self._apply_track_length(self.track_length_m)
        self._apply_track_width(self.track_width_m)
        self._bind_events()
        self._draw_scene()
        self._update_stats()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right = ttk.Frame(main, width=320)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        self.canvas = tk.Canvas(left, width=self.canvas_width, height=self.canvas_height, bg="#f4f7fb", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(right, text="比赛控制", font=("Microsoft YaHei", 14, "bold"))
        title.pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(right, text="开始 / 暂停", command=self.toggle_run).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="单步推进", command=self.step_once).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="重置仿真", command=self.reset_simulation).pack(fill=tk.X, pady=4)
        ttk.Label(right, text="赛制预设", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(8, 4))
        self.mode_combo = ttk.Combobox(right, textvariable=self.mode_var, state="readonly", values=["初赛 3 门", "决赛 10 门"])
        self.mode_combo.pack(fill=tk.X, pady=4)
        ttk.Button(right, text="加载预设赛道", command=self.load_selected_layout).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="清空光电门", command=self.clear_gates).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="切换编辑模式", command=self.toggle_edit_mode).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="切换全屏", command=self.toggle_fullscreen).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="门左旋 5°", command=lambda: self.rotate_selected_gate(-5)).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="门右旋 5°", command=lambda: self.rotate_selected_gate(5)).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="导出日志", command=self.export_logbook_entry).pack(fill=tk.X, pady=4)
        ttk.Button(right, text="导入复现文件", command=self.import_replay_file).pack(fill=tk.X, pady=4)
        ttk.Checkbutton(right, text="显示红外发射圆锥", variable=self.show_cone_var, command=self._on_cone_toggle).pack(anchor=tk.W, pady=4)
        ttk.Checkbutton(right, text="显示船载红外感应", variable=self.show_boat_sensor_var, command=self._on_boat_sensor_toggle).pack(anchor=tk.W, pady=4)

        ttk.Separator(right).pack(fill=tk.X, pady=10)
        ttk.Label(right, text="赛道长度", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(right, textvariable=self.track_length_text).pack(anchor=tk.W, pady=2)
        track_scale = tk.Scale(
            right,
            from_=30,
            to=150,
            orient=tk.HORIZONTAL,
            resolution=1,
            showvalue=False,
            variable=self.track_length_var,
            command=self._on_track_length_change,
        )
        track_scale.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(right, text="范围：30 - 150 米", foreground="#5a6d80").pack(anchor=tk.W)

        ttk.Separator(right).pack(fill=tk.X, pady=10)
        ttk.Label(right, text="赛道宽度", font=("Microsoft YaHei", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(right, textvariable=self.track_width_text).pack(anchor=tk.W, pady=2)
        width_scale = tk.Scale(
            right,
            from_=0,
            to=150,
            orient=tk.HORIZONTAL,
            resolution=1,
            showvalue=False,
            variable=self.track_width_var,
            command=self._on_track_width_change,
        )
        width_scale.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(right, text="范围：0 - 150 米，0 表示自动适配", foreground="#5a6d80").pack(anchor=tk.W)

        ttk.Separator(right).pack(fill=tk.X, pady=10)

        ttk.Label(right, textvariable=self.layout_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.time_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.gate_var).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.gate_check_text, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.gate_angle_text, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.cone_status_text, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.boat_sensor_status_text, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.predict_var, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.result_var, wraplength=290).pack(anchor=tk.W, pady=2)
        ttk.Label(right, textvariable=self.status_var, wraplength=290).pack(anchor=tk.W, pady=(10, 4))

        ttk.Separator(right).pack(fill=tk.X, pady=10)

        help_text = (
            "操作说明：\n"
            "1. 左键点击画布空白处可新增一个光电门。\n"
            "2. 左键拖动光电门可调整位置。\n"
            "3. 选中光电门后可用鼠标滚轮或按钮调整角度。\n"
            "4. 双击光电门可删除。\n"
            "5. 绿色为下一个目标门，蓝色为已通过门，红色为当前目标门。\n"
            "6. 决赛预设会显示 10 个引导门，便于按规则模拟整场比赛。"
        )
        ttk.Label(right, text=help_text, justify=tk.LEFT, wraplength=290).pack(anchor=tk.W, pady=(10, 0))

    def _bind_events(self) -> None:
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<MouseWheel>", self.on_canvas_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_canvas_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_canvas_mouse_wheel)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.root.bind("<space>", lambda _event: self.toggle_run())
        self.root.bind("<Right>", lambda _event: self.step_once())
        self.root.bind("<Escape>", lambda _event: self.stop_run())
        self.root.bind("<F11>", lambda _event: self.toggle_fullscreen())

    def toggle_run(self) -> None:
        self.running = not self.running
        if self.running:
            self.edit_mode = False
            self.status_var.set("运行模式：正在仿真")
            self._schedule_tick()
        else:
            self.status_var.set("已暂停：可继续编辑光电门")
            self._cancel_tick()
        self._draw_scene()

    def stop_run(self) -> None:
        self.running = False
        self.status_var.set("已停止")
        self._cancel_tick()
        self._draw_scene()

    def toggle_fullscreen(self) -> None:
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)
        self.status_var.set("全屏模式已开启" if not current else "已退出全屏模式")
        self._draw_scene()

    def toggle_edit_mode(self) -> None:
        if self.running:
            return
        self.edit_mode = not self.edit_mode
        self.status_var.set("编辑模式：可以拖动和放置光电门" if self.edit_mode else "浏览模式：仅查看场地")
        self._draw_scene()

    def step_once(self) -> None:
        if self.running:
            return
        self.edit_mode = False
        self._advance_simulation()
        self._draw_scene()
        self._update_stats()

    def reset_simulation(self) -> None:
        self.running = False
        self._cancel_tick()
        self.simulator.reset(self.gates)
        self.boat_trail.clear()
        self.selected_gate_index = None
        self.status_var.set("仿真已重置")
        self._draw_scene()
        self._update_stats()

    def export_logbook_entry(self) -> None:
        try:
            entry_dir = self._create_logbook_entry_dir()
            replay_data = self._build_replay_data()
            screenshot_path = entry_dir / "scene.jpg"
            report_path = entry_dir / "report.md"
            replay_path = entry_dir / "replay.json"

            self._save_canvas_screenshot(screenshot_path)
            replay_path.write_text(json.dumps(replay_data, ensure_ascii=False, indent=2), encoding="utf-8")
            report_path.write_text(self._build_report_text(replay_data), encoding="utf-8")

            self.status_var.set(f"日志已导出：{entry_dir.name}")
            messagebox.showinfo("导出完成", f"已导出到：{entry_dir}")
        except Exception as exc:  # pragma: no cover - UI error handling
            messagebox.showerror("导出失败", str(exc))

    def import_replay_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择复现文件",
            initialdir=self.logbook_root,
            filetypes=[("Replay JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
            self._restore_replay(snapshot)
            self.status_var.set(f"已导入复现文件：{Path(path).name}")
        except Exception as exc:  # pragma: no cover - UI error handling
            messagebox.showerror("导入失败", str(exc))

    def _create_logbook_entry_dir(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        layout_tag = "final10" if len(self.gates) >= 10 else f"g{len(self.gates)}"
        entry_dir = self.logbook_root / f"{timestamp}_{layout_tag}"
        suffix = 1
        while entry_dir.exists():
            entry_dir = self.logbook_root / f"{timestamp}_{layout_tag}_{suffix}"
            suffix += 1
        entry_dir.mkdir(parents=True, exist_ok=False)
        return entry_dir

    def _build_replay_data(self) -> dict:
        simulator_snapshot = self.simulator.export_snapshot()
        gate_results = simulator_snapshot.get("gate_results", [])
        results_map = {item["gate_id"]: item for item in gate_results}
        gate_summary = []
        for gate in self.gates:
            gate_summary.append(
                {
                    "gate_id": gate.gate_id,
                    "status": results_map.get(gate.gate_id, {}).get("status", "pending"),
                    "time_s": results_map.get(gate.gate_id, {}).get("time_s"),
                    "x": results_map.get(gate.gate_id, {}).get("x"),
                    "y": results_map.get(gate.gate_id, {}).get("y"),
                    "lateral_error": results_map.get(gate.gate_id, {}).get("lateral_error"),
                }
            )

        return {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "track_length_m": self.track_length_m,
            "track_width_m": self.track_width_m,
            "layout": self.layout_var.get(),
            "mode": self.mode_var.get(),
            "show_cone": self.show_cone_var.get(),
            "show_boat_sensor": self.show_boat_sensor_var.get(),
            "edit_mode": self.edit_mode,
            "running": self.running,
            "boat_trail": list(self.boat_trail),
            "gates": [asdict(gate) for gate in self.gates],
            "gate_summary": gate_summary,
            "simulator": simulator_snapshot,
            "status": self.status_var.get(),
            "time_text": self.time_var.get(),
            "gate_text": self.gate_var.get(),
            "predict_text": self.predict_var.get(),
            "result_text": self.result_var.get(),
        }

    def _build_report_text(self, replay_data: dict) -> str:
        simulator_snapshot = replay_data["simulator"]
        gate_summary = replay_data["gate_summary"]
        total_gates = len(gate_summary)
        passed_gates = sum(1 for item in gate_summary if item["status"] == "success")
        failed_gates = sum(1 for item in gate_summary if item["status"] == "failed")
        pending_gates = total_gates - passed_gates - failed_gates
        elapsed_time = simulator_snapshot.get("time_s", 0.0)
        finished = int(simulator_snapshot.get("current_gate_index", 0)) >= total_gates and total_gates > 0
        gate_results = simulator_snapshot.get("gate_results", [])
        average_gate_time = elapsed_time / max(1, passed_gates + failed_gates)

        lines = [
            "# C1-1 比赛日志报告",
            "",
            f"- 保存时间：{replay_data['saved_at']}",
            f"- 赛制：{replay_data['layout']}",
            f"- 赛道长度：{replay_data['track_length_m']} m",
            f"- 赛道宽度：{replay_data['track_width_m']} m",
            f"- 总门数：{total_gates}",
            f"- 已通过：{passed_gates}",
            f"- 已失败：{failed_gates}",
            f"- 未处理：{pending_gates}",
            f"- 总用时：{elapsed_time:.2f} s",
            f"- 平均门耗时：{average_gate_time:.2f} s",
            f"- 完成状态：{'已完成全部门' if finished else '未完成'}",
            f"- 红外发射圆锥：{'显示' if replay_data['show_cone'] else '隐藏'}",
            f"- 船载红外感应：{'显示' if replay_data['show_boat_sensor'] else '隐藏'}",
            "",
            "## 门结果",
            "",
            "| 门号 | 状态 | 时间(s) | X(m) | Y(m) | 横向偏差(m) |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for item in gate_summary:
            time_text = "-" if item["time_s"] is None else f"{item['time_s']:.2f}"
            x_text = "-" if item["x"] is None else f"{item['x']:.2f}"
            y_text = "-" if item["y"] is None else f"{item['y']:.2f}"
            error_text = "-" if item["lateral_error"] is None else f"{item['lateral_error']:.2f}"
            lines.append(
                f"| {item['gate_id']} | {item['status']} | {time_text} | {x_text} | {y_text} | {error_text} |"
            )

        lines.extend(
            [
                "",
                "## 运行摘要",
                "",
                f"- 当前目标索引：{simulator_snapshot.get('current_gate_index', 0)}",
                f"- 已记录事件：{len(simulator_snapshot.get('history', []))}",
                f"- 轨迹点数：{len(replay_data['boat_trail'])}",
                f"- 随机状态：已保存",
                "",
                "## 原始事件",
                "",
            ]
        )
        if simulator_snapshot.get("history"):
            for item in simulator_snapshot["history"]:
                lines.append(f"- {item}")
        else:
            lines.append("- 无")

        lines.extend(
            [
                "",
                "## 复现说明",
                "",
                "- `replay.json` 可直接导入恢复赛道、船体状态和门结果。",
                "- `scene.jpg` 为当前画布截图。",
                "- 本报告用于仓库归档和二次分析。",
            ]
        )
        return "\n".join(lines)

    def _save_canvas_screenshot(self, image_path: Path) -> None:
        if ImageGrab is None:
            raise RuntimeError("缺少 Pillow，无法导出 JPG 截图")
        self.root.update_idletasks()
        self.canvas.update_idletasks()
        left = self.canvas.winfo_rootx()
        top = self.canvas.winfo_rooty()
        right = left + self.canvas.winfo_width()
        bottom = top + self.canvas.winfo_height()
        image = ImageGrab.grab(bbox=(left, top, right, bottom))
        image.convert("RGB").save(image_path, format="JPEG", quality=92)

    def _restore_replay(self, snapshot: dict) -> None:
        self.running = False
        self._cancel_tick()

        self.track_length_m = int(snapshot.get("track_length_m", self.track_length_m))
        self.track_width_m = int(snapshot.get("track_width_m", self.track_width_m))
        self.track_length_var.set(self.track_length_m)
        self.track_width_var.set(self.track_width_m)
        self.track_length_text.set(f"赛道长度：{self.track_length_m} 米")
        self.track_width_text.set(f"赛道宽度：{self.track_width_m} 米")

        self.show_cone_var.set(bool(snapshot.get("show_cone", self.show_cone_var.get())))
        self.show_boat_sensor_var.set(bool(snapshot.get("show_boat_sensor", self.show_boat_sensor_var.get())))
        self.edit_mode = bool(snapshot.get("edit_mode", self.edit_mode))

        simulator_snapshot = snapshot.get("simulator", snapshot)
        self.simulator.load_snapshot(simulator_snapshot)
        self.gates = list(self.simulator.gates)
        self.boat_trail = [tuple(item) for item in snapshot.get("boat_trail", [])]
        self.selected_gate_index = None

        if len(self.gates) == 10:
            self.mode_var.set("决赛 10 门")
            self.layout_var.set("布局：决赛 10 门")
        elif len(self.gates) == 3:
            self.mode_var.set("初赛 3 门")
            self.layout_var.set("布局：初赛 3 门")
        else:
            self.mode_var.set("初赛 3 门")
            self.layout_var.set(f"布局：导入 {len(self.gates)} 个光电门")

        self._update_gate_standard_status()
        self._on_cone_toggle()
        self._on_boat_sensor_toggle()
        self._sync_viewport()
        self._draw_scene()
        self._update_stats()

    def load_selected_layout(self) -> None:
        self.running = False
        self._cancel_tick()
        if self.mode_var.get() == "决赛 10 门":
            self.gates = build_final_gates()
            self.layout_var.set("布局：决赛 10 门")
            self.status_var.set("已加载决赛 10 门布局")
        else:
            self.gates = build_preliminary_gates(3)
            self.layout_var.set("布局：初赛 3 门")
            self.status_var.set("已加载初赛 3 门布局")
        self.simulator.set_gates(self.gates)
        self.boat_trail.clear()
        self.selected_gate_index = None
        self._update_gate_standard_status()
        self._draw_scene()
        self._update_stats()

    def clear_gates(self) -> None:
        self.running = False
        self._cancel_tick()
        self.gates = []
        self.simulator.set_gates(self.gates)
        self.boat_trail.clear()
        self.selected_gate_index = None
        self.layout_var.set("布局：空白")
        self.status_var.set("已清空光电门，可点击添加")
        self._update_gate_standard_status()
        self._draw_scene()
        self._update_stats()

    def on_canvas_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self.running or not self.edit_mode:
            return
        world = self.canvas_to_world(event.x, event.y)
        gate_index = self._hit_test_gate(event.x, event.y)
        if gate_index is not None:
            self.selected_gate_index = gate_index
            self.gate_dragging = True
            self.status_var.set(f"选中第 {self.gates[gate_index].gate_id} 个光电门，拖动可调整")
            self._update_selected_gate_text()
            self._draw_scene()
            return

        new_gate = Gate(
            gate_id=len(self.gates) + 1,
            x=self._clamp_gate_x(world[0]),
            y=self._clamp_gate_y(world[1]),
            width=1.0,
            height=self.gate_standard_height,
            angle_deg=0.0,
        )
        self.gates.append(new_gate)
        self._renumber_gates()
        self.simulator.set_gates(self.gates)
        self.selected_gate_index = len(self.gates) - 1
        self.status_var.set(f"已新增第 {new_gate.gate_id} 个光电门")
        self._update_selected_gate_text()
        self._draw_scene()
        self._update_stats()

    def on_canvas_drag(self, event: tk.Event[tk.Canvas]) -> None:
        if self.running or not self.edit_mode or self.selected_gate_index is None:
            return
        if self.selected_gate_index < 0 or self.selected_gate_index >= len(self.gates):
            return
        self.gate_dragging = True
        x, y = self.canvas_to_world(event.x, event.y)
        gate = self.gates[self.selected_gate_index]
        self.gates[self.selected_gate_index] = Gate(
            gate_id=gate.gate_id,
            x=self._clamp_gate_x(x),
            y=self._clamp_gate_y(y),
            width=gate.width,
            height=gate.height,
            angle_deg=gate.angle_deg,
        )
        self.simulator.set_gates(self.gates)
        self._draw_scene()
        self._update_stats()

    def on_canvas_release(self, _event: tk.Event[tk.Canvas]) -> None:
        self.gate_dragging = False

    def on_canvas_double_click(self, event: tk.Event[tk.Canvas]) -> None:
        if self.running or not self.edit_mode:
            return
        gate_index = self._hit_test_gate(event.x, event.y)
        if gate_index is None:
            return
        del self.gates[gate_index]
        self._renumber_gates()
        self.simulator.set_gates(self.gates)
        if self.selected_gate_index is not None and self.selected_gate_index >= len(self.gates):
            self.selected_gate_index = None
        self._update_selected_gate_text()
        self.status_var.set("已删除一个光电门")
        self._draw_scene()
        self._update_stats()

    def on_canvas_mouse_wheel(self, event: tk.Event[tk.Canvas]) -> None:
        if self.running or not self.edit_mode or self.selected_gate_index is None:
            return
        if event.num == 4:
            delta = 5
        elif event.num == 5:
            delta = -5
        else:
            delta = 5 if event.delta > 0 else -5
        self.rotate_selected_gate(delta)

    def rotate_selected_gate(self, delta_deg: float) -> None:
        if self.running or self.selected_gate_index is None:
            return
        if self.selected_gate_index < 0 or self.selected_gate_index >= len(self.gates):
            return
        gate = self.gates[self.selected_gate_index]
        angle_deg = self._wrap_angle(gate.angle_deg + delta_deg)
        self.gates[self.selected_gate_index] = Gate(
            gate_id=gate.gate_id,
            x=gate.x,
            y=gate.y,
            width=gate.width,
            height=gate.height,
            angle_deg=angle_deg,
        )
        self.simulator.set_gates(self.gates)
        self._update_selected_gate_text()
        self.status_var.set(f"第 {gate.gate_id} 个光电门角度已调整为 {angle_deg:.0f}°")
        self._draw_scene()
        self._update_stats()

    def _update_selected_gate_text(self) -> None:
        if self.selected_gate_index is None or self.selected_gate_index >= len(self.gates):
            self.gate_angle_text.set("门角度：当前未选中")
            return
        gate = self.gates[self.selected_gate_index]
        self.gate_angle_text.set(f"门角度：第 {gate.gate_id} 门 {gate.angle_deg:.0f}°")

    def _schedule_tick(self) -> None:
        self._cancel_tick()
        self.after_id = self.root.after(120, self._tick)

    def _cancel_tick(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None

    def _tick(self) -> None:
        if not self.running:
            return
        self._advance_simulation()
        self._draw_scene()
        self._update_stats()
        if not self.simulator.is_finished():
            self._schedule_tick()
        else:
            self.running = False
            self.status_var.set("仿真完成：已过完全部光电门")
            self._cancel_tick()

    def _advance_simulation(self) -> None:
        if self.simulator.is_finished() or not self.gates:
            self.result_var.set("结果：当前没有可用光电门")
            return
        prediction, events = self.simulator.step(log=False)
        self.boat_trail.append((self.simulator.state.x, self.simulator.state.y))
        if prediction is not None:
            gate = self.simulator.current_gate()
            gate_text = f"当前目标：第 {gate.gate_id} 门" if gate is not None else "当前目标：已结束"
            self.gate_var.set(gate_text)
            self.predict_var.set(
                "预测：{}，距离 {:.2f} m，预计到门 {:.2f} s，横向偏差 {:.2f} m".format(
                    "可通过" if prediction.will_pass else "需修正",
                    prediction.distance,
                    prediction.time_to_gate,
                    prediction.lateral_error,
                )
            )
        if events:
            self.result_var.set("结果：" + events[-1])
        else:
            self.result_var.set("结果：仿真推进中")
        self.time_var.set(f"时间：{self.simulator.time_s:.1f} s")

    def _update_stats(self) -> None:
        if not self.gates:
            self.gate_var.set("当前目标：无")
            self.predict_var.set("预测：无门可模拟")
            self.time_var.set(f"时间：{self.simulator.time_s:.1f} s")
            self.result_var.set("结果：请先添加光电门")
            return

        self.time_var.set(f"时间：{self.simulator.time_s:.1f} s")
        if self.simulator.is_finished():
            self.gate_var.set("当前目标：已完成")
            self.predict_var.set("预测：全部光电门已通过")
            self.result_var.set(f"结果：已完成 {self.simulator.pass_count}/{len(self.gates)} 门")
        else:
            gate = self.simulator.current_gate()
            if gate is not None:
                prediction = self.simulator.predict_gate(gate)
                self.gate_var.set(f"当前目标：第 {gate.gate_id} 门")
                self.predict_var.set(
                    "预测：{}，距离 {:.2f} m，预计到门 {:.2f} s，横向偏差 {:.2f} m".format(
                        "可通过" if prediction.will_pass else "需修正",
                        prediction.distance,
                        prediction.time_to_gate,
                        prediction.lateral_error,
                    )
                )
                self.result_var.set(f"结果：已通过 {self.simulator.pass_count}/{len(self.gates)} 门")

    def _draw_scene(self) -> None:
        self._sync_viewport()
        self.canvas.delete("all")
        self._draw_background_grid()
        self._draw_track()
        self._draw_gate_cones()
        self._draw_boat_sensor()
        self._draw_gates()
        self._draw_boat()
        self._draw_trail()
        self._draw_legend()

    def _draw_background_grid(self) -> None:
        half_width = max(4, self._effective_track_width() / 2)
        left_index = int(-math.ceil(half_width))
        right_index = int(math.ceil(half_width))
        for meter_x in range(left_index, right_index + 1):
            x = self.world_to_canvas_x(meter_x)
            color = "#dfe7f1" if meter_x != 0 else "#9eb6d5"
            self.canvas.create_line(x, 20, x, self.canvas_height - 20, fill=color)
            self.canvas.create_text(x + 12, 18, text=str(meter_x), fill="#6b7d90", font=("Consolas", 8))
        for meter_y in range(0, self.track_length_m + 1, 10):
            y = self.world_to_canvas_y(meter_y)
            color = "#dfe7f1" if meter_y % 10 else "#9eb6d5"
            self.canvas.create_line(20, y, self.canvas_width - 20, y, fill=color)
            self.canvas.create_text(22, y - 10, text=str(meter_y), fill="#6b7d90", font=("Consolas", 8))

    def _draw_track(self) -> None:
        half_width = self._effective_track_width() / 2
        left = self.world_to_canvas_x(-half_width)
        right = self.world_to_canvas_x(half_width)
        top = self.world_to_canvas_y(self.track_length_m)
        bottom = self.world_to_canvas_y(0)
        self.canvas.create_rectangle(left, top, right, bottom, outline="#2c4c7c", width=3, fill="#dceefb")
        self.canvas.create_rectangle(left + 6, top + 6, right - 6, bottom - 6, outline="#7fb3d5", width=1, fill="#bfe3f7")
        self.canvas.create_text((left + right) / 2, top - 18, text="比赛航道", fill="#41546b", font=("Microsoft YaHei", 11, "bold"))

        self.canvas.create_text(left + 55, bottom - 20, text="起点", fill="#2c4c7c", font=("Microsoft YaHei", 10, "bold"))
        self.canvas.create_text(right - 55, top + 20, text="终点", fill="#2c4c7c", font=("Microsoft YaHei", 10, "bold"))

        for mark_y in range(10, self.track_length_m, 10):
            y = self.world_to_canvas_y(mark_y)
            self.canvas.create_line(left + 12, y, right - 12, y, fill="#7fb3d5", dash=(6, 6))

    def _draw_gates(self) -> None:
        for index, gate in enumerate(self.gates):
            gate_color = "#2d6cdf"
            if self.simulator.is_finished() and index < len(self.gates):
                gate_color = "#2fa86b"
            elif index == self.simulator.current_gate_index:
                gate_color = "#d94f4f"
            elif index < self.simulator.current_gate_index:
                gate_color = "#2f8fda"

            x = self.world_to_canvas_x(gate.x)
            y = self.world_to_canvas_y(gate.y)
            gate_half = max(18, gate.width * self.pixels_per_meter_x * 0.5)
            angle_rad = math.radians(gate.angle_deg)
            dx = math.cos(angle_rad) * gate_half
            dy = math.sin(angle_rad) * gate_half
            px = -math.sin(angle_rad) * 10
            py = math.cos(angle_rad) * 10
            self.canvas.create_line(x - dx, y + dy, x + dx, y - dy, fill=gate_color, width=6)
            self.canvas.create_line(x - dx + px, y + dy + py, x - dx - px, y + dy - py, fill=gate_color, width=4)
            self.canvas.create_line(x + dx + px, y - dy + py, x + dx - px, y - dy - py, fill=gate_color, width=4)
            self.canvas.create_line(x, y - 18, x, y + 18, fill="#1e1e1e", width=1, dash=(2, 2))
            self.canvas.create_text(x, y - 22, text=f"门 {gate.gate_id}", fill=gate_color, font=("Microsoft YaHei", 9, "bold"))
            self.canvas.create_text(x + 110, y + 2, text=f"{gate.width:.1f}m × {gate.height:.1f}m / {gate.angle_deg:.0f}°", fill="#46627f", font=("Consolas", 8))

    def _draw_gate_cones(self) -> None:
        if not self.show_cone_var.get():
            self.cone_status_text.set("发射圆锥：隐藏")
            return

        gate = self.simulator.current_gate()
        if gate is None:
            self.cone_status_text.set("发射圆锥：显示，当前无可用引导门")
            return

        cone_length_m = 4.0
        cone_half_width_m = cone_length_m
        boat_y = self.simulator.state.y
        x = self.world_to_canvas_x(gate.x)
        y = self.world_to_canvas_y(gate.y)
        direction = -1 if boat_y < gate.y else 1
        next_y = self.world_to_canvas_y(gate.y + direction * cone_length_m)
        left_x = self.world_to_canvas_x(gate.x - cone_half_width_m)
        right_x = self.world_to_canvas_x(gate.x + cone_half_width_m)

        self.canvas.create_polygon(
            x,
            y,
            left_x,
            next_y,
            right_x,
            next_y,
            fill="#ffb703",
            outline="#f4a261",
            stipple="gray50",
            width=1,
        )
        self.canvas.create_text(x, y + 8, text="90°", fill="#8b5e34", font=("Consolas", 8, "bold"))
        self.cone_status_text.set("发射圆锥：显示，约90°，朝向当前小船")

    def _draw_boat_sensor(self) -> None:
        if not self.show_boat_sensor_var.get():
            self.boat_sensor_status_text.set("船载感应：隐藏")
            return

        gate = self.simulator.current_gate()
        if gate is None:
            self.boat_sensor_status_text.set("船载感应：显示，当前无目标门")
            return

        state = self.simulator.state
        boat_x = self.world_to_canvas_x(state.x)
        boat_y = self.world_to_canvas_y(state.y)
        target_angle = math.degrees(math.atan2(gate.y - state.y, gate.x - state.x))
        heading_angle = state.heading_deg
        diff = self._wrap_angle(target_angle - heading_angle)
        detected = abs(diff) <= 45 and math.hypot(gate.x - state.x, gate.y - state.y) <= 12

        sensor_length_m = 4.5
        sensor_half_angle = 45.0
        left_angle = math.radians(heading_angle - sensor_half_angle)
        right_angle = math.radians(heading_angle + sensor_half_angle)
        tip_angle = math.radians(heading_angle)
        tip_x = self.world_to_canvas_x(state.x + math.cos(tip_angle) * sensor_length_m)
        tip_y = self.world_to_canvas_y(state.y + math.sin(tip_angle) * sensor_length_m)
        left_x = self.world_to_canvas_x(state.x + math.cos(left_angle) * sensor_length_m)
        left_y = self.world_to_canvas_y(state.y + math.sin(left_angle) * sensor_length_m)
        right_x = self.world_to_canvas_x(state.x + math.cos(right_angle) * sensor_length_m)
        right_y = self.world_to_canvas_y(state.y + math.sin(right_angle) * sensor_length_m)

        fill = "#8ecae6" if detected else "#ffd166"
        outline = "#219ebc" if detected else "#f4a261"
        self.canvas.create_polygon(
            boat_x,
            boat_y,
            left_x,
            left_y,
            tip_x,
            tip_y,
            right_x,
            right_y,
            fill=fill,
            outline=outline,
            stipple="gray50",
            width=1,
        )
        self.canvas.create_line(boat_x, boat_y, tip_x, tip_y, fill=outline, width=2, dash=(4, 2))
        self.canvas.create_text(boat_x, boat_y - 28, text="IR", fill=outline, font=("Consolas", 9, "bold"))
        self.boat_sensor_status_text.set(
            f"船载感应：显示，朝向当前目标门，{'已检测到' if detected else '未进入'} 感应范围"
        )

    def _draw_boat(self) -> None:
        state = self.simulator.state
        x = self.world_to_canvas_x(state.x)
        y = self.world_to_canvas_y(state.y)
        boat_length = 32
        boat_width = 15
        angle = math.radians(state.heading_deg)
        tip_x = x + math.cos(angle) * boat_length
        tip_y = y - math.sin(angle) * boat_length
        rear_left_x = x + math.cos(angle + math.pi * 0.75) * boat_width
        rear_left_y = y - math.sin(angle + math.pi * 0.75) * boat_width
        rear_right_x = x + math.cos(angle - math.pi * 0.75) * boat_width
        rear_right_y = y - math.sin(angle - math.pi * 0.75) * boat_width
        fill = "#1d3557"
        self.canvas.create_polygon(tip_x, tip_y, rear_left_x, rear_left_y, rear_right_x, rear_right_y, fill=fill, outline="#0b1f33", width=2)
        self.canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#f4a261", outline="")
        self.canvas.create_line(x, y, tip_x, tip_y, fill="#f4a261", width=3)
        self.canvas.create_text(x + 40, y - 14, text=f"{state.heading_deg:.0f}°", fill="#1d3557", font=("Consolas", 9, "bold"))

    def _draw_trail(self) -> None:
        if len(self.boat_trail) < 2:
            return
        points: List[float] = []
        for x, y in self.boat_trail:
            points.extend([self.world_to_canvas_x(x), self.world_to_canvas_y(y)])
        self.canvas.create_line(*points, fill="#f4a261", width=2, smooth=True)

    def _draw_legend(self) -> None:
        x0 = 30
        y0 = max(self.canvas_height - 36, 28)
        labels = [
            ("#d94f4f", "当前目标门"),
            ("#2f8fda", "已通过门"),
            ("#2fa86b", "仿真结束门"),
            ("#f4a261", "船模轨迹"),
        ]
        width = max(self.canvas_width - 60, 240)
        per_item = max(120, min(180, width // len(labels)))
        for offset, (color, text) in enumerate(labels):
            x = x0 + offset * per_item
            self.canvas.create_rectangle(x, y0, x + 16, y0 + 16, fill=color, outline="")
            self.canvas.create_text(x + 26, y0 + 8, text=text, anchor=tk.W, fill="#41546b", font=("Microsoft YaHei", 9))

    def _hit_test_gate(self, canvas_x: int, canvas_y: int) -> Optional[int]:
        for index, gate in enumerate(self.gates):
            gx = self.world_to_canvas_x(gate.x)
            gy = self.world_to_canvas_y(gate.y)
            angle_rad = math.radians(gate.angle_deg)
            half = max(18, gate.width * self.pixels_per_meter_x * 0.5)
            dx = canvas_x - gx
            dy = canvas_y - gy
            along = abs(dx * math.cos(angle_rad) + dy * math.sin(angle_rad))
            across = abs(-dx * math.sin(angle_rad) + dy * math.cos(angle_rad))
            if along <= half + 20 and across <= 20:
                return index
        return None

    def _clamp_gate_x(self, x: float) -> float:
        half_width = self._effective_track_width() / 2
        return max(-(half_width - 0.5), min(half_width - 0.5, x))

    def _clamp_gate_y(self, y: float) -> float:
        return max(1.0, min(float(self.track_length_m - 1), y))

    def _on_cone_toggle(self) -> None:
        self.cone_status_text.set("发射圆锥：显示，约90°，朝向当前小船" if self.show_cone_var.get() else "发射圆锥：隐藏")
        self._draw_scene()

    def _on_boat_sensor_toggle(self) -> None:
        self.boat_sensor_status_text.set("船载感应：显示" if self.show_boat_sensor_var.get() else "船载感应：隐藏")
        self._draw_scene()

    def _on_track_length_change(self, value: str) -> None:
        try:
            length = int(float(value))
        except ValueError:
            return
        self._apply_track_length(length)
        self._draw_scene()

    def _on_track_width_change(self, value: str) -> None:
        try:
            width = int(float(value))
        except ValueError:
            return
        self._apply_track_width(width)
        self._draw_scene()

    def _apply_track_length(self, length: int) -> None:
        self.track_length_m = max(30, min(150, length))
        self.track_length_text.set(f"赛道长度：{self.track_length_m} 米")
        self.track_length_var.set(self.track_length_m)
        self._normalize_gates()

    def _apply_track_width(self, width: int) -> None:
        self.track_width_m = max(0, min(150, width))
        self.track_width_text.set(f"赛道宽度：{self.track_width_m} 米")
        self.track_width_var.set(self.track_width_m)
        self._normalize_gates()
        self._update_gate_standard_status()

    def _normalize_gates(self) -> None:
        self.gates = [
            Gate(
                gate_id=index + 1,
                x=self._clamp_gate_x(gate.x),
                y=self._clamp_gate_y(gate.y),
                width=gate.width,
                height=gate.height,
            )
            for index, gate in enumerate(self.gates)
        ]
        self.simulator.set_gates(self.gates)
        self._update_gate_standard_status()

    def _update_gate_standard_status(self) -> None:
        if not self.gates:
            self.gate_check_text.set("引导门标准：1.0m × 0.4m，当前无光电门")
            return

        compliant = all(
            abs(gate.width - self.gate_standard_width) < 1e-6 and abs(gate.height - self.gate_standard_height) < 1e-6
            for gate in self.gates
        )
        status = "已符合" if compliant else "存在不符合项"
        self.gate_check_text.set(f"引导门标准：{self.gate_standard_width:.1f}m × {self.gate_standard_height:.1f}m，{status}")

    @staticmethod
    def _wrap_angle(angle: float) -> float:
        while angle <= -180:
            angle += 360
        while angle > 180:
            angle -= 360
        return angle

    def _effective_track_width(self) -> float:
        if self.track_width_m <= 0:
            return 12.0
        return float(self.track_width_m)

    def _sync_viewport(self) -> None:
        canvas_width = max(self.canvas.winfo_width(), 200)
        canvas_height = max(self.canvas.winfo_height(), 200)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        drawable_width = max(canvas_width - 80, 120)
        drawable_height = max(canvas_height - 90, 120)
        self.pixels_per_meter_x = drawable_width / max(self._effective_track_width(), 1)
        self.pixels_per_meter_y = drawable_height / max(self.track_length_m, 1)
        self.origin_x = canvas_width / 2
        self.origin_y = canvas_height - 50

    def on_canvas_resize(self, _event: tk.Event[tk.Canvas]) -> None:
        self._sync_viewport()
        self._draw_scene()

    def _renumber_gates(self) -> None:
        updated: List[Gate] = []
        for index, gate in enumerate(self.gates, start=1):
            updated.append(Gate(gate_id=index, x=gate.x, y=gate.y, width=gate.width, height=gate.height, angle_deg=gate.angle_deg))
        self.gates = updated
        self.layout_var.set(f"布局：{len(self.gates)} 个光电门")

    def canvas_to_world(self, canvas_x: int, canvas_y: int) -> tuple[float, float]:
        world_x = (canvas_x - self.origin_x) / self.pixels_per_meter_x
        world_y = (self.origin_y - canvas_y) / self.pixels_per_meter_y
        return world_x, world_y

    def world_to_canvas_x(self, world_x: float) -> float:
        return self.origin_x + world_x * self.pixels_per_meter_x

    def world_to_canvas_y(self, world_y: float) -> float:
        return self.origin_y - world_y * self.pixels_per_meter_y


def main() -> None:
    root = tk.Tk()
    app = RaceSimulationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
