import sys
import socket
import numpy as np
from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
from pylivelinkface import PyLiveLinkFace, FaceBlendShape

from csv_recorder import CsvRecorder

# --- 完整的中文映射表 ---
CHINESE_MAPPING = {
    "EyeBlinkLeft": "左眼闭合", "EyeBlinkRight": "右眼闭合",
    "EyeLookDownLeft": "左眼下看", "EyeLookDownRight": "右眼下看",
    "EyeLookInLeft": "左眼向内", "EyeLookInRight": "右眼向内",
    "EyeLookOutLeft": "左眼向外", "EyeLookOutRight": "右眼向外",
    "EyeWideLeft": "左眼睁大", "EyeWideRight": "右眼睁大",
    "EyeSquintLeft": "左眼眯眼", "EyeSquintRight": "右眼眯眼",
    "JawOpen": "张嘴", "JawForward": "下颚前伸", "JawLeft": "下颚向左", "JawRight": "下颚向右",
    "MouthSmileLeft": "左嘴角上扬", "MouthSmileRight": "右嘴角上扬",
    "MouthFrownLeft": "左嘴角下沉", "MouthFrownRight": "右嘴角下沉",
    "MouthPucker": "嘟嘴", "MouthFunnel": "漏斗嘴", "MouthClose": "闭嘴",
    "MouthLeft": "嘴向左移", "MouthRight": "嘴向右移", "MouthDimpleLeft": "左酒窝", "MouthDimpleRight": "右酒窝",
    "MouthStretchLeft": "左嘴角拉伸", "MouthStretchRight": "右嘴角拉伸", "MouthRollLower": "下唇内卷", "MouthRollUpper": "上唇内卷",
    "MouthShrugLower": "下唇撅起", "MouthShrugUpper": "上唇撅起", "MouthPressLeft": "左抿嘴", "MouthPressRight": "右抿嘴",
    "MouthLowerDownLeft": "左下唇压低", "MouthLowerDownRight": "右下唇压低", "MouthUpperUpLeft": "左上唇抬高", "MouthUpperUpRight": "右上唇抬高",
    "BrowDownLeft": "左眉压低", "BrowDownRight": "右眉压低", "BrowInnerUp": "眉心上扬", "BrowOuterUpLeft": "左眉外侧上扬", "BrowOuterUpRight": "右眉外侧上扬",
    "CheekPuff": "鼓腮", "CheekSquintLeft": "左脸颊眯起", "CheekSquintRight": "右脸颊眯起",
    "NoseSneerLeft": "左鼻翼抽动", "NoseSneerRight": "右鼻翼抽动", "TongueOut": "吐舌头",
    "HeadPitch": "抬头低头", "HeadYaw": "左右转头", "HeadRoll": "左右歪头",
    "LeftEyeYaw": "左眼球左右", "LeftEyePitch": "左眼球上下", "LeftEyeRoll": "左眼球翻转",
    "RightEyeYaw": "右眼球左右", "RightEyePitch": "右眼球上下", "RightEyeRoll": "右眼球翻转"
}

UDP_PORT = 11111
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("", UDP_PORT))
s.setblocking(False)

class LiveLinkVisualizer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Link Face ARKit 4.52+ 表情监测器")
        self.resize(1000, 800)

        # 1. 初始化容器
        self.scroll = QtWidgets.QScrollArea()
        self.setCentralWidget(self.scroll)
        self.content_widget = QtWidgets.QWidget()
        self.scroll.setWidget(self.content_widget)
        self.scroll.setWidgetResizable(True)
        self.layout = QtWidgets.QVBoxLayout(self.content_widget)
        
        # 移除默认的边距
        self.layout.setContentsMargins(0, 0, 0, 0)

        # 采集工具条：开始 / 停止写入 30fps 标准 CSV
        self._setup_recording_toolbar()

        # 2. 实例化绘图对象
        self.plot_widget = pg.PlotWidget()
        self.layout.addWidget(self.plot_widget)

        # 3. 数据与字体配置
        self.shapes = [s for s in FaceBlendShape]
        self.shape_names = [CHINESE_MAPPING.get(s.name, s.name) for s in self.shapes]
        
        self.font = QtGui.QFont("Microsoft YaHei", 10)
        self.font_metrics = QtGui.QFontMetrics(self.font)
        
        text_height = self.font_metrics.height()
        item_spacing = int(text_height * 2.5) 
        total_canvas_height = item_spacing * len(self.shapes)
        
        self.plot_widget.setMinimumHeight(total_canvas_height)

        self.y_pos = np.arange(len(self.shapes), dtype=float)
        self.x_val = np.zeros(len(self.shapes))

        # --- 核心修改区 ---
        # 翻转 Y 轴
        self.plot_widget.invertY(True)
        self.plot_widget.setYRange(-0.5, len(self.shapes) - 0.5, padding=0)
        
        # 改变 X 轴范围，使其包含负数区域（假设你的数据域是 -1 到 1）
        self.plot_widget.setXRange(-1.0, 1.0)
        self.plot_widget.setMouseEnabled(x=False, y=False)

        # 在 X=0 的位置添加一条垂直的白色虚线作为基准线，方便查看正负伸展方向
        zero_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('w', width=1, style=QtCore.Qt.DashLine))
        self.plot_widget.addItem(zero_line)
        # -------------------

        # 配置左轴标签
        left_axis = self.plot_widget.getAxis('left')
        ticks = [(i, name) for i, name in enumerate(self.shape_names)]
        left_axis.setTicks([ticks])
        left_axis.setTickFont(self.font)
        
        max_text_width = max([self.font_metrics.boundingRect(name).width() for name in self.shape_names])
        left_axis.setWidth(max_text_width + 25)

        # 4. 创建柱状图
        # x0=0 确保无论 x_val 是正是负，柱子都是从 0 点开始生长的
        self.bar_graph = pg.BarGraphItem(
            x0=0, 
            y=self.y_pos, 
            height=0.5, 
            width=self.x_val, 
            brush=pg.mkBrush(0, 230, 230, 255),
            pen=pg.mkPen('w', width=0.5)        
        )
        self.plot_widget.addItem(self.bar_graph)

        # 5. 定时器刷新
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(16)

    def _setup_recording_toolbar(self) -> None:
        """初始化 CSV 录制器与开始/停止采集工具条。"""
        self.recorder = CsvRecorder(parent=self)
        self.recorder.write_error.connect(self._on_record_error)
        self.recorder.recording_changed.connect(self._on_recording_changed)

        toolbar = QtWidgets.QToolBar("采集")
        toolbar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, toolbar)

        self.btn_start = QtWidgets.QAction("开始采集", self)
        self.btn_stop = QtWidgets.QAction("停止采集", self)
        self.btn_start.triggered.connect(self._start_recording)
        self.btn_stop.triggered.connect(self._stop_recording)
        self.btn_stop.setEnabled(False)

        toolbar.addAction(self.btn_start)
        toolbar.addAction(self.btn_stop)

        self.status_label = QtWidgets.QLabel("未采集")
        toolbar.addWidget(self.status_label)

    def _start_recording(self) -> None:
        """开始写入 30fps 标准 CSV。"""
        self.recorder.start()

    def _stop_recording(self) -> None:
        """停止采集并关闭文件。"""
        self.recorder.stop()

    def _on_recording_changed(self, recording: bool, path: str) -> None:
        """根据录制状态更新按钮与状态栏文案。"""
        self.btn_start.setEnabled(not recording)
        self.btn_stop.setEnabled(recording)
        if recording:
            self.status_label.setText(f"采集中 → {path}")
        elif path:
            self.status_label.setText(f"已保存 → {path}")
        else:
            self.status_label.setText("未采集")

    def _on_record_error(self, message: str) -> None:
        """磁盘写失败时提示用户。"""
        QtWidgets.QMessageBox.critical(self, "采集失败", message)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """窗口关闭时若仍在录制则先安全停止。"""
        if self.recorder.is_recording:
            self.recorder.stop()
        super().closeEvent(event)

    def update_data(self):
        try:
            last_frame = None
            while True:
                data, _ = s.recvfrom(2048)
                success, live_link_face = PyLiveLinkFace.decode(data)
                if success:
                    last_frame = live_link_face
        except BlockingIOError:
            if last_frame:
                # 旁路喂给录制器（观察者），不影响柱状图逻辑
                self.recorder.on_frame(last_frame)
                new_widths = [last_frame.get_blendshape(shape) for shape in self.shapes]
                self.bar_graph.setOpts(width=np.array(new_widths))

if __name__ == "__main__":
    # --- 高 DPI 适配核心部分 ---
    # 必须在 QApplication 实例化之前设置！
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    # 支持更高级的 DPI 缩放策略 (PyQt5 后期版本可用)
    if hasattr(QtWidgets.QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
        QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Microsoft YaHei", 9))
    
    window = LiveLinkVisualizer()
    window.show()
    sys.exit(app.exec_())