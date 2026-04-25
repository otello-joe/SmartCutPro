import os
import json

if os.name == 'nt':
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA', 'C:'), 'SmartCutPro')
else:
    CONFIG_DIR = os.path.expanduser("~/.config/SmartCutPro")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
LOG_FILE = os.path.join(CONFIG_DIR, "app.log")
os.makedirs(CONFIG_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "theme": "Light", "concurrency": 2, "last_watermark": "", "last_bgm": "",
    "last_bgm_vol": 0.2, "default_mode": 1, "auto_archive": True,
    "gpu_codec": "libx264", "ffmpeg_path": "", "app_style": "Standard",
    # 布局记忆默认值
    "win_width": 1150, "win_height": 880, "win_x": 100, "win_y": 100, "pane_width": 310
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()
    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f: self.config.update(json.load(f))
            except: pass
    def save(self):
        with open(CONFIG_FILE, "w") as f: json.dump(self.config, f, indent=4)
    def get(self, key, default=None): return self.config.get(key, default)
    def set(self, key, value):
        self.config[key] = value
        self.save()

cfg = ConfigManager()
