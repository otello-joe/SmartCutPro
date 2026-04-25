import os
import shutil
import subprocess
import threading
import concurrent.futures
import cv2
import urllib.parse
import warnings
import pygame
import re
import logging
import gc
from queue import Queue
from PIL import Image, ImageOps
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import DND_FILES, TkinterDnD

# 忽略不必要的警告
warnings.filterwarnings("ignore", message=".*Given image is not CTKImage.*")

from core.config_mgr import cfg, LOG_FILE
from core.logic import (
    split_by_scene_changes,
    crop_split_screen,
    add_watermark_only,
    get_dynamic_outdir,
    archive_original_file,
    setup_ffmpeg_env
)

# --- 自定义日志处理器：将 logging 模块的输出实时推送到 UI 文本框 ---
class UITextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
    def emit(self, record):
        msg = self.format(record)
        # 使用 after 确保在主线程更新 UI
        self.text_widget.after(0, self._append_text, msg)

    def _append_text(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

# --- Linux 系统级通知 ---
def send_linux_notification(title, message):
    if os.name != 'nt':
        try:
            subprocess.run(['notify-send', title, message], check=False)
        except: pass

class MainWindow(TkinterDnD.Tk):
    def __init__(self, temp_dir):
        super().__init__()
        self.temp_dir = temp_dir

        # 1. 基础数据初始化
        self.theme_mode = cfg.get("theme", "Light")
        self.archive_var = tk.BooleanVar(value=cfg.get("auto_archive", True))
        self.mode_var = tk.IntVar(value=cfg.get("default_mode", 1))

        self.selected_files = []
        self.file_ui_elements = {}
        self.file_vars = {}
        self.processing_files = set()
        self.stop_events = {}
        self.last_clicked_index = -1
        self.wm_img_ref = None
        self.last_out_dir = ""
        self.task_queue = Queue()

        self.current_wm_path = cfg.get("last_watermark", "")
        self.current_bgm_path = cfg.get("last_bgm", "")

        # 2. 纯白工业级外观
        ctk.set_appearance_mode(self.theme_mode)
        self.bg_col = ("#FFFFFF", "#121212")
        self.list_bg = ("#FFFFFF", "#1A1A1A")
        self.card_col = ("#FFFFFF", "#242424")
        self.border_col = ("#EEEEEE", "#2D2D2D")

        try: pygame.mixer.init()
        except: pass
        self.is_playing_bgm = False

        self.title("SmartCut Pro - V62 Pro+ (Pure White Edition)")

        # --- 【布局记忆：加载窗口大小和位置】 ---
        w = cfg.get("win_width", 1150)
        h = cfg.get("win_height", 880)
        x = cfg.get("win_x", 100)
        y = cfg.get("win_y", 100)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(650, 450)

        # 拦截关闭事件以保存布局
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 3. 构建布局
        self._build_ui()
        self._init_dnd_logic()
        self._restore_settings()
        self._apply_root_theme()

    def _apply_root_theme(self):
        mode = ctk.get_appearance_mode()
        color = self.bg_col[0] if mode == "Light" else self.bg_col[1]
        self.configure(bg=color)
        try: self.main_pane.configure(bg=color)
        except: pass

    def _build_ui(self):
        # 主窗格
        self.main_pane = tk.PanedWindow(self, orient="horizontal", sashwidth=1, bd=0, relief="flat")
        self.main_pane.pack(fill="both", expand=True)

        # --- 左侧区域 ---
        self.left_wrapper = ctk.CTkFrame(self.main_pane, fg_color=self.bg_col, corner_radius=0)
        self.left_wrapper.grid_columnconfigure(0, weight=1)
        self.left_wrapper.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.left_wrapper, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        ctk.CTkLabel(header, text="任务指挥中心", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        btn_group = ctk.CTkFrame(header, fg_color="transparent"); btn_group.pack(side="right")
        ctk.CTkButton(btn_group, text="全选", width=35, height=26, fg_color="#34495e", command=self.select_all).pack(side="left", padx=2)
        ctk.CTkButton(btn_group, text="反选", width=35, height=26, fg_color="#7f8c8d", command=self.toggle_selection).pack(side="left", padx=2)
        ctk.CTkButton(btn_group, text="+ 导入", width=60, height=26, command=self.browse_files).pack(side="left", padx=4)
        ctk.CTkButton(btn_group, text="清空", width=50, height=26, fg_color="#FF5252", command=self.clear_files).pack(side="left", padx=2)

        self.scroll_list = ctk.CTkScrollableFrame(self.left_wrapper, fg_color=self.list_bg, corner_radius=8, border_width=1, border_color=self.border_col)
        self.scroll_list.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        self.placeholder = ctk.CTkLabel(self.scroll_list, text="拖拽视频至此处", text_color="#BDBDBD", font=ctk.CTkFont(size=13)); self.placeholder.pack(expand=True, pady=100)
        self.info_label = ctk.CTkLabel(self.left_wrapper, text="准备就绪", text_color="#888888", font=ctk.CTkFont(size=11), anchor="w"); self.info_label.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.main_pane.add(self.left_wrapper, stretch="always")

        # --- 右侧区域 (彻底解决布局冲突与属性错误) ---
        self.right_wrapper = ctk.CTkFrame(self.main_pane, fg_color=self.bg_col, corner_radius=0)
        self.right_wrapper.grid_columnconfigure(0, weight=1)
        self.right_wrapper.grid_rowconfigure(0, weight=1)
        self.right_wrapper.grid_rowconfigure(1, weight=0)

        # 1. 上部分：Tabview (设置固定高度以激活内部滚动条)
        self.tabs = ctk.CTkTabview(
            self.right_wrapper,
            fg_color=self.bg_col,
            segmented_button_selected_color="#0D6EFD",
            height=550
        )
        self.tabs.grid(row=0, column=0, sticky="nsew", padx=8, pady=5)

        tab_p = self.tabs.add("处理配置")
        tab_s = self.tabs.add("系统设置")
        tab_p.configure(fg_color=self.bg_col); tab_s.configure(fg_color=self.bg_col)

        self._build_process_tab(tab_p)
        self._build_settings_tab(tab_s)

        # 2. 下部分：日志窗口
        log_f = ctk.CTkFrame(self.right_wrapper, fg_color="transparent")
        log_f.grid(row=1, column=0, sticky="ew", padx=15, pady=(10, 15))
        ctk.CTkLabel(log_f, text="运行日志", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w")
        self.log_box = ctk.CTkTextbox(log_f, height=150, fg_color="#F9F9F9", text_color="#666666",
                                      font=ctk.CTkFont(family="Consolas", size=11), border_width=1, border_color=self.border_col, state="disabled")
        self.log_box.pack(fill="x", pady=5)

        handler = UITextHandler(self.log_box)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        # --- 【关键点：在 right_wrapper 完全定义后再添加到主窗格】 ---
        saved_pane_width = cfg.get("pane_width", 310)
        self.main_pane.add(self.right_wrapper, width=saved_pane_width, stretch="never")

        self._setup_scrolling_logic(self.scroll_list)

    def _build_process_tab(self, parent):
        scroll_p = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll_p.pack(fill="both", expand=True)

        p = 12
        ctk.CTkLabel(scroll_p, text="模式选择", font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w", padx=p, pady=(5, 2))
        self.mode_switch = ctk.CTkSegmentedButton(scroll_p, values=["智能分割", "分屏裁切", "合成成品"], command=self._on_mode_change); self.mode_switch.pack(fill="x", padx=p, pady=2); self.mode_switch.set("智能分割")

        ctk.CTkLabel(scroll_p, text="资源管理", font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w", padx=p, pady=(10, 2))
        wm_row = ctk.CTkFrame(scroll_p, fg_color="transparent"); wm_row.pack(fill="x", padx=p, pady=1)
        self.wm_btn = ctk.CTkButton(wm_row, text="🖼️ 水印图", height=28, command=self.browse_watermark); self.wm_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(wm_row, text="×", width=28, height=28, fg_color="#E74C3C", command=self.clear_watermark).pack(side="right")
        bgm_row = ctk.CTkFrame(scroll_p, fg_color="transparent"); bgm_row.pack(fill="x", padx=p, pady=1)
        self.bgm_btn = ctk.CTkButton(bgm_row, text="🎵 背景音乐", height=28, command=self.browse_bgm); self.bgm_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkButton(bgm_row, text="×", width=28, height=28, fg_color="#E74C3C", command=self.clear_bgm).pack(side="right")

        self.preview_card = ctk.CTkFrame(scroll_p, fg_color=self.card_col, corner_radius=8, border_width=1, border_color=self.border_col); self.preview_card.pack(fill="x", padx=p, pady=8)
        ctk.CTkLabel(self.preview_card, text="资源预览", font=ctk.CTkFont(size=11, weight="bold")).pack(pady=2)
        self.wm_preview_box = ctk.CTkLabel(self.preview_card, text="无水印预览", text_color="#999999", font=ctk.CTkFont(size=10), height=110); self.wm_preview_box.pack(pady=2, fill="x")
        bgm_f = ctk.CTkFrame(self.preview_card, fg_color="transparent"); bgm_f.pack(fill="x", padx=8, pady=5); bgm_f.grid_columnconfigure(0, weight=1)
        self.bgm_preview_label = ctk.CTkLabel(bgm_f, text="无音频预览", text_color="#888888", font=ctk.CTkFont(size=10), anchor="w"); self.bgm_preview_label.grid(row=0, column=0, sticky="ew")
        self.audio_btn = ctk.CTkButton(bgm_f, text="▶ 试听", width=55, height=24, font=ctk.CTkFont(size=10), command=self.toggle_bgm_preview); self.audio_btn.grid(row=0, column=1, sticky="e")

        speed_f = ctk.CTkFrame(scroll_p, fg_color="transparent"); speed_f.pack(fill="x", padx=p, pady=(10, 0))
        ctk.CTkLabel(speed_f, text="视频变速", font=ctk.CTkFont(size=11)).pack(side="left")
        self.speed_entry = ctk.CTkEntry(speed_f, width=60, height=24, font=ctk.CTkFont(size=11), justify="center", fg_color=self.card_col, border_color=self.border_col)
        self.speed_entry.pack(side="right", padx=(10, 0)); self.speed_entry.insert(0, "1.00"); self.speed_entry.bind("<Return>", self._on_speed_entry_confirm)
        self.speed_slider = ctk.CTkSlider(scroll_p, from_=0.5, to=2.0, height=16, command=self._on_speed_slide); self.speed_slider.pack(fill="x", padx=p, pady=2); self.speed_slider.set(1.0)

        ctk.CTkLabel(scroll_p, text="音量调节", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=p, pady=(10, 0))
        vol_f = ctk.CTkFrame(scroll_p, fg_color="transparent"); vol_f.pack(fill="x", padx=p)
        self.vol_slider = ctk.CTkSlider(vol_f, from_=0, to=1.5, height=16, command=self._on_vol_slide); self.vol_slider.pack(side="left", fill="x", expand=True)
        self.vol_entry = ctk.CTkEntry(vol_f, width=50, height=24, font=ctk.CTkFont(size=11), justify="center", fg_color=self.card_col, border_color=self.border_col)
        self.vol_entry.pack(side="right", padx=(10, 0)); self.vol_entry.insert(0, "0.20"); self.vol_entry.bind("<Return>", self._on_vol_entry_confirm)

        self.start_btn = ctk.CTkButton(scroll_p, text="🚀 开启生产", height=45, font=ctk.CTkFont(size=15, weight="bold"), command=self.start_processing); self.start_btn.pack(fill="x", padx=p, pady=15)
        self.open_btn = ctk.CTkButton(scroll_p, text="📂 浏览输出", height=32, fg_color=("#F0F0F0", "#333333"), text_color=("#333333", "#FFFFFF"), font=ctk.CTkFont(size=12), state="disabled", command=self.open_last_dir); self.open_btn.pack(fill="x", padx=p, pady=(0, 15))

    def _build_settings_tab(self, parent):
        scroll_s = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        scroll_s.pack(fill="both", expand=True)
        p = 15
        ctk.CTkLabel(scroll_s, text="界面主题", font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w", padx=p, pady=(10, 2))
        self.theme_menu = ctk.CTkOptionMenu(scroll_s, values=["Light", "Dark"], height=26, command=self.change_theme); self.theme_menu.pack(fill="x", padx=p); self.theme_menu.set(self.theme_mode)
        ctk.CTkLabel(scroll_s, text="FFmpeg 路径", font=ctk.CTkFont(weight="bold", size=12)).pack(anchor="w", padx=p, pady=(15, 2))
        self.ff_entry = ctk.CTkEntry(scroll_s, height=26, font=ctk.CTkFont(size=11), fg_color=self.card_col, border_color=self.border_col); self.ff_entry.pack(fill="x", padx=p, pady=2); self.ff_entry.insert(0, cfg.get("ffmpeg_path", ""))
        ctk.CTkButton(scroll_s, text="💾 保存路径", height=26, command=self.save_settings).pack(padx=p, pady=5)
        ctk.CTkSwitch(scroll_s, text="完成后自动归档原片", font=ctk.CTkFont(size=12), variable=self.archive_var).pack(anchor="w", padx=p, pady=20)

    def _update_previews(self):
        self.wm_preview_box.configure(image="", text="无水印预览")
        if hasattr(self.wm_preview_box, "_image_holder"): del self.wm_preview_box._image_holder
        self.wm_img_ref = None; self.update()
        if self.current_wm_path and os.path.exists(self.current_wm_path):
            try:
                def render():
                    if not self.current_wm_path: return
                    try:
                        raw = Image.open(self.current_wm_path).convert("RGBA")
                        raw = ImageOps.contain(raw, (220, 100))
                        self.wm_img_ref = ctk.CTkImage(light_image=raw, dark_image=raw, size=(raw.width, raw.height))
                        self.wm_preview_box.configure(image=self.wm_img_ref, text="")
                        self.wm_preview_box._image_holder = self.wm_img_ref
                    except: pass
                self.after(10, render)
            except: self.wm_preview_box.configure(text="❌ 水印加载失败")
        if self.current_bgm_path and os.path.exists(self.current_bgm_path):
            self.bgm_preview_label.configure(text=f"🎵 {os.path.basename(self.current_bgm_path)[:22]}...", text_color="#0D6EFD")
        else: self.bgm_preview_label.configure(text="无音频预览", text_color="#888888")

    def clear_watermark(self):
        self.current_wm_path = ""; cfg.set("last_watermark", "")
        self.wm_preview_box.configure(image="", text="无水印预览"); self._update_previews()

    def select_all(self):
        for var in self.file_vars.values(): var.set(True)
    def toggle_selection(self):
        for var in self.file_vars.values(): var.set(not var.get())
    def _handle_click(self, event, fp):
        current_idx = self.selected_files.index(fp)
        if event.state & 0x0001 and self.last_clicked_index != -1:
            start, end = min(self.last_clicked_index, current_idx), max(self.last_clicked_index, current_idx)
            target_state = self.file_vars[fp].get()
            for i in range(start, end + 1): self.file_vars[self.selected_files[i]].set(target_state)
        self.last_clicked_index = current_idx

    def start_processing(self):
        to_process = [f for f in self.selected_files if self.file_vars[f].get() and f not in self.processing_files]
        if not to_process: return
        try:
            target_dir = os.path.dirname(to_process[0])
            _, _, free = shutil.disk_usage(target_dir)
            if free < 1024 * 1024 * 1024:
                if not messagebox.askyesno("空间警告", "磁盘剩余空间不足 1GB，可能会导致渲染失败。是否继续？"): return
        except: pass

        concurrency = int(cfg.get("concurrency", 2))
        if concurrency <= 0: concurrency = max(1, os.cpu_count() // 2)
        snapshot = {"mode": self.mode_var.get(), "wm": self.current_wm_path, "bgm": self.current_bgm_path, "vol": self.vol_slider.get(), "speed": self.speed_slider.get(), "codec": "libx264"}

        for f in to_process:
            self.processing_files.add(f); self.file_vars[f].set(False); self.task_queue.put((f, snapshot))

        for _ in range(concurrency):
            threading.Thread(target=self._queue_worker, daemon=True).start()

    def _queue_worker(self):
        while not self.task_queue.empty():
            try:
                fp, params = self.task_queue.get_nowait()
                self._worker(fp, params)
                self.task_queue.task_done()
            except: break
        if self.task_queue.empty():
            self.after(0, self._finalize_processing)

    def _finalize_processing(self):
        self.open_btn.configure(state="normal")
        self.info_label.configure(text="✅ 队列任务处理完毕")
        send_linux_notification("SmartCut Pro", "所有视频处理任务已完成！🚀")

    def _worker(self, fp, p):
        try:
            self.last_out_dir = get_dynamic_outdir(fp)
            pcb, scb = lambda v: self.update_progress(fp, v), lambda t, c=None: self.update_status(fp, t, c)
            scb("处理中", "#0D6EFD")
            res = {}
            if p["mode"] == 1: res = split_by_scene_changes(fp, self.stop_events[fp], pcb, scb, self.temp_dir, **p)
            elif p["mode"] == 2: res = crop_split_screen(fp, self.stop_events[fp], pcb, scb, self.temp_dir, **p)
            elif p["mode"] == 3: res = add_watermark_only(fp, self.stop_events[fp], pcb, scb, self.temp_dir, **p)
            if res and res.get("status") == "Success":
                self.update_status(fp, "成功", "#198754")
                if self.archive_var.get(): archive_original_file(fp); self.after(2000, lambda: self._remove_task(fp, self.file_ui_elements[fp]["frame"]))
            else: self.update_status(fp, "跳过", "#f39c12")
        except Exception as e:
            logging.error(f"处理 {fp} 失败: {e}"); self.update_status(fp, "失败", "#e74c3c")
        finally:
            if fp in self.processing_files: self.processing_files.remove(fp)
            gc.collect()

    def update_status(self, fp, txt, col=None):
        if fp in self.file_ui_elements:
            if col: self.after(0, lambda: self.file_ui_elements[fp]["status"].configure(text=txt, text_color=col))
            else: self.after(0, lambda: self.file_ui_elements[fp]["status"].configure(text=txt))
    def update_progress(self, fp, val):
        if fp in self.file_ui_elements: self.after(0, lambda: self.file_ui_elements[fp]["bar"].set(val/100))
    def _add_file_to_ui(self, fp):
        if self.placeholder: self.placeholder.destroy(); self.placeholder = None
        item = ctk.CTkFrame(self.scroll_list, height=60, fg_color=self.card_col, corner_radius=6, border_width=1, border_color=self.border_col)
        item.pack(side="top", fill="x", pady=2, padx=5); item.grid_columnconfigure(2, weight=1)
        var = tk.BooleanVar(value=True); self.file_vars[fp] = var
        chk = ctk.CTkCheckBox(item, text="", variable=var, width=20); chk.grid(row=0, column=0, padx=(8, 2))
        item.bind("<Button-1>", lambda e: self._handle_click(e, fp)); chk.bind("<Button-1>", lambda e: self._handle_click(e, fp))
        try:
            cap = cv2.VideoCapture(fp); cap.set(cv2.CAP_PROP_POS_MSEC, 500); ret, frame = cap.read(); cap.release()
            if ret:
                img = ImageOps.fit(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), (70, 40), Image.Resampling.LANCZOS)
                thumb = ctk.CTkLabel(item, text="", image=ctk.CTkImage(img, size=(70, 40))); thumb.grid(row=0, column=1, padx=5, pady=8)
                thumb.bind("<Button-1>", lambda e: self._handle_click(e, fp))
            else: ctk.CTkLabel(item, text="🎬", width=70).grid(row=0, column=1, padx=5)
        except: ctk.CTkLabel(item, text="🎬", width=70).grid(row=0, column=1, padx=5)
        info_f = ctk.CTkFrame(item, fg_color="transparent"); info_f.grid(row=0, column=2, sticky="ew", padx=8)
        fname = os.path.basename(fp); display_name = fname if len(fname) < 45 else fname[:20] + "..." + fname[-20:]
        ctk.CTkLabel(info_f, text=display_name, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(side="top", fill="x")
        pb = ctk.CTkProgressBar(info_f, height=5, progress_color="#0D6EFD"); pb.pack(side="top", fill="x", pady=(2, 0)); pb.set(0)
        st = ctk.CTkLabel(item, text="就绪", font=ctk.CTkFont(size=11), text_color="#888888", width=60); st.grid(row=0, column=3, padx=10)
        self.stop_events[fp] = threading.Event()
        ctk.CTkButton(item, text="×", width=22, height=22, fg_color="transparent", text_color="#bdc3c7", command=lambda f=fp, w=item: self._remove_task(f, w)).grid(row=0, column=4, padx=(0, 8))
        self.file_ui_elements[fp] = {"frame": item, "status": st, "bar": pb}
        self._apply_scroll_to_new_item(item)

    def _setup_scrolling_logic(self, scroll_frame):
        canvas = scroll_frame._parent_canvas
        def _on_mw(e):
            if e.num == 4: canvas.yview_scroll(-1, "units")
            elif e.num == 5: canvas.yview_scroll(1, "units")
            else: canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        def bind_r(w):
            w.bind("<Button-4>", _on_mw, add="+"); w.bind("<Button-5>", _on_mw, add="+"); w.bind("<MouseWheel>", _on_mw, add="+")
            for c in w.winfo_children(): bind_r(c)
        bind_r(scroll_frame)
        canvas.bind("<Button-2>", lambda e: canvas.scan_mark(canvas.canvasx(e.x), canvas.canvasy(e.y)))
        canvas.bind("<B2-Motion>", lambda e: canvas.scan_dragto(canvas.canvasx(e.x), canvas.canvasy(e.y), gain=1))
    def _apply_scroll_to_new_item(self, item): self._setup_scrolling_logic(self.scroll_list)
    def toggle_bgm_preview(self):
        if not self.current_bgm_path: return
        if self.is_playing_bgm: pygame.mixer.music.stop(); self.audio_btn.configure(text="▶ 试听"); self.is_playing_bgm = False
        else:
            try:
                pygame.mixer.music.load(self.current_bgm_path); pygame.mixer.music.set_volume(self.vol_slider.get()); pygame.mixer.music.play(); self.audio_btn.configure(text="■ 停止"); self.is_playing_bgm = True
            except: pass
    def change_theme(self, new_theme): ctk.set_appearance_mode(new_theme); cfg.set("theme", new_theme); self.after(50, self._apply_root_theme)
    def _restore_settings(self): self._update_previews()
    def save_settings(self): cfg.set("ffmpeg_path", self.ff_entry.get().strip()); setup_ffmpeg_env(); messagebox.showinfo("成功", "保存成功")
    def browse_watermark(self):
        f = self._ask_file_via_dolphin("选择水印", "图片", ["*.png", "*.jpg"])
        if f: self.current_wm_path = f; cfg.set("last_watermark", f); self._update_previews()
    def clear_bgm(self): self.current_bgm_path = ""; cfg.set("last_bgm", ""); self._update_previews()
    def browse_bgm(self):
        f = self._ask_file_via_dolphin("选择音乐", "音频", ["*.mp3", "*.wav", "*.m4a"])
        if f: self.current_bgm_path = f; cfg.set("last_bgm", f); self._update_previews()
    def browse_files(self):
        f_list = self._ask_file_via_dolphin("选择视频", "视频", ["*.mp4", "*.mov", "*.mkv"], multiple=True)
        if f_list:
            for f in f_list:
                if f not in self.selected_files: self.selected_files.append(f); self._add_file_to_ui(f)
            self._check_empty_state()
    def _remove_task(self, f, w):
        if f in self.selected_files: self.selected_files.remove(f)
        if f in self.processing_files: self.processing_files.remove(f)
        w.destroy(); self._check_empty_state()
    def clear_files(self):
        for w in self.scroll_list.winfo_children(): w.destroy()
        self.selected_files.clear(); self.file_ui_elements.clear(); self.processing_files.clear(); self.placeholder = None; self._check_empty_state()
    def open_last_dir(self):
        if self.last_out_dir:
            try: subprocess.run(['xdg-open', self.last_out_dir] if os.name != 'nt' else ['explorer', self.last_out_dir])
            except: pass
    def _check_empty_state(self):
        if not self.selected_files and not self.placeholder:
            self.placeholder = ctk.CTkLabel(self.scroll_list, text="拖拽视频至此处", text_color="#BDBDBD"); self.placeholder.pack(expand=True, pady=180)
    def _init_dnd_logic(self):
        try:
            self.drop_target_register(DND_FILES); self.dnd_bind('<<Drop>>', self._handle_drop)
            self.dnd_bind('<<DragEnter>>', self._on_drag_enter)
            self.dnd_bind('<<DragLeave>>', self._on_drag_leave)
        except: pass
    def _on_drag_enter(self, event):
        self.placeholder.configure(text="🚀 松开鼠标开始导入视频", text_color="#0D6EFD")
        self.scroll_list.configure(border_color="#0D6EFD")
    def _on_drag_leave(self, event):
        self.placeholder.configure(text="拖拽视频至此处", text_color="#BDBDBD")
        self.scroll_list.configure(border_color=self.border_col)
    def _handle_drop(self, event):
        try:
            files = self.tk.splitlist(event.data)
            for f in files:
                clean_f = urllib.parse.unquote(f.strip().replace('file://', ''))
                if os.path.isfile(clean_f) and clean_f.lower().endswith(('.mp4', '.mov', '.mkv')):
                    if clean_f not in self.selected_files: self.selected_files.append(clean_f); self._add_file_to_ui(clean_f)
            self.update_idletasks(); self._check_empty_state()
        except: pass
    def _ask_file_via_dolphin(self, title, filter_label, ext_list, multiple=False):
        if os.name != 'nt':
            kdialog = shutil.which("kdialog")
            if kdialog:
                cmd = [kdialog, "--title", title, "--getopenfilename", os.getcwd(), f"{filter_label} ({' '.join(ext_list)})"]
                if multiple: cmd.insert(3, "--multiple"); cmd.insert(4, "--separate-output")
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0 or not res.stdout.strip(): return None
                return res.stdout.strip().split('\n') if multiple else res.stdout.strip()
        return filedialog.askopenfilenames(title=title) if multiple else filedialog.askopenfilename(title=title)
    def _on_mode_change(self, val): self.mode_var.set({"智能分割": 1, "分屏裁切": 2, "合成成品": 3}[val])

    def _on_speed_slide(self, val):
        stepped_val = round(val * 20) / 20
        self.speed_slider.set(stepped_val)
        self.speed_entry.delete(0, tk.END)
        self.speed_entry.insert(0, f"{stepped_val:.2f}")

    def _on_speed_entry_confirm(self, event):
        try:
            val = float(self.speed_entry.get())
            val = max(0.5, min(2.0, val))
            self.speed_slider.set(val)
            self.speed_entry.delete(0, tk.END)
            self.speed_entry.insert(0, f"{val:.2f}")
        except ValueError:
            self.speed_entry.delete(0, tk.END)
            self.speed_entry.insert(0, f"{self.speed_slider.get():.2f}")

    def _on_vol_slide(self, val):
        stepped_val = round(val * 20) / 20
        self.vol_slider.set(stepped_val)
        self.vol_entry.delete(0, tk.END)
        self.vol_entry.insert(0, f"{stepped_val:.2f}")
        if self.is_playing_bgm:
            try: pygame.mixer.music.set_volume(stepped_val)
            except: pass

    def _on_vol_entry_confirm(self, event):
        try:
            val = float(self.vol_entry.get())
            val = max(0.0, min(1.5, val))
            self.vol_slider.set(val)
            self.vol_entry.delete(0, tk.END)
            self.vol_entry.insert(0, f"{val:.2f}")
            if self.is_playing_bgm:
                try: pygame.mixer.music.set_volume(val)
                except: pass
        except ValueError:
            self.vol_entry.delete(0, tk.END)
            self.vol_entry.insert(0, f"{self.vol_slider.get():.2f}")

    def on_closing(self):
        """保存窗口状态至配置文件"""
        try:
            cfg.set("win_width", self.winfo_width())
            cfg.set("win_height", self.winfo_height())
            cfg.set("win_x", self.winfo_x())
            cfg.set("win_y", self.winfo_y())
            cfg.set("pane_width", self.right_wrapper.winfo_width())
        except: pass
        self.destroy()

if __name__ == "__main__":
    app = MainWindow(temp_dir="/tmp/smartcut_cache")
    app.mainloop()
