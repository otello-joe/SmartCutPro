import os, shutil, atexit, logging, tempfile, warnings, time
from ui.main_window import MainWindow
from tkinterdnd2 import TkinterDnD

warnings.filterwarnings('ignore', category=UserWarning, module='moviepy')

def get_optimal_temp_dir():
    """优化临时目录：Linux 优先使用内存盘 /dev/shm 以极大提升 I/O 速度"""
    if os.name != 'nt' and os.path.exists('/dev/shm'):
        return os.path.join('/dev/shm', 'smartcut_pro_cache')
    return os.path.join(tempfile.gettempdir(), 'smartcut_pro_cache')

APP_TEMP_DIR = get_optimal_temp_dir()

def clean_temp():
    """程序关闭时清理临时文件"""
    if os.path.exists(APP_TEMP_DIR):
        try: shutil.rmtree(APP_TEMP_DIR)
        except: pass

def cleanup_old_cache():
    """启动时清理超过 24 小时的僵尸缓存，防止内存/磁盘溢出"""
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
