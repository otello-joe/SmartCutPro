import sys
import os
import subprocess
import shutil, atexit, logging, tempfile, time
from ui.main_window import MainWindow
from tkinterdnd2 import TkinterDnD

# --- 【终极补丁】：全局拦截 subprocess，彻底拯救 Linux 下的 FFmpeg ---
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
