import sys
import os
import logging
import uuid
import subprocess
import shutil
import re
import tempfile
import gc
import time
import signal
import threading
import json
from datetime import datetime
from scenedetect import detect, ContentDetector, split_video_ffmpeg
from .config_mgr import cfg, LOG_FILE

# 统一临时目录：Linux 优先使用内存盘 /dev/shm
SYSTEM_TEMP = '/dev/shm' if (os.name != 'nt' and os.path.exists('/dev/shm')) else tempfile.gettempdir()

logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 【底层补丁】：洗掉 PyInstaller 的环境变量污染，拯救 Linux 下的 FFmpeg ---
def get_clean_env():
    env = os.environ.copy()
    if 'LD_LIBRARY_PATH_ORIG' in env:
        env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
    elif 'LD_LIBRARY_PATH' in env:
        del env['LD_LIBRARY_PATH']
    return env

# --- 【核心升级】：寻找 PyInstaller 打包自带的 FFmpeg ---
def get_bundled_exe(name):
    """获取打包后的内置程序路径"""
    exe_name = f"{name}.exe" if os.name == 'nt' else name
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        bundled_path = os.path.join(sys._MEIPASS, exe_name)
        if os.path.exists(bundled_path):
            return bundled_path
    return None

def setup_ffmpeg_env():
    # 1. 用户自定义路径优先
    custom_ff = cfg.get("ffmpeg_path")
    if custom_ff and os.path.exists(custom_ff):
        os.environ["FFMPEG_BINARY"] = custom_ff
        if os.name == 'nt':
            ff_dir = os.path.dirname(custom_ff)
            os.environ["PATH"] = ff_dir + os.pathsep + os.environ["PATH"]
        ffprobe_path = custom_ff.replace('ffmpeg', 'ffprobe')
        return custom_ff, ffprobe_path if os.path.exists(ffprobe_path) else 'ffprobe'

    # 2. 其次寻找打包自带的 FFmpeg (绿色免安装核心)
    bundled_ff = get_bundled_exe('ffmpeg')
    bundled_fp = get_bundled_exe('ffprobe')
    if bundled_ff:
        os.environ["FFMPEG_BINARY"] = bundled_ff
        return bundled_ff, (bundled_fp or 'ffprobe')

    # 3. 最后回退到系统环境变量
    return ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'), ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')

FFMPEG_EXE, FFPROBE_EXE = setup_ffmpeg_env()

class CancelledError(Exception):
    pass

def get_video_full_info(filepath):
    try:
        cmd =[FFPROBE_EXE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,bit_rate,avg_frame_rate,duration', '-of', 'json', filepath]
        out = subprocess.run(cmd, capture_output=True, text=True, env=get_clean_env()).stdout
        data = json.loads(out)['streams'][0]
        w = int(data.get('width', 1920))
        h = int(data.get('height', 1080))
        br = int(data.get('bit_rate', 5000000)) / 1000
        fps_str = data.get('avg_frame_rate', '30/1')
        n, d = fps_str.split('/')
        fps = float(n) / float(d) if float(d) != 0 else 30.0
        dur = float(data.get('duration', 0.0))
        return w, h, int(br), fps, dur
    except:
        return 1920, 1080, 5000, 30.0, 0.0

def has_audio(filepath):
    try:
        cmd =[FFPROBE_EXE, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', filepath]
        res = subprocess.run(cmd, capture_output=True, text=True, env=get_clean_env()).stdout.strip()
        return len(res) > 0
    except:
        return False

def get_safe_clean_name(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    return re.sub(r'[^\w\u4e00-\u9fa5\-]', '_', base).strip()[:80]

def get_unique_output_path(out_dir, base_name, suffix=".mp4"):
    target = os.path.abspath(os.path.join(out_dir, f"{base_name}{suffix}"))
    if not os.path.exists(target): return target
    counter = 1
    while True:
        new_target = os.path.abspath(os.path.join(out_dir, f"{base_name}_{counter}{suffix}"))
        if not os.path.exists(new_target): return new_target
        counter += 1

def get_dynamic_outdir(video_path):
    base_dir = os.path.dirname(os.path.abspath(video_path))
    folder_name = f"SmartCut_成品_{datetime.now().strftime('%m%d')}"
    if folder_name in base_dir: return base_dir
    out_dir = os.path.join(base_dir, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir

# --- 【核心黑科技】：纯 FFmpeg 滤镜链，一气呵成完成所有特效 ---
def process_video_ffmpeg(in_video, out_video, start_t, end_t, wm_path, bgm_path, speed, vol, w, h, has_a, stop_event, pause_event, progress_cb, crop_filter=None, crf=23):
    cmd = [FFMPEG_EXE, '-y']

    if start_t is not None and end_t is not None:
        cmd.extend(['-ss', str(start_t), '-to', str(end_t)])
    cmd.extend(['-i', in_video])

    inputs_count = 1
    wm_idx = -1
    if wm_path and os.path.exists(wm_path):
        cmd.extend(['-loop', '1', '-i', wm_path])
        wm_idx = inputs_count
        inputs_count += 1

    bgm_idx = -1
    if bgm_path and os.path.exists(bgm_path):
        cmd.extend(['-stream_loop', '-1', '-i', bgm_path])
        bgm_idx = inputs_count
        inputs_count += 1

    filters =[]
    v_curr = "0:v:0"
    a_curr = "0:a:0" if has_a else None

    # 1. 裁切
    if crop_filter:
        filters.append(f"[{v_curr}]{crop_filter}[v_crop]")
        v_curr = "v_crop"
        if crop_filter.startswith("crop=iw/2"): w = w // 2

    # 2. 变速
    if speed != 1.0:
        filters.append(f"[{v_curr}]setpts={1/speed}*PTS[v_spd]")
        v_curr = "v_spd"
        if a_curr:
            filters.append(f"[{a_curr}]atempo={speed}[a_spd]")
            a_curr = "a_spd"

    # 3. 水印
    if wm_idx != -1:
        filters.append(f"[{wm_idx}:v]scale={w}:{h}[wm_scaled]")
        filters.append(f"[{v_curr}][wm_scaled]overlay=shortest=1[v_wm]")
        v_curr = "v_wm"

    # 4. BGM 混音
    if bgm_idx != -1:
        filters.append(f"[{bgm_idx}:a]volume={vol}[bgm_vol]")
        if a_curr:
            filters.append(f"[{a_curr}][bgm_vol]amix=inputs=2:duration=first:dropout_transition=2[a_mix]")
            a_curr = "a_mix"
        else:
            a_curr = "bgm_vol"

    # 智能判断是否需要加中括号，防止 FFmpeg 报 234 错误
    def get_map(pad):
        return pad if pad.startswith("0:") else f"[{pad}]"

    if filters:
        cmd.extend(['-filter_complex', ";".join(filters)])
        cmd.extend(['-map', get_map(v_curr)])
        if a_curr: cmd.extend(['-map', get_map(a_curr)])
    else:
        cmd.extend(['-map', '0:v:0'])
        if a_curr: cmd.extend(['-map', '0:a:0'])

    # 编码参数 (保持画质无损与极速，强制 yuv420p 保证缩略图显示)
    cmd.extend(['-c:v', 'libx264', '-preset', 'veryfast', '-crf', str(crf), '-pix_fmt', 'yuv420p', '-movflags', '+faststart'])

    if a_curr:
        cmd.extend(['-c:a', 'aac'])

    if wm_idx != -1 or bgm_idx != -1: cmd.append('-shortest')
    cmd.append(out_video)

    # 计算总时长用于进度条
    if start_t is not None and end_t is not None:
        total_dur = (end_t - start_t) / speed
    else:
        _, _, _, _, dur = get_video_full_info(in_video)
        total_dur = dur / speed

    error_log =[]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env=get_clean_env(), universal_newlines=True)
        is_paused = False

        # 异步读取 FFmpeg 进度和错误日志
        def read_stderr():
            time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
            for line in process.stderr:
                error_log.append(line.strip())
                if len(error_log) > 20: error_log.pop(0)
                match = time_pattern.search(line)
                if match and total_dur > 0:
                    h, m, s = map(float, match.groups())
                    current_time = h * 3600 + m * 60 + s
                    progress = min(100, (current_time / total_dur) * 100)
                    if progress_cb: progress_cb(progress)

        threading.Thread(target=read_stderr, daemon=True).start()

        while process.poll() is None:
            if stop_event and stop_event.is_set():
                if is_paused and os.name != 'nt':
                    try: os.kill(process.pid, signal.SIGCONT)
                    except: pass
                process.terminate()
                try: process.wait(timeout=2)
                except: process.kill()
                if os.path.exists(out_video):
                    try: os.remove(out_video)
                    except: pass
                raise CancelledError("Task cancelled by user")

            if pause_event:
                if not pause_event.is_set():
                    if not is_paused and os.name != 'nt':
                        try: os.kill(process.pid, signal.SIGSTOP)
                        except: pass
                        is_paused = True
                    pause_event.wait()
                    if is_paused and os.name != 'nt':
                        try: os.kill(process.pid, signal.SIGCONT)
                        except: pass
                        is_paused = False
            time.sleep(0.2)

        process.wait()
        if process.returncode != 0:
            err_msg = "\n".join(error_log)
            logging.error(f"FFmpeg 渲染失败，退出码: {process.returncode}\n详细错误:\n{err_msg}")
            return False

        if progress_cb: progress_cb(100)
        return True
    except CancelledError:
        raise
    except Exception as e:
        logging.error(f"FFmpeg 执行异常: {e}")
        return False

def split_by_scene_changes(video_path, stop_event, pause_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path)
        w, h, _, _, _ = get_video_full_info(video_path)
        has_a = has_audio(video_path)
        clean_vname = get_safe_clean_name(video_path)

        status_cb("🔍 场景扫描中...")
        scene_list = detect(video_path, ContentDetector(threshold=27.0))
        if len(scene_list) <= 1: return {"status": "Skipped"}

        if not p.get('wm') and not p.get('bgm') and p.get('speed', 1.0) == 1.0:
            status_cb("🚀 极速秒切")
            tpl = os.path.join(out_dir, f"{clean_vname}_S$SCENE_NUMBER.mp4")
            split_video_ffmpeg(video_path, scene_list, output_file_template=tpl, show_progress=False)
            progress_cb(100)
        else:
            total = len(scene_list)
            for i, s in enumerate(scene_list):
                if stop_event.is_set(): raise CancelledError()
                status_cb(f"分段 {i+1}")
                st, en = s[0].get_seconds(), s[1].get_seconds()
                out = get_unique_output_path(out_dir, f"{clean_vname}_P{i+1:02d}")

                def sub_progress(val): progress_cb((i / total) * 100 + (val / total))

                success = process_video_ffmpeg(
                    video_path, out, st, en, p.get('wm'), p.get('bgm'), p.get('speed', 1.0), p.get('vol', 0.2),
                    w, h, has_a, stop_event, pause_event, sub_progress, crf=p.get('crf', 23)
                )
                if not success: break
        return {"status": "Success"}
    except CancelledError:
        raise
    except Exception as e:
        logging.error(f"智能分割出错 {video_path}: {str(e)}", exc_info=True)
        return {"status": "Error"}

def crop_split_screen(video_path, stop_event, pause_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path)
        w, h, _, _, _ = get_video_full_info(video_path)
        has_a = has_audio(video_path)
        clean_vname = get_safe_clean_name(video_path)

        for i, side in enumerate(["L", "R"]):
            if stop_event.is_set(): raise CancelledError()
            status_cb(f"裁切 {side}")
            crop_filter = "crop=iw/2:ih:0:0" if side == "L" else "crop=iw/2:ih:iw/2:0"
            out = get_unique_output_path(out_dir, f"{clean_vname}_{side}")

            def sub_progress(val): progress_cb((i / 2) * 100 + (val / 2))

            success = process_video_ffmpeg(
                video_path, out, None, None, p.get('wm'), p.get('bgm'), p.get('speed', 1.0), p.get('vol', 0.2),
                w, h, has_a, stop_event, pause_event, sub_progress, crop_filter=crop_filter, crf=p.get('crf', 23)
            )
            if not success: break
        return {"status": "Success"}
    except CancelledError:
        raise
    except Exception as e:
        logging.error(f"分屏裁切出错: {str(e)}", exc_info=True)
        return {"status": "Error"}

def add_watermark_only(video_path, stop_event, pause_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path)
        w, h, _, _, _ = get_video_full_info(video_path)
        has_a = has_audio(video_path)
        out = get_unique_output_path(out_dir, f"{get_safe_clean_name(video_path)}_成品")

        success = process_video_ffmpeg(
            video_path, out, None, None, p.get('wm'), p.get('bgm'), p.get('speed', 1.0), p.get('vol', 0.2),
            w, h, has_a, stop_event, pause_event, progress_cb, crf=p.get('crf', 23)
        )
        if not success: return {"status": "Error"}
        return {"status": "Success"}
    except CancelledError:
        raise
    except Exception as e:
        logging.error(f"合成成品出错: {str(e)}", exc_info=True)
        return {"status": "Error"}

def archive_original_file(video_path):
    try:
        parent = os.path.dirname(os.path.abspath(video_path))
        archive_dir = os.path.join(parent, "_已处理原片")
        os.makedirs(archive_dir, exist_ok=True)
        shutil.move(video_path, os.path.join(archive_dir, os.path.basename(video_path)))
    except:
        pass
