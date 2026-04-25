import os, logging, uuid, subprocess, shutil, re, tempfile, gc, time
from datetime import datetime
from scenedetect import detect, ContentDetector, split_video_ffmpeg
from .config_mgr import cfg, LOG_FILE

# 统一临时目录：Linux 优先使用内存盘 /dev/shm
SYSTEM_TEMP = '/dev/shm' if (os.name != 'nt' and os.path.exists('/dev/shm')) else tempfile.gettempdir()

logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

def setup_ffmpeg_env():
    custom_ff = cfg.get("ffmpeg_path")
    if custom_ff and os.path.exists(custom_ff):
        os.environ["IMAGEIO_FFMPEG_EXE"] = custom_ff
        if os.name == 'nt':
            ff_dir = os.path.dirname(custom_ff)
            os.environ["PATH"] = ff_dir + os.pathsep + os.environ["PATH"]
    return custom_ff if (custom_ff and os.path.exists(custom_ff)) else 'ffmpeg'

FFMPEG_EXE = setup_ffmpeg_env()

try:
    from moviepy import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
    import moviepy.video.fx as vfx
    import moviepy.audio.fx as afx
    IS_V2 = True
except ImportError:
    try:
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, AudioFileClip, CompositeAudioClip
        from moviepy.editor import vfx, afx
        IS_V2 = False
    except ImportError as e:
        logging.error(f"MoviePy 加载失败: {e}"); raise

from .utils import GUIProgressBarLogger

def run_ffmpeg_with_stop(cmd, stop_event):
    """执行 FFmpeg 并支持 stop_event 强制终止进程"""
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        while process.poll() is None:
            if stop_event and stop_event.is_set():
                process.terminate()
                try: process.wait(timeout=2)
                except: process.kill()
                return False
            time.sleep(0.2)
        return True
    except Exception as e:
        logging.error(f"FFmpeg 执行异常: {e}"); return False

def get_video_full_info(filepath):
    try:
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=bit_rate,avg_frame_rate', '-of', 'default=noprint_wrappers=1:nokey=1', filepath]
        res = subprocess.run(cmd, capture_output=True, text=True).stdout.strip().split('\n')
        bitrate = int(res[0]) / 1000 if (len(res)>0 and res[0].isdigit()) else 5000
        fps = 30.0
        if len(res) > 1 and '/' in res[1]:
            n, d = res[1].split('/'); fps = float(n)/float(d)
        return int(bitrate), fps
    except: return 5000, 30.0

def get_safe_clean_name(filepath):
    base = os.path.splitext(os.path.basename(filepath))[0]
    clean = re.sub(r'[^\w\u4e00-\u9fa5\-]', '_', base).strip()
    return clean[:80]

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

def apply_effects(clip, wm_path, bgm_path, vol, speed=1.0, stop_event=None):
    # --- 1. 变速不变调核心逻辑 ---
    if speed != 1.0:
        try:
            original_audio = clip.audio
            if IS_V2:
                temp_video = clip.without_audio()
                if hasattr(temp_video, 'multiply_speed'): clip = temp_video.multiply_speed(speed)
                else:
                    from moviepy.video.fx import MultiplySpeed
                    clip = temp_video.with_effects([MultiplySpeed(speed)])
            else:
                temp_video = clip.set_audio(None)
                clip = temp_video.fx(vfx.speedx, speed)

            if original_audio is not None:
                temp_in = os.path.abspath(os.path.join(SYSTEM_TEMP, f"in_{uuid.uuid4().hex[:8]}.wav"))
                temp_out = os.path.abspath(os.path.join(SYSTEM_TEMP, f"out_{uuid.uuid4().hex[:8]}.wav"))
                original_audio.write_audiofile(temp_in, fps=44100, logger=None)
                cmd = [FFMPEG_EXE, '-y', '-i', temp_in, '-filter:a', f'atempo={speed}', '-ar', '44100', temp_out]
                if not run_ffmpeg_with_stop(cmd, stop_event): return None
                if IS_V2: from moviepy import AudioFileClip as AFClip
                else: from moviepy.editor import AudioFileClip as AFClip
                clip.audio = AFClip(temp_out)
                try: os.remove(temp_in); os.remove(temp_out)
                except: pass
        except Exception as e: logging.error(f"变速失败: {e}")

    # --- 2. 剪辑时间 ---
    safe_dur = max(0.1, clip.duration - 0.05)
    if hasattr(clip, 'subclipped'): clip = clip.subclipped(0, safe_dur)
    else: clip = clip.subclip(0, safe_dur)

    # --- 3. 水印 ---
    if wm_path and os.path.exists(wm_path):
        try:
            wm = ImageClip(wm_path)
            if hasattr(wm, 'resized'): wm = wm.resized(width=clip.size[0], height=clip.size[1])
            elif hasattr(wm, 'resize'): wm = wm.resize(newsize=clip.size)
            if hasattr(wm, 'with_duration'): wm = wm.with_duration(clip.duration)
            else: wm = wm.set_duration(clip.duration)
            clip = CompositeVideoClip([clip, wm])
        except Exception as e: logging.error(f"水印失败: {e}")

    # --- 4. 背景音乐 ---
    if bgm_path and os.path.exists(bgm_path):
        try:
            bgm = AudioFileClip(bgm_path)
            if bgm.duration < clip.duration:
                if hasattr(bgm, 'audio_loop'): bgm = bgm.audio_loop(duration=clip.duration)
                else:
                    from moviepy.audio.fx.all import audio_loop
                    bgm = audio_loop(bgm, duration=clip.duration)
            else:
                if hasattr(bgm, 'subclipped'): bgm = bgm.subclipped(0, clip.duration)
                else: bgm = bgm.subclip(0, clip.duration)
            try:
                if IS_V2:
                    from moviepy.audio.fx import MultiplyVolume
                    bgm = bgm.with_effects([MultiplyVolume(vol)])
                elif hasattr(bgm, 'volumex'): bgm = bgm.volumex(vol)
                elif hasattr(bgm, 'multiply_volume'): bgm = bgm.multiply_volume(vol)
            except: pass
            if hasattr(bgm, 'audio_fadeout'): bgm = bgm.audio_fadeout(2)
            clip.audio = CompositeAudioClip([clip.audio, bgm]) if clip.audio else bgm
        except Exception as e: logging.error(f"BGM失败: {e}")
    return clip

def safe_write_video(clip, out, p, logger, bitrate, fps, temp_dir, stop_event):
    if stop_event.is_set(): return
    target_br = f"{int(bitrate * 0.95)}k"
    tmp_audio = os.path.abspath(os.path.join(temp_dir, f"atmp_{uuid.uuid4().hex[:8]}.m4a"))
    write_args = {"codec": p.get('codec', 'libx264'), "bitrate": target_br, "fps": fps, "audio_codec": "aac", "temp_audiofile": tmp_audio, "remove_temp": True, "logger": logger, "threads": 4}
    try:
        clip.write_videofile(out, **write_args)
    except Exception as e:
        logging.error(f"渲染失败: {str(e)}")

def split_by_scene_changes(video_path, stop_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path); bitrate, fps = get_video_full_info(video_path)
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
            clip = VideoFileClip(video_path); total = len(scene_list)
            for i, s in enumerate(scene_list):
                if stop_event.is_set(): break
                status_cb(f"分段 {i+1}")
                st, en = s[0].get_seconds(), s[1].get_seconds()
                sub_raw = clip.subclipped(st, en) if hasattr(clip, 'subclipped') else clip.subclip(st, en)
                sub = apply_effects(sub_raw, p.get('wm'), p.get('bgm'), p.get('vol'), p.get('speed', 1.0), stop_event)
                if sub is None: break
                out = get_unique_output_path(out_dir, f"{clean_vname}_P{i+1:02d}")
                safe_write_video(sub, out, p, GUIProgressBarLogger(progress_cb, (i/total)*100, 1/total), bitrate, fps, temp_dir, stop_event)
            clip.close()
        return {"status": "Success"}
    except Exception as e:
        logging.error(f"智能分割出错 {video_path}: {str(e)}", exc_info=True); return {"status": "Error"}

def crop_split_screen(video_path, stop_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path); bitrate, fps = get_video_full_info(video_path)
        clean_vname = get_safe_clean_name(video_path); clip = VideoFileClip(video_path); w, h = clip.size
        for side in ["L", "R"]:
            if stop_event.is_set(): break
            status_cb(f"裁切 {side}")
            x1, x2 = (0, w/2) if side == "L" else (w/2, w)
            if hasattr(clip, 'cropped'): sub_c = clip.cropped(x1=x1, y1=0, x2=x2, y2=h)
            else: sub_c = clip.crop(x1=x1, y1=0, x2=x2, y2=h)
            sub = apply_effects(sub_c, p.get('wm'), p.get('bgm'), p.get('vol'), p.get('speed', 1.0), stop_event)
            if sub is None: break
            out = get_unique_output_path(out_dir, f"{clean_vname}_{side}")
            safe_write_video(sub, out, p, GUIProgressBarLogger(progress_cb, 0 if side=="L" else 50, 0.5), bitrate, fps, temp_dir, stop_event)
        clip.close(); return {"status": "Success"}
    except Exception as e:
        logging.error(f"分屏裁切出错: {str(e)}", exc_info=True); return {"status": "Error"}

def add_watermark_only(video_path, stop_event, progress_cb, status_cb, temp_dir, **p):
    try:
        out_dir = get_dynamic_outdir(video_path); bitrate, fps = get_video_full_info(video_path)
        clip_raw = VideoFileClip(video_path)
        clip = apply_effects(clip_raw, p.get('wm'), p.get('bgm'), p.get('vol'), p.get('speed', 1.0), stop_event)
        if clip is None: return {"status": "Error"}
        out = get_unique_output_path(out_dir, f"{get_safe_clean_name(video_path)}_成品")
        safe_write_video(clip, out, p, GUIProgressBarLogger(progress_cb), bitrate, fps, temp_dir, stop_event)
        clip.close(); return {"status": "Success"}
    except Exception as e:
        logging.error(f"合成成品出错: {str(e)}", exc_info=True); return {"status": "Error"}

def archive_original_file(video_path):
    try:
        parent = os.path.dirname(os.path.abspath(video_path))
        archive_dir = os.path.join(parent, "_已处理原片")
        os.makedirs(archive_dir, exist_ok=True)
        shutil.move(video_path, os.path.join(archive_dir, os.path.basename(video_path)))
    except: pass
