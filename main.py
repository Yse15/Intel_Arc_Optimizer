"""
Intel Arc GPU Optimizer & Shader Cache Cleaner
Standalone utility for Intel Arc (Battlemage / Alchemist) GPUs.
"""

import sys
import os
import ctypes
import html
import tempfile
import traceback
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QProgressBar, QTextEdit,
    QTabWidget, QScrollArea, QFrame, QMessageBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot

from config_intel import (
    detect_gpu_info, INTEL_TWEAKS, INTEL_SVCS,
    build_intel_batch_script, build_intel_revert_batch_script,
    parse_batch_output, run_ps, cleanup_legacy_persistence
)
from shader_cleaner import scan_all_caches, clean_caches, format_bytes


# ── Глобальный обработчик исключений ─────────────────────────────────────────
def _global_exception_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    err = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[FATAL ERROR] {err}", file=sys.stderr)


sys.excepthook = _global_exception_handler


# ── Подготовка векторных иконок для Qt Style Sheets ─────────────────────────
def _get_check_icon_path() -> str:
    """Создаёт локальный SVG-файл галочки для гарантированной отрисовки в QSS."""
    svg_dir = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()), "IntelArcOptimizer")
    try:
        os.makedirs(svg_dir, exist_ok=True)
        svg_file = os.path.join(svg_dir, "arc_check.svg")
        if not os.path.isfile(svg_file) or os.path.getsize(svg_file) < 20:
            svg_content = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
                'viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="3" '
                'stroke-linecap="round" stroke-linejoin="round">'
                '<polyline points="20 6 9 17 4 12"/>'
                '</svg>'
            )
            with open(svg_file, "w", encoding="utf-8") as f:
                f.write(svg_content)
        return svg_file.replace("\\", "/")
    except Exception:
        return ""


_CHECK_SVG_PATH = _get_check_icon_path()

# ── Стили интерфейса (QSS со строгими селекторами свойств) ───────────────────
QSS_THEME = f"""
QMainWindow {{
    background-color: #0b0f19;
}}
QWidget {{
    color: #e2e8f0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}
QFrame[class="Card"] {{
    background-color: #111827;
    border: 1px solid #1f293d;
    border-radius: 10px;
}}
QFrame[class="HeaderCard"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0f172a, stop:1 #1e1b4b);
    border: 1px solid #2e3856;
    border-radius: 12px;
}}
QTabWidget::pane {{
    border: 1px solid #1f293d;
    background: #0b0f19;
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: #111827;
    color: #94a3b8;
    padding: 10px 24px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: bold;
    border: 1px solid #1f293d;
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: #1e293b;
    color: #00c7fd;
    border-bottom: 2px solid #00c7fd;
}}
QTabBar::tab:hover {{
    color: #f1f5f9;
}}
QPushButton[class="PrimaryBtn"] {{
    background-color: #0071c5;
    color: #ffffff;
    font-weight: bold;
    font-size: 13px;
    padding: 8px 18px;
    border-radius: 8px;
    border: 1px solid #00a4fd;
}}
QPushButton[class="PrimaryBtn"]:hover {{
    background-color: #0090f7;
}}
QPushButton[class="AccentBtn"] {{
    background-color: #00c7fd;
    color: #0b0f19;
    font-weight: bold;
    font-size: 13px;
    padding: 8px 18px;
    border-radius: 8px;
    border: none;
}}
QPushButton[class="AccentBtn"]:hover {{
    background-color: #38bdf8;
}}
QPushButton[class="AccentBtn"]:disabled {{
    background-color: #1e293b;
    color: #64748b;
}}
QPushButton[class="DangerBtn"] {{
    background-color: #1e1e2d;
    color: #ef4444;
    font-weight: bold;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid #ef4444;
}}
QPushButton[class="DangerBtn"]:hover {{
    background-color: #ef4444;
    color: #ffffff;
}}
QPushButton[class="DangerBtn"]:disabled {{
    background-color: #161a24;
    color: #475569;
    border-color: #334155;
}}
QPushButton[class="SecondaryBtn"] {{
    background-color: #1e293b;
    color: #cbd5e1;
    padding: 6px 14px;
    border-radius: 6px;
    border: 1px solid #334155;
}}
QPushButton[class="SecondaryBtn"]:hover {{
    background-color: #334155;
    color: #f8fafc;
}}
QPushButton[class="SecondaryBtn"]:disabled {{
    background-color: #0f172a;
    color: #475569;
    border-color: #1e293b;
}}
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    font-weight: 600;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #0f172a;
}}
QCheckBox::indicator:checked {{
    background-color: #0071c5;
    border-color: #00c7fd;
    image: url("{_CHECK_SVG_PATH}");
}}
QCheckBox::indicator:hover {{
    border-color: #00c7fd;
}}
QProgressBar {{
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 14px;
}}
QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0071c5, stop:1 #00c7fd);
    border-radius: 5px;
}}
QTextEdit[class="Console"] {{
    background-color: #070a12;
    color: #38bdf8;
    border: 1px solid #1e293b;
    border-radius: 8px;
    font-family: "Consolas", monospace;
    font-size: 12px;
    padding: 6px;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
"""


# ── Фоновые воркеры ──────────────────────────────────────────────────────────
class InitWorker(QObject):
    """Фоновый сбор параметров оборудования и кэша при запуске."""
    done = Signal(dict, list)

    @Slot()
    def run(self):
        try:
            # Разовая миграция: очистка устаревших задач автозапуска (флаг-файл < 0.1 мс)
            cleanup_legacy_persistence()
            gpu_info = detect_gpu_info()
            caches = scan_all_caches()
            self.done.emit(gpu_info, caches)
        except Exception:
            self.done.emit({}, [])


class RescanWorker(QObject):
    """Фоновое повторное сканирование кэша шейдеров."""
    done = Signal(list)

    @Slot()
    def run(self):
        try:
            caches = scan_all_caches()
            self.done.emit(caches)
        except Exception:
            self.done.emit([])


class ApplyWorker(QObject):
    progress = Signal(int, int)
    log_msg = Signal(str, str)
    finished = Signal(int, int)

    def __init__(self, keys_to_apply):
        super().__init__()
        self.keys = keys_to_apply

    @Slot()
    def run(self):
        success_count = 0
        ordered_len = len(self.keys)
        try:
            self.log_msg.emit("⚡ Запуск пакетной оптимизации Intel Arc...", "info")
            ps_code, ordered = build_intel_batch_script(self.keys)
            ordered_len = len(ordered)
            self.progress.emit(15, 100)

            r = run_ps(ps_code, timeout=45)
            self.progress.emit(70, 100)

            if r.returncode != 0 and r.stderr:
                err_text = r.stderr.decode("utf-8", errors="ignore").strip()
                if err_text:
                    self.log_msg.emit(f"⚠️ Сообщение PowerShell: {err_text}", "warn")

            stdout = (r.stdout or b"").decode("utf-8", errors="ignore")
            results = parse_batch_output(stdout, ordered, prefix="INTEL_STEP:")

            for k in ordered:
                ok, err = results.get(k, (False, "Unknown error"))
                tweak_label = INTEL_TWEAKS.get(k, {}).get("label", k)
                if ok:
                    success_count += 1
                    self.log_msg.emit(f"✓ {tweak_label}", "success")
                else:
                    self.log_msg.emit(f"✗ {tweak_label} (Ошибка: {err})", "error")

            self.progress.emit(100, 100)
            self.log_msg.emit(f"🎉 Применено {success_count} из {ordered_len} твиков Intel Arc!", "highlight")
        except Exception as e:
            self.log_msg.emit(f"💥 Критическая ошибка воркера: {e}", "error")
            # Только в случае аварийного прерывания скрипта подстраховываемся перезапуском служб
            try:
                svc_list = ", ".join(f"'{s}'" for s in INTEL_SVCS)
                run_ps(f"foreach($_s in @({svc_list})) {{ Start-Service $_s -EA SilentlyContinue }}", timeout=8)
            except Exception:
                pass
        finally:
            self.finished.emit(success_count, ordered_len)


class RevertWorker(QObject):
    progress = Signal(int, int)
    log_msg = Signal(str, str)
    finished = Signal(int, int)

    def __init__(self, keys_to_revert):
        super().__init__()
        self.keys = keys_to_revert

    @Slot()
    def run(self):
        success_count = 0
        ordered_len = len(self.keys)
        try:
            self.log_msg.emit("↺ Сброс настроек Intel Arc к заводским дефолтам...", "info")
            ps_code, ordered = build_intel_revert_batch_script(self.keys)
            ordered_len = len(ordered)
            self.progress.emit(20, 100)

            r = run_ps(ps_code, timeout=40)
            self.progress.emit(80, 100)

            if r.returncode != 0 and r.stderr:
                err_text = r.stderr.decode("utf-8", errors="ignore").strip()
                if err_text:
                    self.log_msg.emit(f"⚠️ Сообщение PowerShell: {err_text}", "warn")

            stdout = (r.stdout or b"").decode("utf-8", errors="ignore")
            results = parse_batch_output(stdout, ordered, prefix="INTEL_REVERT:")

            for k in ordered:
                ok, err = results.get(k, (False, "no result"))
                tweak_label = INTEL_TWEAKS.get(k, {}).get("label", k)
                if ok:
                    success_count += 1
                    self.log_msg.emit(f"✓ Сброшен: {tweak_label}", "success")
                else:
                    self.log_msg.emit(f"✗ Ошибка сброса: {tweak_label} ({err})", "error")

            self.progress.emit(100, 100)
            self.log_msg.emit(f"🏁 Заводские настройки Intel Arc восстановлены ({success_count}/{ordered_len})!", "highlight")
        except Exception as e:
            self.log_msg.emit(f"💥 Ошибка отката: {e}", "error")
            try:
                svc_list = ", ".join(f"'{s}'" for s in INTEL_SVCS)
                run_ps(f"foreach($_s in @({svc_list})) {{ Start-Service $_s -EA SilentlyContinue }}", timeout=8)
            except Exception:
                pass
        finally:
            self.finished.emit(success_count, ordered_len)


class ShaderCleanWorker(QObject):
    progress = Signal(int, int)
    log_msg = Signal(str, str)
    finished = Signal(int, int)

    def __init__(self, target_ids):
        super().__init__()
        self.target_ids = target_ids

    @Slot()
    def run(self):
        try:
            self.progress.emit(15, 100)
            self.log_msg.emit("🧹 Начало очистки кэша шейдеров...", "info")
            files, bytes_freed, logs = clean_caches(self.target_ids)
            self.progress.emit(85, 100)

            for l in logs:
                st = "success" if l.startswith("✓") else ("warn" if "⚠️" in l else "info")
                self.log_msg.emit(l, st)

            self.progress.emit(100, 100)
            self.finished.emit(files, bytes_freed)
        except Exception as e:
            self.log_msg.emit(f"💥 Ошибка при очистке шейдеров: {e}", "error")
            for s in INTEL_SVCS:
                try:
                    run_ps(f"if((Get-Service '{s}' -EA SilentlyContinue).Status -ne 'Running'){{ Start-Service '{s}' -EA SilentlyContinue }}", timeout=5)
                except Exception:
                    pass
            self.finished.emit(0, 0)


# ── Главное окно приложения ─────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Intel Arc GPU Optimizer & Shader Cleaner")
        self.resize(890, 690)
        self.setMinimumSize(830, 610)
        self.setStyleSheet(QSS_THEME)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.is_admin = False
        self.gpu_info = {}
        self.tweak_checks = {}
        self.shader_checks = {}

        self.init_thread = None
        self.init_worker = None
        self.active_thread = None
        self.active_worker = None
        self._rescan_thread = None
        self._rescan_worker = None
        self._close_pending = False

        # 1. Сначала строим весь UI (создаём self.console)
        self._setup_ui()
        # 2. Теперь безопасно проверяем админа и логируем
        self._check_admin()
        # 3. Запускаем асинхронную инициализацию оборудования
        self._start_async_init()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # 1. Шапка с информацией о видеокарте
        header_card = QFrame()
        header_card.setProperty("class", "HeaderCard")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 12, 16, 12)

        title_col = QVBoxLayout()
        app_title = QLabel("INTEL ARC GPU OPTIMIZER")
        app_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00c7fd;")
        app_sub = QLabel("Xe & Xe2 Battlemage Low-Latency Tuning")
        app_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_col.addWidget(app_title)
        title_col.addWidget(app_sub)
        h_layout.addLayout(title_col)

        h_layout.addStretch()

        # Карточка GPU
        gpu_box = QVBoxLayout()
        gpu_box.setAlignment(Qt.AlignRight)

        top_gpu_row = QHBoxLayout()
        self.gpu_name_lbl = QLabel("🎮 Определение оборудования...")
        self.gpu_name_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #ffffff;")
        self.btn_refresh_gpu = QPushButton("🔄")
        self.btn_refresh_gpu.setToolTip("Повторить сканирование оборудования")
        self.btn_refresh_gpu.setProperty("class", "SecondaryBtn")
        self.btn_refresh_gpu.setMaximumWidth(32)
        self.btn_refresh_gpu.clicked.connect(self._start_async_init)

        top_gpu_row.addWidget(self.gpu_name_lbl)
        top_gpu_row.addWidget(self.btn_refresh_gpu)
        gpu_box.addLayout(top_gpu_row)

        self.details_lbl = QLabel("Сканирование подключей дисплейного драйвера...")
        self.details_lbl.setStyleSheet("font-size: 11px; color: #38bdf8;")
        gpu_box.addWidget(self.details_lbl)

        h_layout.addLayout(gpu_box)
        root_layout.addWidget(header_card)

        # 2. Вкладки (Твики / Кэш шейдеров)
        self.tabs = QTabWidget()
        self.tab_tweaks = QWidget()
        self.tab_shaders = QWidget()

        self._build_tweaks_tab()
        self._build_shaders_tab()

        self.tabs.addTab(self.tab_tweaks, "⚡ Оптимизация Intel Arc")
        self.tabs.addTab(self.tab_shaders, "🧹 Очистка кэша шейдеров")
        root_layout.addWidget(self.tabs, stretch=1)

        # 3. Индикатор прогресса
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        root_layout.addWidget(self.progress_bar)

        # 4. Лог-консоль
        self.console = QTextEdit()
        self.console.setProperty("class", "Console")
        self.console.setReadOnly(True)
        self.console.document().setMaximumBlockCount(300)
        self.console.setMaximumHeight(130)
        root_layout.addWidget(self.console)

    # ── Вкладка 1: Твики Intel Arc ──────────────────────────────────────────
    def _build_tweaks_tab(self):
        layout = QVBoxLayout(self.tab_tweaks)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(10)

        action_bar = QHBoxLayout()

        self.btn_apply = QPushButton("🚀 Применить выбранное")
        self.btn_apply.setProperty("class", "AccentBtn")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        action_bar.addWidget(self.btn_apply)

        self.btn_revert = QPushButton("↺ Сбросить дефолты")
        self.btn_revert.setProperty("class", "DangerBtn")
        self.btn_revert.clicked.connect(self._on_revert_clicked)
        action_bar.addWidget(self.btn_revert)

        action_bar.addSpacing(16)
        action_bar.addStretch()

        btn_select_all = QPushButton("Все")
        btn_select_all.setProperty("class", "SecondaryBtn")
        btn_select_all.clicked.connect(lambda: self._set_all_tweaks(True))
        action_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Снять")
        btn_deselect_all.setProperty("class", "SecondaryBtn")
        btn_deselect_all.clicked.connect(lambda: self._set_all_tweaks(False))
        action_bar.addWidget(btn_deselect_all)

        layout.addLayout(action_bar)

        # Список карточек твиков со скроллом
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(8)

        for key, tweak in INTEL_TWEAKS.items():
            card = QFrame()
            card.setProperty("class", "Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)

            top_row = QHBoxLayout()
            chk = QCheckBox(tweak["label"])
            chk.setChecked(tweak.get("recommended", True))
            self.tweak_checks[key] = chk
            top_row.addWidget(chk)

            cat_badge = QLabel(f" {tweak.get('cat', 'GPU')} ")
            cat_badge.setStyleSheet(
                "background-color: #1e293b; color: #38bdf8; "
                "font-size: 11px; border-radius: 4px; padding: 2px 6px;"
            )
            top_row.addWidget(cat_badge)
            top_row.addStretch()

            desc_lbl = QLabel(tweak.get("desc", ""))
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; padding-left: 26px;")

            card_layout.addLayout(top_row)
            card_layout.addWidget(desc_lbl)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    # ── Вкладка 2: Кэш шейдеров ─────────────────────────────────────────────
    def _build_shaders_tab(self):
        layout = QVBoxLayout(self.tab_shaders)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        action_bar = QHBoxLayout()

        self.btn_clean_shaders = QPushButton("🧹 Очистить кэш шейдеров")
        self.btn_clean_shaders.setProperty("class", "AccentBtn")
        self.btn_clean_shaders.clicked.connect(self._on_clean_shaders_clicked)
        action_bar.addWidget(self.btn_clean_shaders)

        self.btn_rescan = QPushButton("🔄 Пересканировать")
        self.btn_rescan.setProperty("class", "SecondaryBtn")
        self.btn_rescan.clicked.connect(self._start_rescan_shaders)
        action_bar.addWidget(self.btn_rescan)

        action_bar.addStretch()

        self.lbl_total_cache = QLabel("Сканирование библиотек и дисков...")
        self.lbl_total_cache.setStyleSheet("font-size: 13px; font-weight: bold; color: #00c7fd;")
        action_bar.addWidget(self.lbl_total_cache)

        layout.addLayout(action_bar)

        self.shaders_container = QVBoxLayout()
        self.shaders_container.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content.setLayout(self.shaders_container)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

    # ── Асинхронная инициализация ────────────────────────────────────────────
    def _start_async_init(self):
        if self.init_thread and self.init_thread.isRunning():
            return

        self._set_ui_busy(True)
        self.init_thread = QThread()
        self.init_worker = InitWorker()
        self.init_worker.moveToThread(self.init_thread)

        self.init_worker.done.connect(self._on_init_completed)
        self.init_worker.done.connect(self.init_thread.quit)
        self.init_worker.done.connect(self.init_worker.deleteLater)
        self.init_thread.finished.connect(self.init_thread.deleteLater)

        def _cleanup_init():
            self.init_thread = None
            self.init_worker = None
            self._check_pending_close()
        self.init_thread.finished.connect(_cleanup_init)

        self.init_thread.started.connect(self.init_worker.run)
        self.init_thread.start()

    @Slot(dict, list)
    def _on_init_completed(self, gpu_info: dict, caches: list):
        self.gpu_info = gpu_info

        name = gpu_info.get("name", "Intel Graphics")
        drv_ver = gpu_info.get("driver_version", "Неизвестно")
        vram = gpu_info.get("vram_gb", 0.0)
        vram_str = f"{vram:.1f} GB" if vram else ""
        badge = "Xe2 Battlemage" if gpu_info.get("is_battlemage") else ("Xe-HPG Arc" if gpu_info.get("is_arc") else "Intel Graphics")
        reg_p = gpu_info.get("adapter_reg_path", "")
        reg_idx = reg_p.split("\\")[-1] if reg_p else "0000"

        # Формируем статус служб
        svcs = gpu_info.get("services", [])
        svcs_str = "активны" if any(s[1] == "Running" for s in svcs) else "не запущены"

        self.gpu_name_lbl.setText(f"🎮 {name}")
        self.details_lbl.setText(f"Архитектура: {badge}  |  Драйвер: {drv_ver}  |  VRAM: {vram_str}  |  Службы: {svcs_str}")

        if gpu_info.get("vendor") != "intel":
            self._log("⚠️ Видеокарта Intel Arc не обнаружена на этой системе!", "warn")
            self.btn_apply.setToolTip("Требуется видеокарта Intel Arc или процессор Intel")

        self._populate_shader_list(caches)
        self._set_ui_busy(False)
        self._log(f"Оборудование определено: {name} (VRAM: {vram_str})", "info")

    def _start_rescan_shaders(self):
        if self._rescan_thread and self._rescan_thread.isRunning():
            self._set_ui_busy(False)
            return

        self.lbl_total_cache.setText("Сканирование...")
        self._set_ui_busy(True)

        self._rescan_thread = QThread()
        self._rescan_worker = RescanWorker()
        self._rescan_worker.moveToThread(self._rescan_thread)

        self._rescan_worker.done.connect(self._populate_shader_list)
        self._rescan_worker.done.connect(self._rescan_thread.quit)
        self._rescan_worker.done.connect(self._rescan_worker.deleteLater)
        self._rescan_thread.finished.connect(self._rescan_thread.deleteLater)

        def _cleanup_rescan():
            self._rescan_thread = None
            self._rescan_worker = None
            self._set_ui_busy(False)
            self._check_pending_close()

        self._rescan_thread.finished.connect(_cleanup_rescan)
        self._rescan_thread.started.connect(self._rescan_worker.run)
        self._rescan_thread.start()

    @Slot(list)
    def _populate_shader_list(self, targets: list):
        if not targets:
            if self.shader_checks:
                self._log("⚠️ Не удалось обновить кэши, сохранён текущий список", "warn")
                return
            self.lbl_total_cache.setText("Кэши не обнаружены")
            return

        # Полное удаление всех предыдущих элементов и виджетов без утечки спейсеров
        while self.shaders_container.count():
            item = self.shaders_container.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self.shader_checks.clear()
        total_size = sum(t["size_bytes"] for t in targets)
        total_files = sum(t["file_count"] for t in targets)

        self.lbl_total_cache.setText(f"Общий кэш: {total_files} файлов ({format_bytes(total_size)})")

        for t in targets:
            card = QFrame()
            card.setProperty("class", "Card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(4)

            top_row = QHBoxLayout()
            chk = QCheckBox(f"{t['name']}")
            chk.setChecked(t["exists"] and t["file_count"] > 0)
            chk.setEnabled(t["exists"])
            self.shader_checks[t["id"]] = chk
            top_row.addWidget(chk)

            status_str = f"{t['file_count']} файлов  |  {t['size_formatted']}" if t["exists"] else "Не найдено"
            col = "#00c7fd" if (t["exists"] and t["file_count"] > 0) else "#64748b"
            size_lbl = QLabel(status_str)
            size_lbl.setStyleSheet(f"font-weight: bold; color: {col}; font-size: 12px;")
            top_row.addStretch()
            top_row.addWidget(size_lbl)

            card_layout.addLayout(top_row)

            path_lbl = QLabel(f"📁 {t['path']}")
            path_lbl.setStyleSheet("color: #64748b; font-size: 10px; font-family: monospace; padding-left: 26px;")
            desc_lbl = QLabel(t["desc"])
            desc_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; padding-left: 26px;")

            card_layout.addWidget(desc_lbl)
            card_layout.addWidget(path_lbl)
            self.shaders_container.addWidget(card)

        self.shaders_container.addStretch()

    # ── Логирование и события ────────────────────────────────────────────────
    @Slot(str, str)
    def _log(self, text: str, status: str = "info"):
        if not hasattr(self, "console") or self.console is None:
            return

        now = datetime.now().strftime("%H:%M:%S")
        color = "#e2e8f0"
        prefix = "•"
        if status == "success":
            color = "#10b981"
            prefix = "✔"
        elif status == "error":
            color = "#ef4444"
            prefix = "✖"
        elif status == "warn":
            color = "#f59e0b"
            prefix = "⚠"
        elif status == "highlight":
            color = "#00c7fd"
            prefix = "★"

        clean_text = html.escape(str(text))
        html_line = f'<span style="color:#64748b;">[{now}]</span> <b style="color:{color};">{prefix} {clean_text}</b>'
        self.console.append(html_line)

    def _set_all_tweaks(self, state: bool):
        for chk in self.tweak_checks.values():
            chk.setChecked(state)

    def _set_ui_busy(self, busy: bool):
        can_apply = (not busy) and (self.gpu_info.get("vendor") == "intel") and self.is_admin
        self.btn_apply.setEnabled(can_apply)
        self.btn_revert.setEnabled((not busy) and self.is_admin)
        self.btn_clean_shaders.setEnabled(not busy)
        if hasattr(self, "btn_rescan"):
            self.btn_rescan.setEnabled(not busy)
        if hasattr(self, "btn_refresh_gpu"):
            self.btn_refresh_gpu.setEnabled(not busy)

        if busy:
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(True)
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setTextVisible(False)

    # ── Вызов действий ───────────────────────────────────────────────────────
    def _on_apply_clicked(self):
        if self.active_thread and self.active_thread.isRunning():
            return

        if not self.is_admin:
            QMessageBox.warning(self, "Требуются права администратора", "Для записи параметров в реестр HKLM запустите программу от имени Администратора.")
            return

        keys = [k for k, chk in self.tweak_checks.items() if chk.isChecked()]
        if not keys:
            QMessageBox.warning(self, "Внимание", "Не выбрано ни одного твика для применения.")
            return

        self._set_ui_busy(True)
        self.active_thread = QThread()
        self.active_worker = ApplyWorker(keys)
        self.active_worker.moveToThread(self.active_thread)

        self.active_worker.progress.connect(self.progress_bar.setValue)
        self.active_worker.log_msg.connect(self._log)
        self.active_worker.finished.connect(self._on_apply_completed)
        self.active_worker.finished.connect(self.active_thread.quit)
        self.active_worker.finished.connect(self.active_worker.deleteLater)
        self.active_thread.finished.connect(self.active_thread.deleteLater)

        def _cleanup_apply():
            self.active_thread = None
            self.active_worker = None
            self._set_ui_busy(False)
            self._check_pending_close()
        self.active_thread.finished.connect(_cleanup_apply)

        self.active_thread.started.connect(self.active_worker.run)
        self.active_thread.start()

    @Slot(int, int)
    def _on_apply_completed(self, success_cnt: int, total_cnt: int):
        if success_cnt > 0:
            QMessageBox.information(
                self, "Оптимизация завершена",
                f"Успешно применено {success_cnt} из {total_cnt} параметров Intel Arc!\n\n"
                "💡 Чтобы настройки вступили в силу прямо сейчас без перезагрузки:\n"
                "• Нажмите сочетание клавиш Win + Ctrl + Shift + B (перезапуск видеодрайвера);\n"
                "• Либо перезагрузите компьютер в удобное время."
            )
        else:
            QMessageBox.warning(
                self, "Ошибка применения",
                "Не удалось применить выбранные параметры. Проверьте права администратора и журнал консоли."
            )

    def _on_revert_clicked(self):
        if self.active_thread and self.active_thread.isRunning():
            return

        if not self.is_admin:
            QMessageBox.warning(self, "Требуются права администратора", "Для сброса параметров в реестре HKLM запустите программу от имени Администратора.")
            return

        res = QMessageBox.question(
            self, "Подтверждение",
            "Вы уверены, что хотите сбросить все параметры Intel Arc к заводским дефолтам?",
            QMessageBox.Yes | QMessageBox.No
        )
        if res != QMessageBox.Yes:
            return

        keys = list(INTEL_TWEAKS.keys())
        self._set_ui_busy(True)
        self.active_thread = QThread()
        self.active_worker = RevertWorker(keys)
        self.active_worker.moveToThread(self.active_thread)

        self.active_worker.progress.connect(self.progress_bar.setValue)
        self.active_worker.log_msg.connect(self._log)
        self.active_worker.finished.connect(self._on_revert_completed)
        self.active_worker.finished.connect(self.active_thread.quit)
        self.active_worker.finished.connect(self.active_worker.deleteLater)
        self.active_thread.finished.connect(self.active_thread.deleteLater)

        def _cleanup_revert():
            self.active_thread = None
            self.active_worker = None
            self._set_ui_busy(False)
            self._check_pending_close()
        self.active_thread.finished.connect(_cleanup_revert)

        self.active_thread.started.connect(self.active_worker.run)
        self.active_thread.start()

    @Slot(int, int)
    def _on_revert_completed(self, success_cnt: int, total_cnt: int):
        if success_cnt > 0:
            QMessageBox.information(
                self, "Дефолты восстановлены",
                f"Заводские параметры Intel Arc успешно восстановлены ({success_cnt}/{total_cnt})!\n\n"
                "💡 Рекомендуется нажать Win + Ctrl + Shift + B или перезагрузить компьютер."
            )
        else:
            QMessageBox.warning(
                self, "Ошибка отката",
                "Не удалось сбросить параметры. Проверьте журнал консоли."
            )

    def _on_clean_shaders_clicked(self):
        if self.active_thread and self.active_thread.isRunning():
            return

        selected_ids = [t_id for t_id, chk in self.shader_checks.items() if chk.isChecked()]
        if not selected_ids:
            QMessageBox.warning(self, "Внимание", "Выберите хотя бы одну локацию кэша шейдеров.")
            return

        self._set_ui_busy(True)
        self.active_thread = QThread()
        self.active_worker = ShaderCleanWorker(selected_ids)
        self.active_worker.moveToThread(self.active_thread)

        self.active_worker.progress.connect(self.progress_bar.setValue)
        self.active_worker.log_msg.connect(self._log)
        self.active_worker.finished.connect(self._on_shader_clean_finished)
        self.active_worker.finished.connect(self.active_thread.quit)
        self.active_worker.finished.connect(self.active_worker.deleteLater)
        self.active_thread.finished.connect(self.active_thread.deleteLater)

        def _cleanup_clean():
            self.active_thread = None
            self.active_worker = None
            self._check_pending_close()
        self.active_thread.finished.connect(_cleanup_clean)

        self.active_thread.started.connect(self.active_worker.run)
        self.active_thread.start()

    def _on_shader_clean_finished(self, files_cnt: int, bytes_cnt: int):
        self._start_rescan_shaders()
        self._log(f"🧹 Очистка завершена: удалено {files_cnt} файлов ({format_bytes(bytes_cnt)})", "highlight")
        QMessageBox.information(
            self, "Готово",
            f"Кэш шейдеров успешно очищен!\n\nУдалено файлов: {files_cnt}\nОсвобождено места: {format_bytes(bytes_cnt)}"
        )

    def _check_admin(self):
        try:
            self.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            self.is_admin = False

        if not self.is_admin:
            self._log("⚠️ ВНИМАНИЕ: Программа запущена без прав администратора!", "warn")
            self._log("Для записи параметров в реестр HKLM запустите файл run.bat от имени Администратора.", "warn")

    def _check_pending_close(self):
        if getattr(self, "_close_pending", False):
            running = [
                t for t in (getattr(self, "init_thread", None),
                            getattr(self, "active_thread", None),
                            getattr(self, "_rescan_thread", None))
                if t is not None and t.isRunning()
            ]
            if not running:
                QApplication.quit()

    def closeEvent(self, event):
        running = [
            t for t in (getattr(self, "init_thread", None),
                        getattr(self, "active_thread", None),
                        getattr(self, "_rescan_thread", None))
            if t is not None and t.isRunning()
        ]
        if running:
            event.ignore()
            self.hide()
            self._close_pending = True
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
