#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Studio Pro — Mobile & Termux Edition
- Android Termux ও PC উভয় জায়গায় সরাসরি কার্যকর (কোনো Tkinter বা ভারী ডিপেনডেন্সি নেই)
- 100% Copyright Bypass & Turbo Engine (FFmpeg Native High-Speed Filters)
- Termux-এ চললে সরাসরি ফোনের স্টোরেজ (/sdcard/Download) থেকে ভিডিও নির্বাচন ও সেভ করার সুবিধা
"""

import os
import sys
import json
import time
import socket
import shutil
import threading
import subprocess
from flask import Flask, request, jsonify, send_from_directory, render_template_string

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50 GB max upload

# Termux পরিবেশ সনাক্তকরণ
IS_TERMUX = 'com.termux' in os.environ.get('PREFIX', '') or os.path.exists('/data/data/com.termux')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if IS_TERMUX and os.path.exists('/sdcard/Download'):
    UPLOAD_FOLDER = "/sdcard/Download"
    OUTPUT_FOLDER = "/sdcard/Download"
else:
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "mobile_uploads")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "mobile_outputs")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ============================ FFmpeg TOOL DISCOVERY ============================

def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    found = shutil.which(name)
    if not found and os.name == "nt":
        found = shutil.which(exe)

    if not found:
        cand = os.path.join(BASE_DIR, exe)
        if os.path.exists(cand):
            return cand
    return found


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


# ============================ HARDWARE ENCODER DETECTION ============================

def test_ffmpeg_encoder(codec):
    if not FFMPEG:
        return False
    try:
        r = subprocess.run(
            [FFMPEG, "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=15",
             "-c:v", codec, "-f", "null", "-"],
            capture_output=True, text=True, timeout=8
        )
        return r.returncode == 0
    except Exception:
        return False


def detect_hardware_encoders():
    encoders = []
    # 1. NVIDIA NVENC
    if test_ffmpeg_encoder("h264_nvenc"):
        encoders.append({
            "id": "nvenc",
            "name": "NVIDIA NVENC (GPU)",
            "codec": "h264_nvenc",
            "opts": ["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "22"]
        })
    # 2. Intel QuickSync (QSV)
    if test_ffmpeg_encoder("h264_qsv"):
        encoders.append({
            "id": "qsv",
            "name": "Intel QuickSync (QSV GPU)",
            "codec": "h264_qsv",
            "opts": ["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", "3.5M"]
        })
    # 3. AMD AMF
    if test_ffmpeg_encoder("h264_amf"):
        encoders.append({
            "id": "amf",
            "name": "AMD AMF (GPU)",
            "codec": "h264_amf",
            "opts": ["-c:v", "h264_amf", "-usage", "transcoding", "-quality", "speed"]
        })
    # 4. Android MediaCodec (if Termux ffmpeg compiled with it)
    if test_ffmpeg_encoder("h264_mediacodec"):
        encoders.append({
            "id": "mediacodec",
            "name": "Android MediaCodec (Hardware)",
            "codec": "h264_mediacodec",
            "opts": ["-c:v", "h264_mediacodec", "-b:v", "3.5M"]
        })
    # 5. CPU Ultrafast
    encoders.append({
        "id": "cpu",
        "name": "CPU x264 (Ultrafast Mode)",
        "codec": "libx264",
        "opts": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "21", "-threads", "0"]
    })
    return encoders


DETECTED_ENCODERS = detect_hardware_encoders()


# ============================ PROBE & FILTERS ============================

def probe_duration(path):
    if not FFPROBE:
        return None
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=120)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def probe_audio_sr(path):
    if not FFPROBE:
        return 48000, 2
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate,channels", "-of", "json", path],
            capture_output=True, text=True, timeout=60)
        st = json.loads(r.stdout)["streams"][0]
        return int(st.get("sample_rate", 48000)), int(st.get("channels", 2))
    except Exception:
        return 48000, 2


def probe_video_info(path):
    if not FFPROBE:
        return 1920, 1080, 30.0
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate", "-of", "json", path],
            capture_output=True, text=True, timeout=60)
        st = json.loads(r.stdout)["streams"][0]
        w = int(st.get("width", 1920))
        h = int(st.get("height", 1080))

        def parse_fps(val):
            if not val or val == "0/0":
                return 30.0
            p = val.split("/")
            if len(p) == 2 and int(p[1]) != 0:
                return float(p[0]) / float(p[1])
            return float(val)

        fps = parse_fps(st.get("r_frame_rate")) or parse_fps(st.get("avg_frame_rate")) or 30.0
        return w, h, fps
    except Exception:
        return 1920, 1080, 30.0


def has_audio(path):
    if not FFPROBE:
        return True
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60)
        return bool(r.stdout.strip())
    except Exception:
        return False


def get_atempo_chain(ratio):
    filters = []
    r = float(ratio)
    while r > 2.0:
        filters.append("atempo=2.0")
        r /= 2.0
    while r < 0.5:
        filters.append("atempo=0.5")
        r /= 0.5
    filters.append(f"atempo={r:.5f}")
    return ",".join(filters)


def build_bypass_video_filters(w, h, bypass_strength="Strong", speed_factor=1.025,
                               mirror=False, resolution_mode="720p",
                               grade_name="Teal & Orange", grade_intensity=65.0):
    vf = []
    if bypass_strength == "Extreme":
        crop_pct = 0.94
        grain_strength = 6
        vignette_val = "PI/3.6"
        hue_rot = 3.5
        sat_boost = 1.18
        con_boost = 1.14
    elif bypass_strength == "Moderate":
        crop_pct = 0.98
        grain_strength = 3
        vignette_val = "PI/4.5"
        hue_rot = 1.8
        sat_boost = 1.08
        con_boost = 1.06
    else:
        crop_pct = 0.96
        grain_strength = 4
        vignette_val = "PI/4"
        hue_rot = 2.5
        sat_boost = 1.14
        con_boost = 1.10

    # ১. মাইক্রো-ক্রপ ও জুম
    vf.append(f"crop=in_w*{crop_pct:.3f}:in_h*{crop_pct:.3f}:(in_w-out_w)/2:(in_h-out_h)/2")

    # ২. মিরর ফ্লিপ
    if mirror:
        vf.append("hflip")

    # ৩. রেজোলিউশন স্কেল
    if resolution_mode == "720p":
        target_w, target_h = 1280, 720
    elif resolution_mode == "1080p":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = w, h

    vf.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")

    # ৪. কালার গ্রেড
    s = max(0.1, min(float(grade_intensity), 100.0)) / 100.0
    if grade_name.startswith("Teal"):
        vf.append(f"colorbalance=rs={0.07*s:.3f}:bs={-0.07*s:.3f}:rh={-0.05*s:.3f}:bh={0.07*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.12*s:.3f}:saturation={1.0+0.18*s:.3f}:gamma={1.0+0.02*s:.3f}")
    elif grade_name.startswith("Warm"):
        vf.append(f"colorbalance=rs={0.10*s:.3f}:bs={-0.06*s:.3f}:gs={0.02*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.10*s:.3f}:saturation={1.0+0.14*s:.3f}:gamma={1.0+0.03*s:.3f}")
    elif grade_name.startswith("Cold"):
        vf.append(f"colorbalance=bs={0.10*s:.3f}:bh={0.06*s:.3f}:rs={-0.05*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.10*s:.3f}:saturation={1.0-0.10*s:.3f}")
    elif grade_name.startswith("Vivid"):
        vf.append(f"eq=contrast={1.0+0.14*s:.3f}:saturation={1.0+0.28*s:.3f}")
        vf.append(f"unsharp=3:3:{0.4*s:.2f}")
    elif grade_name.startswith("Noir"):
        vf.append(f"hue=s={1.0-1.0*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.20*s:.3f}:brightness={-0.02*s:.3f}")
    else:
        vf.append(f"colorbalance=rs={0.05*s:.3f}:bs={-0.05*s:.3f}:rh={0.03*s:.3f}")
        vf.append(f"eq=contrast={con_boost:.3f}:saturation={sat_boost:.3f}")

    vf.append(f"hue=h={hue_rot:.1f}:s={sat_boost:.2f}")
    vf.append(f"vignette={vignette_val}")
    vf.append(f"noise=alls={grain_strength}:allf=t+u")

    if abs(speed_factor - 1.0) > 0.001:
        vf.append(f"setpts=PTS/{speed_factor:.4f}")

    return ",".join(vf)


def build_bypass_audio_filters(sr=48000, voice_preset="Original",
                               pitch_steps=0.0, speed_factor=1.025,
                               enable_aphaser=True, enable_eq=True):
    af = []
    sr = int(sr) if sr else 48000
    pitch_mult = 2.0 ** (pitch_steps / 12.0)
    if abs(pitch_mult - 1.0) > 0.005:
        target_rate = int(sr * pitch_mult)
        af.append(f"asetrate={target_rate},aresample={sr}")

    tempo_ratio = speed_factor / pitch_mult
    af.append(get_atempo_chain(tempo_ratio))

    if enable_aphaser:
        af.append("aphaser=in_gain=0.92:out_gain=0.92:delay=3.0:decay=0.35:speed=0.5:type=t")

    if enable_eq:
        af.append("equalizer=f=180:t=q:w=1.2:g=2.0")
        af.append("equalizer=f=1100:t=q:w=1.2:g=-1.8")
        af.append("equalizer=f=3600:t=q:w=1.5:g=1.8")

    af.append("acompressor=threshold=0.55:ratio=2.5:makeup=1.1")
    return ",".join(af)


def run_ffmpeg_progress(cmd, dur, cb, log_fn=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, errors="replace")
    err_lines = []

    def drain():
        try:
            for line in p.stderr:
                err_lines.append(line)
        except Exception:
            pass

    th = threading.Thread(target=drain, daemon=True)
    th.start()
    last_reported = -1
    for line in p.stdout:
        line = line.strip()
        if line.startswith("out_time=") and dur:
            try:
                parts = line.split("=", 1)[1].split(":")
                while len(parts) < 3:
                    parts.insert(0, "0")
                t = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                pct = min(100, max(0, int(100 * t / dur)))
                if pct != last_reported:
                    last_reported = pct
                    cb(pct)
            except Exception:
                pass
    code = p.wait()
    th.join(timeout=5)
    if code != 0:
        raise RuntimeError("ffmpeg ব্যর্থ:\n" + "".join(err_lines)[-800:])


# ============================ SERVER STATE ============================

current_task = {
    "busy": False,
    "progress": 0,
    "status": "প্রস্তুত",
    "filename": "",
    "out_filename": "",
    "error": None,
    "start_time": 0,
    "elapsed": "0s",
    "eta": "--",
    "logs": []
}


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Video Studio Pro — Mobile Edition</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e17;
            --bg-card: rgba(22, 30, 49, 0.75);
            --bg-card-border: rgba(255, 255, 255, 0.08);
            --accent-blue: #2563eb;
            --accent-cyan: #06b6d4;
            --accent-green: #10b981;
            --accent-gradient: linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --radius-lg: 16px;
            --radius-md: 12px;
            --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            -webkit-tap-highlight-color: transparent;
        }

        body {
            font-family: 'Outfit', 'Hind Siliguri', -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-main);
            min-height: 100vh;
            padding-bottom: 50px;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(6, 182, 212, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.12) 0%, transparent 40%);
            background-attachment: fixed;
        }

        header {
            padding: 18px 20px;
            background: rgba(10, 14, 23, 0.85);
            backdrop-filter: blur(20px);
            position: sticky;
            top: 0;
            z-index: 100;
            border-bottom: 1px solid var(--bg-card-border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .brand-icon {
            width: 38px;
            height: 38px;
            background: var(--accent-gradient);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
        }

        .brand-title {
            font-size: 1.15rem;
            font-weight: 700;
            letter-spacing: -0.3px;
        }

        .brand-title span {
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hw-tag {
            font-size: 0.72rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .hw-dot {
            width: 6px;
            height: 6px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 1.8s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.6; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.6; }
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
            padding: 16px 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: var(--radius-lg);
            padding: 16px;
            box-shadow: var(--shadow-card);
            backdrop-filter: blur(12px);
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .card-title {
            font-size: 0.98rem;
            font-weight: 600;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .termux-banner {
            background: rgba(6, 182, 212, 0.12);
            border: 1px solid rgba(6, 182, 212, 0.3);
            border-radius: var(--radius-md);
            padding: 10px 12px;
            font-size: 0.8rem;
            color: #7dd3fc;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Upload Area */
        .upload-box {
            border: 2px dashed rgba(59, 130, 246, 0.4);
            border-radius: var(--radius-md);
            padding: 24px 16px;
            text-align: center;
            background: rgba(15, 23, 42, 0.4);
            cursor: pointer;
            transition: all 0.25s ease;
        }

        .upload-box:active {
            transform: scale(0.98);
            border-color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.08);
        }

        .upload-icon {
            font-size: 38px;
            margin-bottom: 8px;
        }

        .upload-text {
            font-size: 0.95rem;
            font-weight: 600;
            color: #f1f5f9;
        }

        .upload-sub {
            font-size: 0.78rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .file-info-badge {
            margin-top: 12px;
            padding: 10px 12px;
            background: rgba(30, 41, 59, 0.8);
            border-radius: 10px;
            display: none;
            align-items: center;
            justify-content: space-between;
            font-size: 0.85rem;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        /* Selectable Chips / Segments */
        .chip-group {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
            gap: 8px;
            margin-top: 8px;
        }

        .chip-btn {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            padding: 10px 8px;
            border-radius: 10px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s ease;
        }

        .chip-btn.active {
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.2), rgba(59, 130, 246, 0.3));
            border-color: var(--accent-cyan);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(6, 182, 212, 0.25);
        }

        /* Toggle Switches */
        .toggle-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .toggle-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .toggle-label {
            font-size: 0.88rem;
            font-weight: 500;
        }

        .toggle-sub {
            font-size: 0.74rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 46px;
            height: 26px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position: absolute;
            cursor: pointer;
            top: 0; left: 0; right: 0; bottom: 0;
            background-color: rgba(255, 255, 255, 0.15);
            transition: .3s;
            border-radius: 26px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: .3s;
            border-radius: 50%;
        }

        input:checked + .slider {
            background: linear-gradient(135deg, #06b6d4, #3b82f6);
        }

        input:checked + .slider:before {
            transform: translateX(20px);
        }

        /* Action Buttons */
        .btn-action {
            width: 100%;
            padding: 15px;
            background: var(--accent-gradient);
            border: none;
            border-radius: var(--radius-lg);
            color: white;
            font-size: 1.05rem;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 8px 25px rgba(59, 130, 246, 0.45);
            transition: transform 0.2s ease, opacity 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .btn-action:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            box-shadow: none;
        }

        .btn-action:active:not(:disabled) {
            transform: scale(0.98);
        }

        /* Progress Card */
        .progress-card {
            display: none;
            text-align: center;
            padding: 20px 16px;
        }

        .progress-bar-bg {
            width: 100%;
            height: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            overflow: hidden;
            margin: 14px 0 8px;
        }

        .progress-bar-fill {
            height: 100%;
            width: 0%;
            background: var(--accent-gradient);
            border-radius: 10px;
            transition: width 0.3s ease;
            box-shadow: 0 0 12px rgba(6, 182, 212, 0.6);
        }

        .status-msg {
            font-size: 0.92rem;
            font-weight: 600;
            color: #38bdf8;
            margin-top: 6px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 14px;
        }

        .stat-item {
            background: rgba(15, 23, 42, 0.5);
            padding: 8px;
            border-radius: 8px;
            font-size: 0.78rem;
            color: var(--text-muted);
        }

        .stat-val {
            font-size: 1rem;
            font-weight: 700;
            color: #f8fafc;
            margin-top: 2px;
        }

        .result-box {
            display: none;
            margin-top: 14px;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: var(--radius-md);
            padding: 16px;
            text-align: center;
        }

        .btn-download {
            margin-top: 12px;
            width: 100%;
            padding: 14px;
            background: #10b981;
            color: white;
            font-weight: 700;
            border: none;
            border-radius: 10px;
            font-size: 0.98rem;
            cursor: pointer;
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            text-decoration: none;
        }

        .log-box {
            background: #020617;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 10px;
            font-family: monospace;
            font-size: 0.75rem;
            color: #94a3b8;
            max-height: 120px;
            overflow-y: auto;
            text-align: left;
            margin-top: 12px;
            white-space: pre-wrap;
            line-height: 1.4;
        }
    </style>
</head>
<body>

<header>
    <div class="brand">
        <div class="brand-icon">⚡</div>
        <div>
            <div class="brand-title">Video Studio <span>Pro</span></div>
            <div style="font-size: 0.72rem; color: #94a3b8;">Mobile & Termux Edition</div>
        </div>
    </div>
    <div class="hw-tag">
        <div class="hw-dot"></div>
        <span id="hwName">প্রস্তুত</span>
    </div>
</header>

<div class="container">

    {% if is_termux %}
    <div class="termux-banner">
        <span>🤖</span>
        <div><b>Termux মোড সক্রিয়:</b> এডিট করা ভিডিও সরাসরি আপনার ফোনের <b>Download</b> ফোল্ডারে সেভ হবে!</div>
    </div>
    {% endif %}

    <!-- কার্ড ১: ফাইল আপলোড -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">📁 ভিডিও বাছাই করুন</div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">যেকোনো ৫ ঘণ্টার ফাইল</span>
        </div>

        <div class="upload-box" onclick="document.getElementById('videoInput').click()">
            <div class="upload-icon">🎬</div>
            <div class="upload-text">মোবাইল থেকে ভিডিও নির্বাচন করুন</div>
            <div class="upload-sub">Gallery বা Files থেকে ভিডিও ট্যাপ করুন</div>
            <input type="file" id="videoInput" accept="video/*,audio/*" style="display: none;" onchange="handleFileSelect(event)">
        </div>

        <div class="file-info-badge" id="fileBadge">
            <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%;">
                <span id="fileName" style="font-weight: 600;">ভিডিও.mp4</span>
                <div id="fileSize" style="font-size: 0.75rem; color: #94a3b8;">-- MB</div>
            </div>
            <button onclick="clearSelectedFile()" style="background: none; border: none; color: #ef4444; font-size: 1.2rem;">✖</button>
        </div>
    </div>

    <!-- কার্ড ২: ১০০% কপিরাইট বাইপাস পাওয়ার -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🛡️ ১০০% Copyright Bypass পাওয়ার</div>
        </div>
        <div class="chip-group" id="strengthGroup">
            <div class="chip-btn active" data-val="Strong" onclick="setStrength('Strong', this)">
                ⚡ Strong<br><span style="font-size:0.7rem; font-weight:normal;">১০০% রিকমেন্ডেড</span>
            </div>
            <div class="chip-btn" data-val="Extreme" onclick="setStrength('Extreme', this)">
                🔥 Extreme<br><span style="font-size:0.7rem; font-weight:normal;">সর্বোচ্চ পরিবর্তন</span>
            </div>
            <div class="chip-btn" data-val="Moderate" onclick="setStrength('Moderate', this)">
                ✨ Moderate<br><span style="font-size:0.7rem; font-weight:normal;">হালকা গ্রেডিং</span>
            </div>
        </div>
    </div>

    <!-- কার্ড ৩: স্পিড প্রোফাইল -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">⚡ রেন্ডারিং স্পিড প্রোফাইল</div>
        </div>
        <div class="chip-group" id="resGroup">
            <div class="chip-btn active" data-val="720p" onclick="setRes('720p', this)">
                ⚡ 720p Turbo Fast<br><span style="font-size:0.7rem; font-weight:normal;">দ্রুততম রেন্ডার</span>
            </div>
            <div class="chip-btn" data-val="1080p" onclick="setRes('1080p', this)">
                🎬 1080p Full HD<br><span style="font-size:0.7rem; font-weight:normal;">হাই কোয়ালিটি</span>
            </div>
        </div>
    </div>

    <!-- কার্ড ৪: ফিঙ্গারপ্রিন্ট ব্রেকার অপশন -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">⚙️ স্পেশাল ফিচারস</div>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🔄 হরিজন্টাল মিরর (Mirror Flip)</div>
                <div class="toggle-sub">ভিডিও সম্পূর্ণ ডানে-বামে উল্টানো</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="mirrorFlip">
                <span class="slider"></span>
            </label>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🏃 ১.০২৫x মাইক্রো-স্পিড শিফট</div>
                <div class="toggle-sub">টাইমস্ট্যাম্প ও ফ্রেমরেট ম্যাচিং ধ্বংস করে</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="speedShift" checked>
                <span class="slider"></span>
            </label>
        </div>
    </div>

    <!-- কার্ড ৫: কালার গ্রেডিং ও লুক -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🎨 সিনেমাটিক কালার গ্রেড</div>
        </div>
        <div class="chip-group" id="gradeGroup">
            <div class="chip-btn active" data-val="Teal & Orange" onclick="setGrade('Teal & Orange', this)">Teal & Orange</div>
            <div class="chip-btn" data-val="Vivid Pop" onclick="setGrade('Vivid Pop', this)">Vivid Pop</div>
            <div class="chip-btn" data-val="Warm Film" onclick="setGrade('Warm Film', this)">Warm Gold</div>
            <div class="chip-btn" data-val="Cold Cinematic" onclick="setGrade('Cold Cinematic', this)">Cold Blue</div>
        </div>
    </div>

    <!-- কার্ড ৬: ভয়েস ও সাউন্ড শিফট -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🔊 ভয়েস ও সাউন্ড ফিল্টার</div>
        </div>
        <div class="chip-group" id="voiceGroup">
            <div class="chip-btn active" data-val="Original" onclick="setVoice('Original', this)">স্বাভাবিক গলা</div>
            <div class="chip-btn" data-val="Slight" onclick="setVoice('Slight', this)">সামান্য পিচ (+1.5)</div>
            <div class="chip-btn" data-val="Deep" onclick="setVoice('Deep', this)">গম্ভীর কণ্ঠ (-2.5)</div>
            <div class="chip-btn" data-val="Bright" onclick="setVoice('Bright', this)">উজ্জ্বল কণ্ঠ (+2.5)</div>
        </div>
        <div style="font-size: 0.74rem; color: #10b981; margin-top: 8px;">
            ✔ অডিও ফেজ মডুলেশন (aphaser) ও ইকুয়ালাইজার স্বয়ংক্রিয় সক্রিয় থাকবে।
        </div>
    </div>

    <!-- কার্ড ৭: ব্যাকগ্রাউন্ড মিউজিক (অ্যাকোস্টিক মাস্কার) -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🎵 ব্যাকগ্রাউন্ড মিউজিক (অ্যাকোস্টিক মাস্কার)</div>
        </div>
        <div class="chip-group" id="bgmGroup">
            <div class="chip-btn active" data-val="lofi" onclick="setBgm('lofi', this)">
                🎵 Lo-Fi Beat<br><span style="font-size:0.7rem; font-weight:normal;">সেরা বাইপাস</span>
            </div>
            <div class="chip-btn" data-val="cinematic" onclick="setBgm('cinematic', this)">
                🎬 Cinema Drone<br><span style="font-size:0.7rem; font-weight:normal;">সিনেমাটিক ড্রোন</span>
            </div>
            <div class="chip-btn" data-val="none" onclick="setBgm('none', this)">
                🔇 বন্ধ<br><span style="font-size:0.7rem; font-weight:normal;">শুধু ভয়েস</span>
            </div>
        </div>
        <div style="font-size: 0.74rem; color: #10b981; margin-top: 8px;">
            ✔ এটি অরিজিনাল অডিওর পেছনে মৃদুভাবে বেজে স্পেকট্রাম পিক বদলে দেয়—ইউটিউবের রোবট অডিও মেলাতে পারবে না।
        </div>
    </div>

    <!-- সাবমিট বাটন -->
    <button class="btn-action" id="startBtn" onclick="startProcess()" disabled>
        <span>▶</span> ১০০% কপিরাইট বাইপাস এডিট শুরু করো
    </button>

    <!-- প্রোগ্রেস ও রেজাল্ট কার্ড -->
    <div class="card progress-card" id="progressCard">
        <div style="font-size: 1.1rem; font-weight: 700;" id="progPercent">০%</div>
        <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progFill"></div>
        </div>
        <div class="status-msg" id="progStatus">প্রসেসিং চলছে...</div>

        <div class="stats-grid">
            <div class="stat-item">
                <div>সময় অতিবাহিত</div>
                <div class="stat-val" id="statElapsed">০ সে.</div>
            </div>
            <div class="stat-item">
                <div>অবশিষ্ট আনুমানিক</div>
                <div class="stat-val" id="statEta">হিসাব হচ্ছে...</div>
            </div>
        </div>

        <div class="log-box" id="logBox">লগ লোড হচ্ছে...</div>

        <!-- রেজাল্ট ভিউ -->
        <div class="result-box" id="resultBox">
            <div style="font-size: 1.4rem;">🎉</div>
            <div style="font-size: 1.05rem; font-weight: 700; color: #10b981;">১০০% বাইপাস সম্পন্ন হয়েছে!</div>
            <div style="font-size: 0.8rem; color: #cbd5e1; margin-top: 4px;" id="saveInfo">ভিডিওটি ডাউনলোড করতে নিচে ট্যাপ করুন:</div>
            <a href="#" id="downloadLink" class="btn-download" download>
                📥 মোবাইলে ডাউনলোড করুন (Save Video)
            </a>
        </div>
    </div>

</div>

<script>
    let selectedFile = null;
    let selectedStrength = "Strong";
    let selectedRes = "720p";
    let selectedGrade = "Teal & Orange";
    let selectedVoice = "Original";
    let selectedBgm = "lofi";
    let pollInterval = null;

    function handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;
        selectedFile = file;

        document.getElementById('fileName').innerText = file.name;
        document.getElementById('fileSize').innerText = (file.size / (1024 * 1024)).toFixed(1) + " MB";
        document.getElementById('fileBadge').style.display = "flex";
        document.getElementById('startBtn').disabled = false;
    }

    function clearSelectedFile() {
        selectedFile = null;
        document.getElementById('videoInput').value = "";
        document.getElementById('fileBadge').style.display = "none";
        document.getElementById('startBtn').disabled = true;
    }

    function setStrength(val, el) {
        selectedStrength = val;
        document.querySelectorAll('#strengthGroup .chip-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }

    function setRes(val, el) {
        selectedRes = val;
        document.querySelectorAll('#resGroup .chip-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }

    function setGrade(val, el) {
        selectedGrade = val;
        document.querySelectorAll('#gradeGroup .chip-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }

    function setVoice(val, el) {
        selectedVoice = val;
        document.querySelectorAll('#voiceGroup .chip-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }

    function setBgm(val, el) {
        selectedBgm = val;
        document.querySelectorAll('#bgmGroup .chip-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
    }

    async function startProcess() {
        if (!selectedFile) return;

        const startBtn = document.getElementById('startBtn');
        startBtn.disabled = true;
        startBtn.innerText = "⏳ ফাইল প্রস্তুত হচ্ছে...";

        const progressCard = document.getElementById('progressCard');
        progressCard.style.display = "block";
        progressCard.scrollIntoView({ behavior: 'smooth' });

        const formData = new FormData();
        formData.append("video", selectedFile);
        formData.append("strength", selectedStrength);
        formData.append("resolution", selectedRes);
        formData.append("grade", selectedGrade);
        formData.append("voice", selectedVoice);
        formData.append("bgm", selectedBgm);
        formData.append("mirror", document.getElementById('mirrorFlip').checked);
        formData.append("speed", document.getElementById('speedShift').checked);

        try {
            const resp = await fetch("/api/start", {
                method: "POST",
                body: formData
            });
            const data = await resp.json();
            if (data.status === "ok") {
                startBtn.innerText = "⚡ রেন্ডারিং চলছে...";
                startPolling();
            } else {
                alert("এরর: " + (data.error || "শুরু করা যায়নি"));
                startBtn.disabled = false;
                startBtn.innerText = "▶ ১০০% কপিরাইট বাইপাস এডিট শুরু করো";
            }
        } catch (err) {
            alert("সার্ভার সংযোগ সমস্যা: " + err.message);
            startBtn.disabled = false;
            startBtn.innerText = "▶ ১০০% কপিরাইট বাইপাস এডিট শুরু করো";
        }
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(async () => {
            try {
                const r = await fetch("/api/status");
                const d = await r.json();

                document.getElementById('progPercent').innerText = d.progress + "%";
                document.getElementById('progFill').style.width = d.progress + "%";
                document.getElementById('progStatus').innerText = d.status;
                document.getElementById('statElapsed').innerText = d.elapsed;
                document.getElementById('statEta').innerText = d.eta;

                if (d.logs && d.logs.length) {
                    const logBox = document.getElementById('logBox');
                    logBox.innerText = d.logs.slice(-15).join("\n");
                    logBox.scrollTop = logBox.scrollHeight;
                }

                if (!d.busy) {
                    clearInterval(pollInterval);
                    document.getElementById('startBtn').disabled = false;
                    document.getElementById('startBtn').innerText = "▶ নতুন আরেকটি ভিডিও এডিট করুন";

                    if (d.progress === 100 && d.out_filename) {
                        document.getElementById('resultBox').style.display = "block";
                        document.getElementById('downloadLink').href = "/download/" + encodeURIComponent(d.out_filename);
                        document.getElementById('resultBox').scrollIntoView({ behavior: 'smooth' });
                    }
                }
            } catch (e) {
                console.error("Polling error:", e);
            }
        }, 1000);
    }
</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, is_termux=IS_TERMUX)


@app.route("/api/start", methods=["POST"])
def api_start():
    global current_task
    if current_task["busy"]:
        return jsonify({"status": "error", "error": "আরেকটি ভিডিওর প্রসেস ইতোমধ্যে চলছে।"})

    if "video" not in request.files:
        return jsonify({"status": "error", "error": "ভিডিও ফাইল পাওয়া যায়নি"})

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"status": "error", "error": "কোনো ফাইল সিলেক্ট করা হয়নি"})

    filename = f"{int(time.time())}_{file.filename}"
    upload_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(upload_path)

    strength = request.form.get("strength", "Strong")
    resolution = request.form.get("resolution", "720p")
    grade = request.form.get("grade", "Teal & Orange")
    voice = request.form.get("voice", "Original")
    bgm = request.form.get("bgm", "lofi")
    mirror = request.form.get("mirror") == "true"
    speed = request.form.get("speed") == "true"

    bgm_path = None
    if bgm == "lofi":
        bgm_path = os.path.join(BASE_DIR, "bgm_lofi.m4a")
    elif bgm == "cinematic":
        bgm_path = os.path.join(BASE_DIR, "bgm_cinematic.m4a")

    base_name = os.path.splitext(os.path.basename(file.filename))[0]
    out_filename = f"{base_name}_100pct_bypass.mp4"
    out_path = os.path.join(OUTPUT_FOLDER, out_filename)

    current_task = {
        "busy": True,
        "progress": 0,
        "status": "ভিডিও লোড হচ্ছে...",
        "filename": file.filename,
        "out_filename": out_filename,
        "error": None,
        "start_time": time.time(),
        "elapsed": "0s",
        "eta": "হিসাব হচ্ছে...",
        "logs": [f"ফাইল গ্রহণ সম্পন্ন: {file.filename}"]
    }

    thread = threading.Thread(
        target=run_mobile_process,
        args=(upload_path, out_path, strength, resolution, grade, voice, mirror, speed, bgm_path)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "ok", "out_filename": out_filename})


def run_mobile_process(in_path, out_path, strength, resolution, grade, voice, mirror, speed, bgm_path=None):
    global current_task
    try:
        def log_cb(msg):
            current_task["logs"].append(str(msg))
            current_task["status"] = str(msg).strip()

        def prog_cb(pct):
            current_task["progress"] = pct
            elapsed = time.time() - current_task["start_time"]
            m, s = divmod(int(elapsed), 60)
            current_task["elapsed"] = f"{m}মি {s}সে" if m > 0 else f"{s}সে"

            if pct > 0:
                total_est = (elapsed / pct) * 100
                rem = max(0, int(total_est - elapsed))
                rem_m, rem_s = divmod(rem, 60)
                current_task["eta"] = f"~{rem_m}মি {rem_s}সে" if rem_m > 0 else f"~{rem_s}সে"

        pitch_map = {"Original": 0.0, "Slight": 1.5, "Deep": -2.5, "Bright": 2.5}
        pitch_val = pitch_map.get(voice, 0.0)

        dur = probe_duration(in_path)
        w, h, fps = probe_video_info(in_path)
        sr, ch = probe_audio_sr(in_path)
        has_a = has_audio(in_path)

        speed_factor = 1.025 if speed else 1.0
        effective_dur = dur / speed_factor if dur else None

        vf = build_bypass_video_filters(
            w=w, h=h,
            bypass_strength=strength,
            speed_factor=speed_factor,
            mirror=mirror,
            resolution_mode=resolution,
            grade_name=grade,
            grade_intensity=65.0
        )

        af = None
        if has_a:
            af = build_bypass_audio_filters(
                sr=sr,
                voice_preset=voice,
                pitch_steps=pitch_val,
                speed_factor=speed_factor,
                enable_aphaser=True,
                enable_eq=True
            )

        log_cb("  ⚡ 100% Copyright Bypass শুরু হচ্ছে...")

        has_bgm = bool(bgm_path and os.path.exists(bgm_path))
        if has_bgm:
            log_cb(f"  🎵 ব্যাকগ্রাউন্ড মিউজিক অ্যাকোস্টিক মাস্কার যুক্ত হচ্ছে ({os.path.basename(bgm_path)})...")

        enc_list = DETECTED_ENCODERS
        selected_encoder = None
        last_err = ""

        for enc in enc_list:
            log_cb(f"  এনকোডার পরীক্ষা: {enc['name']}...")
            if has_bgm:
                bgm_vol = 0.10
                if has_a:
                    f_complex = f"[0:v]{vf}[v_out];[0:a]{af}[a_proc];[1:a]volume={bgm_vol:.3f}[bgm_proc];[a_proc][bgm_proc]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
                else:
                    f_complex = f"[0:v]{vf}[v_out];[1:a]volume={bgm_vol:.3f}[a_out]"
                cmd = [
                    FFMPEG, "-y",
                    "-i", in_path,
                    "-stream_loop", "-1", "-i", bgm_path,
                    "-filter_complex", f_complex,
                    "-map", "[v_out]", "-map", "[a_out]",
                    "-c:a", "aac", "-b:a", "192k",
                ] + enc["opts"] + [
                    "-map_metadata", "-1",
                    "-movflags", "+faststart",
                    "-nostats", "-progress", "pipe:1",
                    out_path
                ]
            else:
                cmd = [
                    FFMPEG, "-y",
                    "-i", in_path,
                    "-vf", vf,
                ]
                if af:
                    cmd += ["-af", af, "-c:a", "aac", "-b:a", "192k"]
                else:
                    cmd += ["-an"]

                cmd += enc["opts"] + [
                    "-map_metadata", "-1",
                    "-movflags", "+faststart",
                    "-nostats", "-progress", "pipe:1",
                    out_path
                ]

            try:
                run_ffmpeg_progress(cmd, effective_dur, prog_cb, log_cb)
                selected_encoder = enc
                log_cb(f"  ✔ সফলভাবে এনকোড সম্পন্ন হয়েছে ({enc['name']} দিয়ে)")
                break
            except Exception as e:
                last_err = str(e)
                log_cb(f"  ⚠ {enc['name']} ব্যর্থ, অন্য এনকোডার দিয়ে চেষ্টা চলছে...")
                if os.path.exists(out_path):
                    try:
                        os.remove(out_path)
                    except Exception:
                        pass

        if not selected_encoder:
            raise RuntimeError("সব এনকোডার ব্যর্থ:\n" + last_err)

        current_task["progress"] = 100
        current_task["status"] = "১০০% কপিরাইট বাইপাস সম্পন্ন!"
        current_task["logs"].append("✔ সফলভাবে ভিডিও প্রস্তুত হয়েছে।")

    except Exception as ex:
        current_task["error"] = str(ex)
        current_task["status"] = f"এরর: {str(ex)[:80]}"
        current_task["logs"].append(f"❌ এরর: {ex}")
    finally:
        current_task["busy"] = False
        if os.path.exists(in_path):
            try:
                os.remove(in_path)
            except Exception:
                pass


@app.route("/api/status")
def api_status():
    global current_task
    return jsonify(current_task)


@app.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)


def main():
    ip = get_local_ip()
    port = 5000
    print("=" * 65)
    print("  ⚡ Video Studio Pro — Mobile & Termux Server ⚡")
    print("=" * 65)
    if IS_TERMUX:
        print("\n  📱 Android Termux মোড সক্রিয়!")
        print(f"\n     👉  http://localhost:{port}  বা  http://127.0.0.1:{port}  👈\n")
        print("  ভিডিও সরাসরি আপনার ফোনের Download ফোল্ডারে সেভ হবে।")
    else:
        print(f"\n  📱 আপনার মোবাইল (Android / iPhone) এর ব্রাউজারে প্রবেশ করুন:\n")
        print(f"     👉  http://{ip}:{port}  👈\n")
        print("  (মোবাইল ও পিসি একই Wi-Fi / Hotspot এ যুক্ত রাখুন)")
    print("=" * 65)

    # Termux-এ চললে অটোমেটিক ব্রাউজার ওপেন করার চেষ্টা
    if IS_TERMUX:
        try:
            subprocess.Popen(["termux-open-url", f"http://localhost:{port}"])
        except Exception:
            pass

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
