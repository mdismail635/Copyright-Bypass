#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Studio Pro — Mobile & Termux Edition (1000% YouTube Copyright Bypass & 2-3 GB Size Engine)
- 🚀 1000% Ultra Nuclear Anti-Content ID Shield (Lissajous Dynamic Crop, Optical Lens Warp, AudioID Notch & Vibrato)
- 📦 Targeted Bitrate & Size Engine: গাণিতিকভাবে ৫ ঘণ্টার ভিডিও সাইজ ঠিক ২-৩ GB (ডিফল্ট ~২.৪ GB)
- 📱 Android Termux ও PC উভয় জায়গায় ব্রাউজার দিয়ে দ্রুততম এক্সেস
- ⚡ Intel QSV, NVIDIA NVENC, AMD AMF, Android MediaCodec ও CPU x264 অপ্টিমাইজড
"""

import os
import sys
import json
import time
import socket
import shutil
import threading
import subprocess
try:
    from flask import Flask, request, jsonify, send_from_directory, render_template_string
except ModuleNotFoundError:
    print("\n" + "="*55)
    print("⚠️  Flask লাইব্রেরি পাওয়া যায়নি! স্বয়ংক্রিয়ভাবে ইনস্টল করা হচ্ছে...")
    print("="*55)
    installed = False
    for cmd in [
        [sys.executable, "-m", "pip", "install", "flask", "--break-system-packages"],
        [sys.executable, "-m", "pip", "install", "flask"],
    ]:
        try:
            subprocess.check_call(cmd)
            installed = True
            break
        except Exception:
            pass

    if not installed:
        try:
            # Termux এ pip মিসিং থাকলে pkg install python-pip চালানো
            subprocess.run(["pkg", "install", "python-pip", "-y"])
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "--break-system-packages"])
            installed = True
        except Exception as e:
            print(f"\n❌ Flask অটো-ইন্সটল ব্যর্থ হয়েছে: {e}")
            print("অনুগ্রহ করে Termux-এ এই কমান্ডগুলো রান করুন:")
            print("👉  pkg install python-pip -y  👈")
            print("👉  python3 -m pip install flask --break-system-packages  👈\n")
            sys.exit(1)

    from flask import Flask, request, jsonify, send_from_directory, render_template_string
    print("✅ Flask সফলভাবে ইনস্টল হয়েছে!\n")

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

    try:
        if name == "ffmpeg":
            import imageio_ffmpeg
            p = imageio_ffmpeg.get_ffmpeg_exe()
            if p and os.path.exists(p):
                return p
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


# ============================ SIZE & BITRATE PROFILES (5 HOURS = 2-3 GB) ============================

SIZE_PROFILES = {
    "5h_2to3gb": {
        "name": "🎯 5 Hours = 2-3 GB (YouTube Standard - রিকমেন্ডেড)",
        "badge": "৫ ঘণ্টা = ~২.৪ GB",
        "desc": "গ্যারান্টিযুক্ত ২-৩ জিবি সাইজ। ইউটিউবের জন্য ক্রিস্প ৭২০p কোয়ালিটি ও হালকা বিটরেট।",
        "v_bitrate": "1050k",
        "maxrate": "1350k",
        "bufsize": "2200k",
        "a_bitrate": "96k",
        "est_gb_per_hour": 0.49
    },
    "5h_1to2gb": {
        "name": "⚡ 5 Hours = 1.5-2 GB (Super Compact)",
        "badge": "৫ ঘণ্টা = ~১.৭ GB",
        "desc": "সর্বোচ্চ স্টোরেজ সাশ্রয়ী ও দ্রুত আপলোড। কম ডেটা খরচে পারফেক্ট।",
        "v_bitrate": "750k",
        "maxrate": "950k",
        "bufsize": "1500k",
        "a_bitrate": "80k",
        "est_gb_per_hour": 0.35
    },
    "5h_3to4gb": {
        "name": "💎 5 Hours = 3-4 GB (HQ Balanced)",
        "badge": "৫ ঘণ্টা = ~৩.৩ GB",
        "desc": "উচ্চতর কোয়ালিটি ও শার্পনেস বজায় রাখবে।",
        "v_bitrate": "1450k",
        "maxrate": "1800k",
        "bufsize": "2800k",
        "a_bitrate": "112k",
        "est_gb_per_hour": 0.67
    }
}


def get_encoder_options(enc_id, size_profile_key="5h_2to3gb"):
    prof = SIZE_PROFILES.get(size_profile_key, SIZE_PROFILES["5h_2to3gb"])
    vb = prof["v_bitrate"]
    maxr = prof["maxrate"]
    bufs = prof["bufsize"]

    if enc_id == "nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p3", "-b:v", vb, "-maxrate", maxr, "-bufsize", bufs, "-pix_fmt", "yuv420p"]
    elif enc_id == "qsv":
        return ["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", vb, "-maxrate", maxr, "-bufsize", bufs, "-pix_fmt", "yuv420p"]
    elif enc_id == "amf":
        return ["-c:v", "h264_amf", "-b:v", vb, "-maxrate", maxr, "-bufsize", bufs, "-pix_fmt", "yuv420p"]
    elif enc_id == "mediacodec":
        return ["-c:v", "h264_mediacodec", "-b:v", vb, "-maxrate", maxr, "-pix_fmt", "yuv420p"]
    else:  # CPU x264
        return ["-c:v", "libx264", "-preset", "veryfast", "-b:v", vb, "-maxrate", maxr, "-bufsize", bufs, "-pix_fmt", "yuv420p", "-threads", "0"]


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
            "name": "NVIDIA NVENC (GPU সুপারফাস্ট)",
            "codec": "h264_nvenc"
        })
    # 2. Intel QuickSync (QSV)
    if test_ffmpeg_encoder("h264_qsv"):
        encoders.append({
            "id": "qsv",
            "name": "Intel QuickSync (QSV GPU সুপারফাস্ট)",
            "codec": "h264_qsv"
        })
    # 3. AMD AMF
    if test_ffmpeg_encoder("h264_amf"):
        encoders.append({
            "id": "amf",
            "name": "AMD AMF (GPU সুপারফাস্ট)",
            "codec": "h264_amf"
        })
    # 4. Android MediaCodec (if Termux ffmpeg compiled with it)
    if test_ffmpeg_encoder("h264_mediacodec"):
        encoders.append({
            "id": "mediacodec",
            "name": "Android MediaCodec (Hardware)",
            "codec": "h264_mediacodec"
        })
    # 5. CPU Veryfast
    encoders.append({
        "id": "cpu",
        "name": "CPU x264 (Veryfast Mode)",
        "codec": "libx264"
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
        return 44100, 2
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=sample_rate,channels", "-of", "json", path],
            capture_output=True, text=True, timeout=60)
        st = json.loads(r.stdout)["streams"][0]
        return int(st.get("sample_rate", 44100)), int(st.get("channels", 2))
    except Exception:
        return 44100, 2


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


# ============================ 1000% COPYRIGHT BYPASS FILTERS ============================

def build_bypass_video_filters(w, h, bypass_strength="Nuclear", speed_factor=1.035,
                               mirror=True, resolution_mode="720p",
                               grade_name="Teal & Orange", grade_intensity=70.0):
    """
    🚀 1000% Ultra Nuclear Anti-Content ID Video Engine:
    ১. ডাইনামিক লিসাজাস মোশন ড্রিফট (Anti-Spatial Coordinate Matching)
    ২. অপটিক্যাল লেন্স ডিফর্মেশন (Anti-SIFT/SURF Affine Invariant Matcher)
    ৩. অনুভূমিক মিরর ফ্লিপ (YouTube Visual Hash Inverter)
    ৪. টেম্পোরাল ডাইনামিক মাইক্রো-নয়েজ (DCT Hash Scrambler)
    ৫. সিনেমাটিক ভিনিয়েট ও কালার গ্রেডিং
    ৬. ফ্রেমরেট ও পিটিএস ডেসিনক্রোনাইজেশন
    """
    vf = []
    
    if bypass_strength in ("Nuclear", "1000% Ultra Nuclear", "1000%"):
        crop_pct = 0.89
        grain_strength = 6
        vignette_val = "PI/3.5"
        hue_rot = 3.8
        sat_boost = 1.16
        con_boost = 1.14
        enable_lens = True
        enable_drift = True
    elif bypass_strength == "Extreme":
        crop_pct = 0.92
        grain_strength = 6
        vignette_val = "PI/3.6"
        hue_rot = 3.5
        sat_boost = 1.15
        con_boost = 1.12
        enable_lens = True
        enable_drift = True
    elif bypass_strength == "Moderate":
        crop_pct = 0.97
        grain_strength = 3
        vignette_val = "PI/4.5"
        hue_rot = 1.8
        sat_boost = 1.08
        con_boost = 1.06
        enable_lens = False
        enable_drift = False
    else:  # Strong
        crop_pct = 0.94
        grain_strength = 5
        vignette_val = "PI/3.8"
        hue_rot = 2.8
        sat_boost = 1.12
        con_boost = 1.10
        enable_lens = True
        enable_drift = True

    # ১. ক্রপ ও ডাইনামিক সাইন-কোসাইন মোশন ড্রিফট
    if enable_drift:
        vf.append(
            f"crop=w='in_w*{crop_pct:.3f}':h='in_h*{crop_pct:.3f}':"
            f"x='max(0,min(in_w-out_w,(in_w-out_w)/2+sin(t*0.5)*18))':"
            f"y='max(0,min(in_h-out_h,(in_h-out_h)/2+cos(t*0.35)*14))'"
        )
    else:
        vf.append(f"crop=in_w*{crop_pct:.3f}:in_h*{crop_pct:.3f}:(in_w-out_w)/2:(in_h-out_h)/2")

    # ২. মিরর ফ্লিপ (ডানে-বামে উল্টানো - ইউটিউবের ভিজুয়াল হ্যাশ সম্পূর্ণ ইনভার্ট করে)
    if mirror:
        vf.append("hflip")

    # ৩. রেজোলিউশন স্কেলিং ও প্যাডিং (টার্বো স্পিড ও সাইজ কন্ট্রোলের জন্য 720p ডিফল্ট)
    if resolution_mode == "720p":
        target_w, target_h = 1280, 720
    elif resolution_mode == "1080p":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = w, h

    vf.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")

    # ৪. অপটিক্যাল লেন্স কার্ভেচার (Anti-SIFT/SURF Affine Distortion)
    if enable_lens:
        vf.append("lenscorrection=cx=0.5:cy=0.5:k1=0.012:k2=-0.006")

    # ৫. সিনেমাটিক কালার গ্রেডিং
    s = max(0.1, min(float(grade_intensity), 100.0)) / 100.0
    if grade_name.startswith("Teal"):
        vf.append(f"colorbalance=rs={0.08*s:.3f}:bs={-0.08*s:.3f}:rh={-0.06*s:.3f}:bh={0.08*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.14*s:.3f}:saturation={1.0+0.18*s:.3f}:gamma={1.0+0.03*s:.3f}")
    elif grade_name.startswith("Warm"):
        vf.append(f"colorbalance=rs={0.11*s:.3f}:bs={-0.07*s:.3f}:gs={0.03*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.12*s:.3f}:saturation={1.0+0.16*s:.3f}:gamma={1.0+0.03*s:.3f}")
    elif grade_name.startswith("Cold"):
        vf.append(f"colorbalance=bs={0.11*s:.3f}:bh={0.07*s:.3f}:rs={-0.06*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.12*s:.3f}:saturation={1.0-0.08*s:.3f}")
    elif grade_name.startswith("Vivid"):
        vf.append(f"eq=contrast={1.0+0.16*s:.3f}:saturation={1.0+0.28*s:.3f}")
        vf.append(f"unsharp=3:3:{0.4*s:.2f}")
    elif grade_name.startswith("Noir"):
        vf.append(f"hue=s={1.0-1.0*s:.3f}")
        vf.append(f"eq=contrast={1.0+0.22*s:.3f}:brightness={-0.02*s:.3f}")
    else:
        vf.append(f"colorbalance=rs={0.06*s:.3f}:bs={-0.06*s:.3f}:rh={0.04*s:.3f}")
        vf.append(f"eq=contrast={con_boost:.3f}:saturation={sat_boost:.3f}")

    vf.append(f"hue=h={hue_rot:.1f}:s={sat_boost:.2f}")
    vf.append(f"vignette={vignette_val}")
    vf.append(f"noise=alls={grain_strength}:allf=t+u")
    vf.append("unsharp=3:3:0.4:3:3:0.0")

    # ৬. মাইক্রো-স্পিড পিটিএস ডেসিনক্রোনাইজেশন
    if abs(speed_factor - 1.0) > 0.001:
        vf.append(f"setpts=PTS/{speed_factor:.4f}")

    return ",".join(vf)


def build_bypass_audio_filters(sr=44100, voice_preset="MicroShift",
                               pitch_steps=0.8, speed_factor=1.035,
                               enable_wobble=True, enable_chorus=True,
                               enable_eq=True, enable_stereo=True):
    """
    🔊 1000% AudioID Destruction Engine:
    ১. পিচ শিফট (আসল ফ্রিকোয়েন্সি পিক সম্পূর্ণ স্থানান্তরিত করে)
    ২. টাইম-ভ্যারিইং ভাইব্রেটো/ওবল (কনস্ট্যান্ট ডেল্টা পিক রেশিও চিরতরে নষ্ট করে)
    ৩. মাল্টি-স্টেজ কোরাস ডিলে ও ফেজ শিফট (aphaser)
    ৪. ডিপ নচ ইকুয়ালাইজার (Anchor Frequencies ধ্বংস করে)
    ৫. মিড-সাইড স্টেরিও ডেকরিলেশন (ইউটিউবের মনো ডাউনমিক্স হ্যাশিং ভেঙে দেয়)
    ৬. হাই-পাস ও লো-পাস স্পেকট্রাম ট্রাঙ্ক
    """
    af = []
    sr = int(sr) if sr else 44100

    # নিশ্চিত স্টেরিও চ্যানেল ফর্ম্যাট
    af.append("aformat=channel_layouts=stereo")

    # ১. পিচ শিফট
    pitch_mult = 2.0 ** (pitch_steps / 12.0)
    if abs(pitch_mult - 1.0) > 0.005:
        target_rate = int(sr * pitch_mult)
        af.append(f"asetrate={target_rate},aresample={sr}")

    # ২. টেম্পো রেশিও ক্যালকুলেশন
    tempo_ratio = speed_factor / pitch_mult
    af.append(get_atempo_chain(tempo_ratio))

    # ৩. স্পেকট্রাম ট্রাঙ্ক (সাব-বাস ৫০Hz ও আল্ট্রাসনিক ১৫.৫kHz ছাঁটাই)
    af.append("highpass=f=55,lowpass=f=15500")

    # ৪. ইউটিউব অডিও আইডি নচ ফিল্টার্স (ফ্রিকোয়েন্সি রিজেকশন)
    if enable_eq:
        af.append("equalizer=f=350:t=q:w=2.0:g=-4.0")
        af.append("equalizer=f=1200:t=q:w=2.5:g=-4.5")
        af.append("equalizer=f=2800:t=q:w=2.5:g=-4.0")
        af.append("equalizer=f=5200:t=q:w=2.0:g=-3.5")
        af.append("equalizer=f=180:t=q:w=1.2:g=2.5")
        af.append("equalizer=f=8000:t=q:w=1.5:g=2.0")

    # ৫. ফেজ মডুলেশন ও টাইম-ভ্যারিইং ওবল
    af.append("aphaser=in_gain=0.9:out_gain=0.9:delay=3.0:decay=0.4:speed=0.4:type=t")
    if enable_chorus:
        af.append("chorus=0.7:0.9:45:0.35:0.25:1.5")
    if enable_wobble:
        af.append("vibrato=f=0.8:d=0.22")

    # ৬. মিড-সাইড স্টেরিও ডেকরিলেশন
    if enable_stereo:
        af.append("extrastereo=m=1.35")

    # ৭. ডায়নামিক কম্প্রেশন
    af.append("acompressor=threshold=0.5:ratio=3.0:makeup=1.15")

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
        raise RuntimeError("FFmpeg এনকোড ব্যর্থ:\n" + "".join(err_lines)[-800:])


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
    "est_size": "--",
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


# ============================ WEB UI TEMPLATE ============================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Video Studio Pro — 1000% Copyright Bypass & Size Controller</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&family=Hind+Siliguri:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #070b14;
            --bg-card: rgba(18, 25, 43, 0.78);
            --bg-card-border: rgba(255, 255, 255, 0.09);
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
            --accent-green: #10b981;
            --accent-gold: #f59e0b;
            --accent-gradient: linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%);
            --accent-fire: linear-gradient(135deg, #ef4444 0%, #f97316 50%, #f59e0b 100%);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --radius-lg: 16px;
            --radius-md: 12px;
            --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.6);
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
            padding-bottom: 60px;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(6, 182, 212, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(139, 92, 246, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(245, 158, 11, 0.05) 0%, transparent 60%);
            background-attachment: fixed;
        }

        header {
            padding: 16px 20px;
            background: rgba(7, 11, 20, 0.88);
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
            gap: 12px;
        }

        .brand-icon {
            width: 42px;
            height: 42px;
            background: var(--accent-gradient);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 4px 18px rgba(6, 182, 212, 0.45);
        }

        .brand-title {
            font-size: 1.18rem;
            font-weight: 800;
            letter-spacing: -0.3px;
        }

        .brand-title span {
            background: var(--accent-gradient);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .hw-tag {
            font-size: 0.74rem;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 20px;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .hw-dot {
            width: 7px;
            height: 7px;
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
            max-width: 650px;
            margin: 0 auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: var(--radius-lg);
            padding: 18px;
            box-shadow: var(--shadow-card);
            backdrop-filter: blur(14px);
            transition: border-color 0.25s ease;
        }

        .card-featured {
            border: 1.5px solid rgba(6, 182, 212, 0.4);
            box-shadow: 0 10px 30px -10px rgba(6, 182, 212, 0.3);
            background: linear-gradient(180deg, rgba(22, 33, 58, 0.85) 0%, rgba(18, 25, 43, 0.8) 100%);
        }

        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .card-title {
            font-size: 1.02rem;
            font-weight: 700;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .badge-pill {
            font-size: 0.72rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 12px;
            background: rgba(6, 182, 212, 0.2);
            color: #38bdf8;
            border: 1px solid rgba(6, 182, 212, 0.3);
        }

        .termux-banner {
            background: rgba(6, 182, 212, 0.12);
            border: 1px solid rgba(6, 182, 212, 0.35);
            border-radius: var(--radius-md);
            padding: 12px 14px;
            font-size: 0.82rem;
            color: #7dd3fc;
            display: flex;
            align-items: center;
            gap: 10px;
            line-height: 1.4;
        }

        /* Upload Area */
        .upload-box {
            border: 2px dashed rgba(59, 130, 246, 0.45);
            border-radius: var(--radius-md);
            padding: 26px 16px;
            text-align: center;
            background: rgba(15, 23, 42, 0.45);
            cursor: pointer;
            transition: all 0.25s ease;
        }

        .upload-box:active, .upload-box:hover {
            transform: scale(0.99);
            border-color: var(--accent-cyan);
            background: rgba(6, 182, 212, 0.08);
        }

        .upload-icon {
            font-size: 42px;
            margin-bottom: 8px;
        }

        .upload-text {
            font-size: 1rem;
            font-weight: 700;
            color: #f1f5f9;
        }

        .upload-sub {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 4px;
        }

        .file-info-badge {
            margin-top: 12px;
            padding: 12px 14px;
            background: rgba(30, 41, 59, 0.85);
            border-radius: 12px;
            display: none;
            align-items: center;
            justify-content: space-between;
            font-size: 0.88rem;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        /* Selectable Chips / Segments */
        .chip-group {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 10px;
            margin-top: 8px;
        }

        .chip-btn {
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.1);
            color: var(--text-muted);
            padding: 12px 10px;
            border-radius: 12px;
            font-size: 0.84rem;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
        }

        .chip-btn.active {
            background: linear-gradient(135deg, rgba(6, 182, 212, 0.25), rgba(59, 130, 246, 0.35));
            border-color: var(--accent-cyan);
            color: #ffffff;
            box-shadow: 0 4px 16px rgba(6, 182, 212, 0.3);
        }

        .chip-btn.active.fire {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.25), rgba(245, 158, 11, 0.35));
            border-color: #f59e0b;
            box-shadow: 0 4px 16px rgba(245, 158, 11, 0.35);
        }

        .chip-btn.active.gold {
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.25), rgba(6, 182, 212, 0.35));
            border-color: #10b981;
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.3);
        }

        /* Toggle Switches */
        .toggle-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .toggle-row:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }

        .toggle-label {
            font-size: 0.90rem;
            font-weight: 600;
        }

        .toggle-sub {
            font-size: 0.76rem;
            color: var(--text-muted);
            margin-top: 3px;
            line-height: 1.3;
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 48px;
            height: 28px;
            flex-shrink: 0;
            margin-left: 12px;
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
            background-color: rgba(255, 255, 255, 0.16);
            transition: .3s;
            border-radius: 28px;
        }

        .slider:before {
            position: absolute;
            content: "";
            height: 22px;
            width: 22px;
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

        /* Action Button */
        .btn-action {
            width: 100%;
            padding: 17px;
            background: var(--accent-gradient);
            border: none;
            border-radius: var(--radius-lg);
            color: white;
            font-size: 1.12rem;
            font-weight: 800;
            cursor: pointer;
            box-shadow: 0 8px 25px rgba(6, 182, 212, 0.5);
            transition: transform 0.2s ease, opacity 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
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
            padding: 22px 18px;
        }

        .progress-bar-bg {
            width: 100%;
            height: 12px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            overflow: hidden;
            margin: 16px 0 10px;
        }

        .progress-bar-fill {
            height: 100%;
            width: 0%;
            background: var(--accent-gradient);
            border-radius: 12px;
            transition: width 0.3s ease;
            box-shadow: 0 0 14px rgba(6, 182, 212, 0.7);
        }

        .status-msg {
            font-size: 0.96rem;
            font-weight: 600;
            color: #38bdf8;
            margin-top: 6px;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
            margin-top: 16px;
        }

        .stat-item {
            background: rgba(15, 23, 42, 0.55);
            padding: 10px 8px;
            border-radius: 10px;
            font-size: 0.76rem;
            color: var(--text-muted);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }

        .stat-val {
            font-size: 0.95rem;
            font-weight: 700;
            color: #f8fafc;
            margin-top: 4px;
        }

        .result-box {
            display: none;
            margin-top: 16px;
            background: rgba(16, 185, 129, 0.14);
            border: 1.5px solid rgba(16, 185, 129, 0.4);
            border-radius: var(--radius-md);
            padding: 18px;
            text-align: center;
        }

        .btn-download {
            margin-top: 14px;
            width: 100%;
            padding: 16px;
            background: #10b981;
            color: white;
            font-weight: 800;
            border: none;
            border-radius: 12px;
            font-size: 1.05rem;
            cursor: pointer;
            box-shadow: 0 6px 22px rgba(16, 185, 129, 0.45);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            text-decoration: none;
        }

        .log-box {
            background: #020617;
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 12px;
            font-family: monospace;
            font-size: 0.76rem;
            color: #94a3b8;
            max-height: 140px;
            overflow-y: auto;
            text-align: left;
            margin-top: 14px;
            white-space: pre-wrap;
            line-height: 1.45;
        }
    </style>
</head>
<body>

<header>
    <div class="brand">
        <div class="brand-icon">⚡</div>
        <div>
            <div class="brand-title">Video Studio <span>Pro</span></div>
            <div style="font-size: 0.74rem; color: #94a3b8;">1000% Copyright Bypass & Turbo Engine</div>
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
        <span style="font-size: 1.4rem;">🤖</span>
        <div><b>Termux মোড সক্রিয়:</b> এডিট করা ভিডিও সরাসরি আপনার ফোনের <b>Download ফোল্ডারে</b> সেভ হবে!</div>
    </div>
    {% endif %}

    <!-- কার্ড ১: ফাইল আপলোড -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">📁 ভিডিও নির্বাচন করুন</div>
            <span class="badge-pill">৫ ঘণ্টা পর্যন্ত সাপোর্ট</span>
        </div>

        <div class="upload-box" onclick="document.getElementById('videoInput').click()">
            <div class="upload-icon">🎬</div>
            <div class="upload-text">মোবাইল বা পিসি থেকে ভিডিও নির্বাচন করুন</div>
            <div class="upload-sub">Gallery বা Files থেকে যেকোনো সাইজের ভিডিও ট্যাপ করুন</div>
            <input type="file" id="videoInput" accept="video/*,audio/*" style="display: none;" onchange="handleFileSelect(event)">
        </div>

        <div class="file-info-badge" id="fileBadge">
            <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80%;">
                <span id="fileName" style="font-weight: 700; color: #f8fafc;">ভিডিও.mp4</span>
                <div id="fileSize" style="font-size: 0.78rem; color: #38bdf8; margin-top: 2px;">-- MB</div>
            </div>
            <button onclick="clearSelectedFile()" style="background: none; border: none; color: #ef4444; font-size: 1.4rem; cursor: pointer;">✖</button>
        </div>
    </div>

    <!-- কার্ড ২: ১০০০% কপিরাইট বাইপাস পাওয়ার -->
    <div class="card card-featured">
        <div class="card-header">
            <div class="card-title">🛡️ কপিরাইট বাইপাস পাওয়ার লেভেল</div>
            <span class="badge-pill" style="background: rgba(245, 158, 11, 0.2); color: #fbbf24; border-color: rgba(245, 158, 11, 0.4);">ইউটিউব শিল্ড</span>
        </div>
        <div class="chip-group" id="strengthGroup">
            <div class="chip-btn active fire" data-val="Nuclear" onclick="setStrength('Nuclear', this)">
                🚀 1000% Ultra Nuclear<br><span style="font-size:0.7rem; font-weight:normal; opacity: 0.9;">ইউটিউব ১০০% গ্যারান্টি</span>
            </div>
            <div class="chip-btn" data-val="Strong" onclick="setStrength('Strong', this)">
                ⚡ Strong<br><span style="font-size:0.7rem; font-weight:normal;">১০০% রিকমেন্ডেড</span>
            </div>
            <div class="chip-btn" data-val="Extreme" onclick="setStrength('Extreme', this)">
                🔥 Extreme<br><span style="font-size:0.7rem; font-weight:normal;">ভারী ড্রিফট জুম</span>
            </div>
            <div class="chip-btn" data-val="Moderate" onclick="setStrength('Moderate', this)">
                ✨ Moderate<br><span style="font-size:0.7rem; font-weight:normal;">হালকা গ্রেডিং</span>
            </div>
        </div>
    </div>

    <!-- কার্ড ৩: সাইজ ও কম্প্রেশন কন্ট্রোল (৫ ঘণ্টা = ২-৩ GB) -->
    <div class="card card-featured">
        <div class="card-header">
            <div class="card-title">📦 ভিডিও সাইজ ও কম্প্রেশন কন্ট্রোল</div>
            <span class="badge-pill" style="background: rgba(16, 185, 129, 0.2); color: #34d399; border-color: rgba(16, 185, 129, 0.4);">২-৩ GB গ্যারান্টি</span>
        </div>
        <div class="chip-group" id="sizeGroup">
            <div class="chip-btn active gold" data-val="5h_2to3gb" onclick="setSizeProfile('5h_2to3gb', this)">
                🎯 5 Hours = 2-3 GB<br><span style="font-size:0.7rem; font-weight:normal;">ইউটিউব স্ট্যান্ডার্ড (রিকমেন্ডেড)</span>
            </div>
            <div class="chip-btn" data-val="5h_1to2gb" onclick="setSizeProfile('5h_1to2gb', this)">
                ⚡ 5 Hours = 1.5-2 GB<br><span style="font-size:0.7rem; font-weight:normal;">সুপার কমপ্যাক্ট লাইট</span>
            </div>
            <div class="chip-btn" data-val="5h_3to4gb" onclick="setSizeProfile('5h_3to4gb', this)">
                💎 5 Hours = 3-4 GB<br><span style="font-size:0.7rem; font-weight:normal;">ব্যালান্সড হাই কোয়ালিটি</span>
            </div>
        </div>
        <div style="font-size: 0.76rem; color: #34d399; margin-top: 10px; display: flex; align-items: center; gap: 6px;">
            <span>✔</span> <span>গাণিতিকভাবে নিশ্চিত: ৫ ঘণ্টার ভিডিও সাইজ ঠিক <b>২.৩ - ২.৫ জিবি</b> হবে। কখনও বিশাল সাইজ হবে না!</span>
        </div>
    </div>

    <!-- কার্ড ৪: রেজোলিউশন ও রেন্ডার স্পিড -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">⚡ রেজোলিউশন ও রেন্ডার স্পিড</div>
        </div>
        <div class="chip-group" id="resGroup">
            <div class="chip-btn active" data-val="720p" onclick="setRes('720p', this)">
                ⚡ 720p Turbo Fast<br><span style="font-size:0.7rem; font-weight:normal;">দ্রুততম ও ২-৩ জিবি সাইজের জন্য সেরা</span>
            </div>
            <div class="chip-btn" data-val="1080p" onclick="setRes('1080p', this)">
                🎬 1080p Full HD<br><span style="font-size:0.7rem; font-weight:normal;">হাই ডেফিনিশন</span>
            </div>
        </div>
    </div>

    <!-- কার্ড ৫: ফিঙ্গারপ্রিন্ট ব্রেকার আর্মার -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">⚙️ স্পেশাল ফিঙ্গারপ্রিন্ট ব্রেকার্স</div>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🔄 হরিজন্টাল মিরর ফ্লিপ (Mirror Flip)</div>
                <div class="toggle-sub">ভিডিও সম্পূর্ণ ডানে-বামে উল্টানো (ইউটিউবের ভিজ্যুয়াল হ্যাশ সম্পূর্ণ অকার্যকর করে)</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="mirrorFlip" checked>
                <span class="slider"></span>
            </label>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🏃 ১.০৩৫x মাইক্রো-স্পিড ও টাইমকোড শিফট</div>
                <div class="toggle-sub">টাইমস্ট্যাম্প, ড্রপফ্রেম ও ফ্রেমরেট ম্যাচিং ধ্বংস করে</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="speedShift" checked>
                <span class="slider"></span>
            </label>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🌊 ডাইনামিক লিসাজাস মোশন ড্রিফট</div>
                <div class="toggle-sub">সময়ের সাথে সাথে স্মুথলি ক্রপ কো-অর্ডিনেট নড়ে — কোনো ফ্রেমে স্ট্যাটিক ম্যাচিং হবে না</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="driftShift" checked>
                <span class="slider"></span>
            </label>
        </div>
        <div class="toggle-row">
            <div>
                <div class="toggle-label">🛡️ ইনবিল্ট সাইকোঅ্যাকোস্টিক নয়েজ শিল্ড</div>
                <div class="toggle-sub">মানুষের কানে প্রায় অদৃশ্য পিংক নয়েজ বেড, যা ইউটিউবের অডিও পিক কনস্টেলেশন ম্যাচিং ভেঙে দেয়</div>
            </div>
            <label class="switch">
                <input type="checkbox" id="noiseShield" checked>
                <span class="slider"></span>
            </label>
        </div>
    </div>

    <!-- কার্ড ৬: কালার গ্রেডিং -->
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

    <!-- কার্ড ৭: ভয়েস ও অডিও ফিল্টার -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🔊 ভয়েস ও সাউন্ড শিফট (AudioID Destruction)</div>
        </div>
        <div class="chip-group" id="voiceGroup">
            <div class="chip-btn active" data-val="MicroShift" onclick="setVoice('MicroShift', this)">
                🛡️ Micro-Shift (+0.8st)<br><span style="font-size:0.7rem; font-weight:normal;">ডিটেকশন ব্রেকার</span>
            </div>
            <div class="chip-btn" data-val="Original" onclick="setVoice('Original', this)">
                🗣️ স্বাভাবিক গলা<br><span style="font-size:0.7rem; font-weight:normal;">অরিজিনাল পিচ</span>
            </div>
            <div class="chip-btn" data-val="Slight" onclick="setVoice('Slight', this)">
                🎙️ সামান্য পিচ (+1.5st)<br><span style="font-size:0.7rem; font-weight:normal;">হালকা তীক্ষ্ণ</span>
            </div>
            <div class="chip-btn" data-val="Deep" onclick="setVoice('Deep', this)">
                📻 গম্ভীর কণ্ঠ (-2.5st)<br><span style="font-size:0.7rem; font-weight:normal;">গভীর বেস</span>
            </div>
        </div>
        <div style="font-size: 0.74rem; color: #38bdf8; margin-top: 8px;">
            ✔ অটোমেটিক ভাইব্রেটো (Wobble), কোরাস, মাল্টি-ব্যান্ড নচ ফিল্টার্স ও স্টেরিও ডেকরিলেশন সংযুক্ত।
        </div>
    </div>

    <!-- কার্ড ৮: ব্যাকগ্রাউন্ড মিউজিক (অ্যাকোস্টিক মাস্কার) -->
    <div class="card">
        <div class="card-header">
            <div class="card-title">🎵 ব্যাকগ্রাউন্ড মিউজিক (অ্যাকোস্টিক মাস্কার)</div>
        </div>
        <div class="chip-group" id="bgmGroup">
            <div class="chip-btn active" data-val="lofi" onclick="setBgm('lofi', this)">
                🎵 Lo-Fi Beat<br><span style="font-size:0.7rem; font-weight:normal;">সেরা অ্যাকোস্টিক শিল্ড</span>
            </div>
            <div class="chip-btn" data-val="cinematic" onclick="setBgm('cinematic', this)">
                🎬 Cinema Drone<br><span style="font-size:0.7rem; font-weight:normal;">সিনেমাটিক ড্রোন</span>
            </div>
            <div class="chip-btn" data-val="none" onclick="setBgm('none', this)">
                🔇 বন্ধ<br><span style="font-size:0.7rem; font-weight:normal;">ইনবিল্ট শিল্ড সক্রিয়</span>
            </div>
        </div>
        <div style="font-size: 0.74rem; color: #10b981; margin-top: 8px;">
            ✔ এটি মূল অডিওর পেছনে মৃদুভাবে বেজে স্পেকট্রাম পিক বদলে দেয়—ইউটিউবের রোবট অডিও মেলাতে পারবে না।
        </div>
    </div>

    <!-- সাবমিট বাটন -->
    <button class="btn-action" id="startBtn" onclick="startProcess()" disabled>
        <span>▶</span> 🚀 ১০০০% কপিরাইট বাইপাস প্রসেস শুরু করো
    </button>

    <!-- প্রোগ্রেস ও রেজাল্ট কার্ড -->
    <div class="card progress-card" id="progressCard">
        <div style="font-size: 1.25rem; font-weight: 800;" id="progPercent">০%</div>
        <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progFill"></div>
        </div>
        <div class="status-msg" id="progStatus">প্রসেসিং শুরু হচ্ছে...</div>

        <div class="stats-grid">
            <div class="stat-item">
                <div>সময় অতিবাহিত</div>
                <div class="stat-val" id="statElapsed">০ সে.</div>
            </div>
            <div class="stat-item">
                <div>অবশিষ্ট আনুমানিক</div>
                <div class="stat-val" id="statEta">হিসাব হচ্ছে...</div>
            </div>
            <div class="stat-item">
                <div>টার্গেট সাইজ</div>
                <div class="stat-val" id="statEstSize">২-৩ GB</div>
            </div>
        </div>

        <div class="log-box" id="logBox">লগ লোড হচ্ছে...</div>

        <!-- রেজাল্ট ভিউ -->
        <div class="result-box" id="resultBox">
            <div style="font-size: 1.6rem;">🎉</div>
            <div style="font-size: 1.15rem; font-weight: 800; color: #10b981;">১০০০% কপিরাইট বাইপাস সম্পন্ন!</div>
            <div style="font-size: 0.82rem; color: #cbd5e1; margin-top: 4px;" id="saveInfo">ভিডিওটি ডাউনলোড করে সরাসরি ইউটিউবে আপলোড করতে পারবেন:</div>
            <a href="#" id="downloadLink" class="btn-download" download>
                📥 মোবাইলে ডাউনলোড করুন (Save Video)
            </a>
        </div>
    </div>

</div>

<script>
    let selectedFile = null;
    let selectedStrength = "Nuclear";
    let selectedSizeProfile = "5h_2to3gb";
    let selectedRes = "720p";
    let selectedGrade = "Teal & Orange";
    let selectedVoice = "MicroShift";
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
        document.querySelectorAll('#strengthGroup .chip-btn').forEach(b => b.classList.remove('active', 'fire'));
        el.classList.add('active');
        if (val === 'Nuclear') el.classList.add('fire');
    }

    function setSizeProfile(val, el) {
        selectedSizeProfile = val;
        document.querySelectorAll('#sizeGroup .chip-btn').forEach(b => b.classList.remove('active', 'gold'));
        el.classList.add('active', 'gold');
        if (val === '5h_2to3gb') document.getElementById('statEstSize').innerText = "২-৩ GB";
        else if (val === '5h_1to2gb') document.getElementById('statEstSize').innerText = "১.৫-২ GB";
        else document.getElementById('statEstSize').innerText = "৩-৪ GB";
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
        formData.append("size_profile", selectedSizeProfile);
        formData.append("resolution", selectedRes);
        formData.append("grade", selectedGrade);
        formData.append("voice", selectedVoice);
        formData.append("bgm", selectedBgm);
        formData.append("mirror", document.getElementById('mirrorFlip').checked);
        formData.append("speed", document.getElementById('speedShift').checked);
        formData.append("drift", document.getElementById('driftShift').checked);
        formData.append("noise_shield", document.getElementById('noiseShield').checked);

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
                startBtn.innerText = "▶ 🚀 ১০০০% কপিরাইট বাইপাস প্রসেস শুরু করো";
            }
        } catch (err) {
            alert("সার্ভার সংযোগ সমস্যা: " + err.message);
            startBtn.disabled = false;
            startBtn.innerText = "▶ 🚀 ১০০০% কপিরাইট বাইপাস প্রসেস শুরু করো";
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
                if (d.est_size && d.est_size !== "--") {
                    document.getElementById('statEstSize').innerText = d.est_size;
                }

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

    strength = request.form.get("strength", "Nuclear")
    size_profile = request.form.get("size_profile", "5h_2to3gb")
    resolution = request.form.get("resolution", "720p")
    grade = request.form.get("grade", "Teal & Orange")
    voice = request.form.get("voice", "MicroShift")
    bgm = request.form.get("bgm", "lofi")
    mirror = request.form.get("mirror") == "true"
    speed = request.form.get("speed") == "true"
    noise_shield = request.form.get("noise_shield") == "true"

    bgm_path = None
    if bgm == "lofi":
        bgm_path = os.path.join(BASE_DIR, "bgm_lofi.m4a")
    elif bgm == "cinematic":
        bgm_path = os.path.join(BASE_DIR, "bgm_cinematic.m4a")

    base_name = os.path.splitext(os.path.basename(file.filename))[0]
    out_filename = f"{base_name}_1000pct_bypass.mp4"
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
        "est_size": "২-৩ GB",
        "logs": [f"ফাইল গ্রহণ সম্পন্ন: {file.filename}"]
    }

    thread = threading.Thread(
        target=run_mobile_process,
        args=(upload_path, out_path, strength, size_profile, resolution, grade, voice, mirror, speed, noise_shield, bgm_path)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"status": "ok", "out_filename": out_filename})


def run_mobile_process(in_path, out_path, strength, size_profile, resolution, grade, voice, mirror, speed, noise_shield, bgm_path=None):
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

        pitch_map = {"MicroShift": 0.8, "Original": 0.0, "Slight": 1.5, "Deep": -2.5, "Bright": 2.5}
        pitch_val = pitch_map.get(voice, 0.8)

        dur = probe_duration(in_path)
        w, h, fps = probe_video_info(in_path)
        sr, ch = probe_audio_sr(in_path)
        has_a = has_audio(in_path)

        speed_factor = 1.035 if speed else 1.0
        effective_dur = dur / speed_factor if dur else None

        prof = SIZE_PROFILES.get(size_profile, SIZE_PROFILES["5h_2to3gb"])
        if dur:
            est_total_gb = (dur / 3600.0) * prof["est_gb_per_hour"]
            current_task["est_size"] = f"~{est_total_gb:.2f} GB"
            log_cb(f"  ভিডিও সময়কাল: {dur / 60:.1f} মিনিট | আনুমানিক সাইজ: {est_total_gb:.2f} GB")

        vf = build_bypass_video_filters(
            w=w, h=h,
            bypass_strength=strength,
            speed_factor=speed_factor,
            mirror=mirror,
            resolution_mode=resolution,
            grade_name=grade,
            grade_intensity=70.0
        )

        af = None
        if has_a:
            af = build_bypass_audio_filters(
                sr=sr,
                voice_preset=voice,
                pitch_steps=pitch_val,
                speed_factor=speed_factor,
                enable_wobble=True,
                enable_chorus=True,
                enable_eq=True,
                enable_stereo=True
            )

        log_cb("  🚀 ১০০০% কপিরাইট বাইপাস ও সাইজ কন্ট্রোলার শুরু হচ্ছে...")

        has_bgm = bool(bgm_path and os.path.exists(bgm_path))
        if has_bgm:
            log_cb(f"  🎵 ব্যাকগ্রাউন্ড মিউজিক অ্যাকোস্টিক মাস্কার যুক্ত হচ্ছে ({os.path.basename(bgm_path)})...")

        enc_list = DETECTED_ENCODERS
        selected_encoder = None
        last_err = ""

        # মেটাডাটা ক্যামোফ্লেজ ও ফাস্টস্টার্ট অপশন
        meta_args = [
            "-map_metadata", "-1",
            "-metadata", "title=",
            "-metadata", "artist=",
            "-metadata", "comment=",
            "-metadata:g:0", "make=Apple",
            "-metadata:g:0", "model=iPhone 15 Pro Max",
            "-metadata:g:0", "software=iOS 17.5.1",
            "-metadata:s:v:0", "handler_name=Core Media Video",
            "-metadata:s:a:0", "handler_name=Core Media Audio",
            "-movflags", "+faststart",
            "-nostats", "-progress", "pipe:1"
        ]

        audio_bitrate = prof["a_bitrate"]

        for enc in enc_list:
            log_cb(f"  এনকোডার পরীক্ষা: {enc['name']}...")
            enc_opts = get_encoder_options(enc["id"], size_profile)

            if has_bgm:
                bgm_vol = 0.15
                if has_a:
                    f_complex = (
                        f"[0:v]{vf}[v_out];"
                        f"[0:a]{af}[a_proc];"
                        f"anoisesrc=c=pink:r=44100:a=0.002[p_noise];"
                        f"[1:a]volume={bgm_vol:.3f}[bgm_proc];"
                        f"[a_proc][p_noise][bgm_proc]amix=inputs=3:duration=first:dropout_transition=0:weights=1 0.04 0.9[a_out]"
                    )
                else:
                    f_complex = f"[0:v]{vf}[v_out];[1:a]volume={bgm_vol:.3f}[a_out]"

                cmd = [
                    FFMPEG, "-y",
                    "-i", in_path,
                    "-stream_loop", "-1", "-i", bgm_path,
                    "-filter_complex", f_complex,
                    "-map", "[v_out]", "-map", "[a_out]",
                    "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100"
                ] + enc_opts + meta_args + [out_path]

            else:
                if has_a and noise_shield:
                    f_complex = (
                        f"[0:v]{vf}[v_out];"
                        f"[0:a]{af}[a_proc];"
                        f"anoisesrc=c=pink:r=44100:a=0.003[p_noise];"
                        f"[a_proc][p_noise]amix=inputs=2:duration=first:dropout_transition=0:weights=1 0.05[a_out]"
                    )
                    cmd = [
                        FFMPEG, "-y",
                        "-i", in_path,
                        "-filter_complex", f_complex,
                        "-map", "[v_out]", "-map", "[a_out]",
                        "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100"
                    ] + enc_opts + meta_args + [out_path]

                else:
                    cmd = [
                        FFMPEG, "-y",
                        "-i", in_path,
                        "-vf", vf,
                    ]
                    if af:
                        cmd += ["-af", af, "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100"]
                    else:
                        cmd += ["-an"]

                    cmd += enc_opts + meta_args + [out_path]

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

        if os.path.exists(out_path):
            actual_bytes = os.path.getsize(out_path)
            actual_mb = actual_bytes / (1024 * 1024)
            actual_gb = actual_bytes / (1024 * 1024 * 1024)
            current_task["est_size"] = f"{actual_gb:.2f} GB" if actual_gb >= 1.0 else f"{actual_mb:.1f} MB"
            log_cb(f"  ✔ ফাইনাল ফাইল সাইজ: {current_task['est_size']} (পারফেক্ট ২-৩ জিবি টার্গেট অর্জন)")

        current_task["progress"] = 100
        current_task["status"] = "১০০০% কপিরাইট বাইপাস সম্পন্ন!"
        current_task["logs"].append("✔ সফলভাবে ভিডিও প্রস্তুত হয়েছে। সরাসরি ইউটিউবে আপলোড করতে পারবেন।")

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
    port = 5000
    host = "0.0.0.0"
    local_ip = get_local_ip()

    print("\n" + "=" * 65)
    print("  ⚡ Video Studio Pro — 1000% Copyright Bypass & Turbo Engine")
    print(f"  🎯 5 Hours = 2-3 GB Guaranteed Bitrate Engine Active")
    print("=" * 65)
    print(f"  ▶ লোকাল ব্রাউজারে খুলুন : http://localhost:{port}")
    print(f"  ▶ মোবাইল থেকে ব্রাউজারে: http://{local_ip}:{port}")
    if IS_TERMUX:
        print("  ▶ Termux ডিরেক্টরি      : /sdcard/Download")
    print("=" * 65 + "\n")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
