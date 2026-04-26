import sys
import os
import importlib.metadata
import subprocess

# --- 【终极补丁 1】：欺骗 imageio，防止 PyInstaller 打包后找不到元数据崩溃 ---
_original_version = importlib.metadata.version
def _patched_version(pkg_name):
    if pkg_name == 'imageio': return '2.33.0'
    if pkg_name == 'moviepy': return '1.0.3'
    try: return _original_version(pkg_name)
    except importlib.metadata.PackageNotFoundError: return '0.0.0'
importlib.metadata.version = _patched_version

# --- 【终极补丁 2】：全局拦截 subprocess，彻底拯救 Linux 下的 FFmpeg ---
# 这样不仅我们自己的代码，连 MoviePy 底层调用的 ffmpeg 也会被洗干净环境变量！
_old_popen = subprocess.Popen
def _patched_popen(*args, **kwargs):
    if 'env' not in kwargs:
        env = os.environ.copy()
        if 'LD_LIBRARY_PATH_ORIG' in env:
            env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
        elif 'LD_LIBRARY_PATH' in env:
            del env['LD_LIBRARY_PATH']
        kwargs['env'] = env
    return _old_popen(*args, **kwargs)
subprocess.Popen = _patched_popen
# --------------------------------------------------------

import shutil, atexit, logging, tempfile, warnings, time
from ui.main_window import MainWindow
from tkinterdnd2 import TkinterDnD

warnings.filterwarnings('ignore', category=UserWarning, module='moviepy')

def get_optimal_temp_dir():
    if os.name != 'nt' and os.path.exists('/dev/shm'):
        return os.path.join('/dev/shm', 'smartcut_pro_cache')
    return os.path.join(tempfile.gettempdir(), 'smartcut_pro_cache')

APP_TEMP_DIR = get_optimal_temp_dir()

def clean_temp():
    if os.path.exists(APP_TEMP_DIR):
        try: shutil.rmtree(APP_TEMP_DIR)
        except: pass

def cleanup_old_cache():
    if os.path.exists(APP_TEMP_DIR):
        now = time.time()
        for f in os.listdir(APP_TEMP_DIR):
            fp = os.path.join(APP_TEMP_DIR, f)
            try:
                if os.stat(fp).st_mtime < now - 86400:
                    if os.path.isdir(fp): shutil.rmtree(fp)
                    else: os.remove(fp)
            except: pass

if __name__ == '__main__':
    cleanup_old_cache()
    os.makedirs(APP_TEMP_DIR, exist_ok=True)
    atexit.register(clean_temp)
    app = MainWindow(temp_dir=APP_TEMP_DIR)
    app.mainloop()
