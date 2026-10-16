"""标准格式 30fps CSV 录制器。

列名与顺序严格对齐「标准静默动作Ver2026091001.csv」。
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from enum import Enum, auto
from typing import List, Optional

from PyQt5 import QtCore
from pylivelinkface import FaceBlendShape, PyLiveLinkFace


class StandardCsvSchema:
    """与标准样例完全一致的 CSV 表头契约。"""

    # 列名顺序不可更改，必须与标准文件第一行一致
    HEADER: List[str] = [
        "Timecode",
        "BlendshapeCount",
        "EyeBlinkLeft",
        "EyeLookDownLeft",
        "EyeLookInLeft",
        "EyeLookOutLeft",
        "EyeLookUpLeft",
        "EyeSquintLeft",
        "EyeWideLeft",
        "EyeBlinkRight",
        "EyeLookDownRight",
        "EyeLookInRight",
        "EyeLookOutRight",
        "EyeLookUpRight",
        "EyeSquintRight",
        "EyeWideRight",
        "JawForward",
        "JawLeft",
        "JawRight",
        "JawOpen",
        "MouthClose",
        "MouthFunnel",
        "MouthPucker",
        "MouthLeft",
        "MouthRight",
        "MouthSmileLeft",
        "MouthSmileRight",
        "MouthFrownLeft",
        "MouthFrownRight",
        "MouthDimpleLeft",
        "MouthDimpleRight",
        "MouthStretchLeft",
        "MouthStretchRight",
        "MouthRollLower",
        "MouthRollUpper",
        "MouthShrugLower",
        "MouthShrugUpper",
        "MouthPressLeft",
        "MouthPressRight",
        "MouthLowerDownLeft",
        "MouthLowerDownRight",
        "MouthUpperUpLeft",
        "MouthUpperUpRight",
        "BrowDownLeft",
        "BrowDownRight",
        "BrowInnerUp",
        "BrowOuterUpLeft",
        "BrowOuterUpRight",
        "CheekPuff",
        "CheekSquintLeft",
        "CheekSquintRight",
        "NoseSneerLeft",
        "NoseSneerRight",
        "TongueOut",
        "HeadYaw",
        "HeadPitch",
        "HeadRoll",
    ]

    TIMECODE_VALUE = "0"
    BLENDSHAPE_COUNT = "61"
    # 标准文件中数值统一为 8 位小数
    VALUE_FORMAT = "%.8f"

    # 除 Timecode / BlendshapeCount 外的通道，对应 FaceBlendShape 0–54
    BLENDSHAPE_COLUMNS: List[str] = HEADER[2:]

    @classmethod
    def blendshape_enums(cls) -> List[FaceBlendShape]:
        """按表头顺序解析为 FaceBlendShape 枚举列表。"""
        return [FaceBlendShape[name] for name in cls.BLENDSHAPE_COLUMNS]


class _RecorderState(Enum):
    """录制器状态机。"""

    IDLE = auto()
    RECORDING = auto()


class CsvRecorder(QtCore.QObject):
    """30fps CSV 录制器（观察者）：缓存最新帧，按固定节拍写盘。"""

    FPS = 30
    # 约 33.333ms，对应 30fps
    INTERVAL_MS = int(round(1000 / FPS))

    # 写盘失败时向外通知，便于 UI 弹窗
    write_error = QtCore.pyqtSignal(str)
    # 录制状态变化：(是否正在录制, 当前文件路径或空串)
    recording_changed = QtCore.pyqtSignal(bool, str)

    def __init__(
        self,
        parent: Optional[QtCore.QObject] = None,
        output_dir: str = "recordings",
    ):
        super().__init__(parent)
        self._output_dir = output_dir
        self._state = _RecorderState.IDLE
        self._latest_frame: Optional[PyLiveLinkFace] = None
        self._file = None
        self._writer: Optional[csv.writer] = None
        self._path: str = ""
        self._shapes = StandardCsvSchema.blendshape_enums()

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def is_recording(self) -> bool:
        return self._state == _RecorderState.RECORDING

    @property
    def current_path(self) -> str:
        return self._path

    def on_frame(self, live_link_face: PyLiveLinkFace) -> None:
        """观察者入口：只更新最新一帧，不直接写盘。"""
        self._latest_frame = live_link_face

    def default_output_path(self) -> str:
        """生成默认输出路径：recordings/capture_YYYYMMDD_HHMMSS.csv"""
        os.makedirs(self._output_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self._output_dir, f"capture_{stamp}.csv")

    def start(self, path: Optional[str] = None) -> bool:
        """开始录制。已在录制中则忽略并返回 False。"""
        if self._state == _RecorderState.RECORDING:
            return False

        target = path or self.default_output_path()
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)

        try:
            # newline='' 保证 csv 模块跨平台换行正确
            self._file = open(target, "w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._file)
            self._writer.writerow(StandardCsvSchema.HEADER)
            self._file.flush()
        except OSError as exc:
            self._cleanup_file()
            self.write_error.emit(f"无法创建录制文件：{exc}")
            return False

        self._path = target
        self._state = _RecorderState.RECORDING
        self._timer.start()
        self.recording_changed.emit(True, self._path)
        return True

    def stop(self) -> None:
        """停止录制并关闭文件。未在录制时无操作。"""
        if self._state != _RecorderState.RECORDING:
            return

        self._timer.stop()
        self._cleanup_file()
        self._state = _RecorderState.IDLE
        finished_path = self._path
        self._path = ""
        self.recording_changed.emit(False, finished_path)

    def _cleanup_file(self) -> None:
        """安全关闭文件句柄。"""
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
        self._file = None
        self._writer = None

    def _tick(self) -> None:
        """30fps 节拍：写出一行标准格式数据。"""
        if self._state != _RecorderState.RECORDING or self._writer is None:
            return

        try:
            row = self._build_row(self._latest_frame)
            self._writer.writerow(row)
            # 及时落盘，降低异常退出时丢数据风险
            if self._file is not None:
                self._file.flush()
        except OSError as exc:
            self.write_error.emit(f"写入 CSV 失败：{exc}")
            self.stop()

    def _build_row(self, frame: Optional[PyLiveLinkFace]) -> List[str]:
        """构造一行：Timecode=0，BlendshapeCount=61，其余通道 %.8f。"""
        values: List[str] = [
            StandardCsvSchema.TIMECODE_VALUE,
            StandardCsvSchema.BLENDSHAPE_COUNT,
        ]
        fmt = StandardCsvSchema.VALUE_FORMAT
        if frame is None:
            # 尚未收到任何帧：通道写 0
            values.extend(fmt % 0.0 for _ in self._shapes)
        else:
            values.extend(
                fmt % frame.get_blendshape(shape) for shape in self._shapes
            )
        return values
