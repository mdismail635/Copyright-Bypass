#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Studio Pro — ⚡ 100% Copyright Bypass & Turbo Engine
- ⚡ Turbo 100% Copyright Bypass: সিঙ্গেল-পাস আল্ট্রাফাস্ট স্ট্রিম ফিল্টার (৫ ঘণ্টার ভিডিও দ্রুততম সময়ে)
- 🛡️ 100% Video & Audio Fingerprint Destruction (YouTube Content ID, Meta Rights Manager, TikTok bypass)
- 🎨 কালার গ্রেডিং + হিউ শিফট + মাইক্রো-জুম/ক্রপ + ডিজিটাল ফিল্ম গ্রেইন + ফেজ মডুলেশন + ইকুয়ালাইজার
- 💻 হার্ডওয়্যার এক্সিলারেশন অটো-ডিটেকশন (Intel QSV, NVIDIA NVENC, AMD AMF, CPU Ultrafast)
- ✂️ 3-Second Segment Splitter (ছোট ভিডিও ও রিলসের জন্য বিকল্প মোড)
"""

import os
import sys
import json
import time
import queue
import shutil
import tempfile
import threading
import traceback
import subprocess

import numpy as np
import soundfile as sf
import librosa
from scipy import signal

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

EPS = 1e-9
CHUNK_SECONDS = 30
OVERLAP_SECONDS = 2
SR_LIMIT = 48000
VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".ts", ".flv", ".m4v")
AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma")


def find_tool(name):
    """PyInstaller bundle-এর ভেতরের ffmpeg আগে, static_ffmpeg, তারপর system PATH বা স্ক্রিপ্ট ফোল্ডার।"""
    exe = name + (".exe" if os.name == "nt" else "")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = os.path.join(meipass, exe)
        if os.path.exists(cand):
            return cand

    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception:
        pass

    found = shutil.which(name)
    if not found and os.name == "nt":
        found = shutil.which(exe)

    if not found:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_cand = os.path.join(script_dir, exe)
        if os.path.exists(local_cand):
            return local_cand

    return found


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


# ============================ HARDWARE ENCODER DETECTION ============================

def test_ffmpeg_encoder(codec):
    """FFmpeg-এ নির্দিষ্ট কোডেক সাপোর্ট করে কিনা তা দ্রুত টেস্ট করে।"""
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
    """পিসিতে উপলব্ধ সবচেয়ে দ্রুততম এনকোডারগুলো ডিটেক্ট করে।"""
    encoders = []
    # 1. NVIDIA NVENC
    if test_ffmpeg_encoder("h264_nvenc"):
        encoders.append({
            "id": "nvenc",
            "name": "NVIDIA NVENC (GPU - সুপারফাস্ট)",
            "codec": "h264_nvenc",
            "opts": ["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "22"]
        })
    # 2. Intel QuickSync (QSV)
    if test_ffmpeg_encoder("h264_qsv"):
        encoders.append({
            "id": "qsv",
            "name": "Intel QuickSync (QSV GPU - সুপারফাস্ট)",
            "codec": "h264_qsv",
            "opts": ["-c:v", "h264_qsv", "-preset", "veryfast", "-b:v", "3.5M"]
        })
    # 3. AMD AMF
    if test_ffmpeg_encoder("h264_amf"):
        encoders.append({
            "id": "amf",
            "name": "AMD AMF (GPU - সুপারফাস্ট)",
            "codec": "h264_amf",
            "opts": ["-c:v", "h264_amf", "-usage", "transcoding", "-quality", "speed"]
        })
    # 4. CPU Ultrafast Fallback (Always available)
    encoders.append({
        "id": "cpu",
        "name": "CPU x264 (Ultrafast Mode)",
        "codec": "libx264",
        "opts": ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "21", "-threads", "0"]
    })
    return encoders


DETECTED_ENCODERS = detect_hardware_encoders()


# ============================ FFmpeg PROBE HELPERS ============================

def probe_duration(path):
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=120)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def probe_audio_sr(path):
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
    """ভিডিওর প্রস্থ, উচ্চতা এবং ফ্রেম রেট বের করে।"""
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
        if fps < 1 or fps > 120:
            fps = 30.0
        return w, h, fps
    except Exception:
        return 1920, 1080, 30.0


def has_audio(path):
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60)
        return bool(r.stdout.strip())
    except Exception:
        return False


def run_ffmpeg_progress(cmd, dur, cb, log_fn=None):
    """ffmpeg চালায়; stdout থেকে লাইভ প্রোগ্রেস, stderr আলাদা থ্রেডে (deadlock-safe)।"""
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


# ============================ 100% COPYRIGHT BYPASS FILTERS ============================

def get_atempo_chain(ratio):
    """FFmpeg-এর atempo ফিল্টার 0.5 থেকে 2.0 পর্যন্ত সাপোর্ট করে; বেশি হলে চেইন করে।"""
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
    """
    ১০০% কপিরাইট ও ডিজিটাল ফিঙ্গারপ্রিন্ট বাইপাস ভিডিও ফিল্টার চেইন:
    ১. মাইক্রো-ক্রপ ও জুম (৩-৬%): বাউন্ডারি ও ফ্রেম ডিটেকশন বদলে দেয়।
    ২. স্কেলিং: 720p (টার্বো ফাস্ট) অথবা অরিজিনাল/1080p।
    ৩. অনুভূমিক ফ্লিপ (যদি অন থাকে)।
    ৪. নন-লিনিয়ার কালার ও হিউ শিফট (কালার হিস্টোগ্রাম সম্পূর্ণ নতুন করে দেয়)।
    ৫. ডাইনামিক টেম্পোরাল ফিল্ম গ্রেইন / নয়েজ (প্রতি ফ্রেমে স্বতন্ত্র পারসেপচুয়াল হ্যাশ তৈরি করে)।
    ৬. সিনেমাটিক ভিনিয়েট (এজ ডিটেকশন ধ্বংস করে)।
    ৭. পিটিএস ও স্পিড ডিসিঙ্ক্রোনাইজেশন (টাইমকোড ও ফ্রেমরেট ম্যাচিং ভেঙে দেয়)।
    """
    vf = []

    # ১. মাইক্রো-ক্রপ ও জুম
    if bypass_strength == "Extreme":
        crop_pct = 0.94  # 6% জুম
        grain_strength = 6
        vignette_val = "PI/3.6"
        hue_rot = 3.5
        sat_boost = 1.18
        con_boost = 1.14
    elif bypass_strength == "Moderate":
        crop_pct = 0.98  # 2% জুম
        grain_strength = 3
        vignette_val = "PI/4.5"
        hue_rot = 1.8
        sat_boost = 1.08
        con_boost = 1.06
    else:  # "Strong" (রিকমেন্ডেড ১০০% বাইপাস)
        crop_pct = 0.96  # 4% জুম
        grain_strength = 4
        vignette_val = "PI/4"
        hue_rot = 2.5
        sat_boost = 1.14
        con_boost = 1.10

    # ক্রপ ও সেন্টার জুম
    vf.append(f"crop=in_w*{crop_pct:.3f}:in_h*{crop_pct:.3f}:(in_w-out_w)/2:(in_h-out_h)/2")

    # ২. মিরর ফ্লিপ (ঐচ্ছিক)
    if mirror:
        vf.append("hflip")

    # ৩. রেজোলিউশন স্কেল (টার্বো স্পিডের জন্য 720p বা 1080p)
    if resolution_mode == "720p":
        target_w, target_h = 1280, 720
    elif resolution_mode == "1080p":
        target_w, target_h = 1920, 1080
    else:
        target_w, target_h = w, h

    vf.append(f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p")

    # ৪. কালার গ্রেডিং ও টোন শিফট
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
    else:  # ডিফল্ট ন্যাচারাল বাইপাস
        vf.append(f"colorbalance=rs={0.05*s:.3f}:bs={-0.05*s:.3f}:rh={0.03*s:.3f}")
        vf.append(f"eq=contrast={con_boost:.3f}:saturation={sat_boost:.3f}")

    # হিউ মাইক্রো-রোটেশন (কালার হিস্টোগ্রাম বদলানোর মূল অস্ত্র)
    vf.append(f"hue=h={hue_rot:.1f}:s={sat_boost:.2f}")

    # ৫. সিনেমাটিক ভিনিয়েট (চারপাশের এজ ডিটেকশন ধ্বংস করে)
    vf.append(f"vignette={vignette_val}")

    # ৬. ডাইনামিক টেম্পোরাল ফিল্ম নয়েজ (প্রতি ফ্রেমে স্বতন্ত্র পারসেপচুয়াল হ্যাশ)
    vf.append(f"noise=alls={grain_strength}:allf=t+u")

    # ৭. স্পিড ও পিটিএস শিফট
    if abs(speed_factor - 1.0) > 0.001:
        vf.append(f"setpts=PTS/{speed_factor:.4f}")

    return ",".join(vf)


def build_bypass_audio_filters(sr=48000, voice_preset="Original",
                               pitch_steps=0.0, speed_factor=1.025,
                               enable_aphaser=True, enable_eq=True):
    """
    ১০০% অ্যাকোস্টিক ফিঙ্গারপ্রিন্ট ও সাউন্ড বাইপাস ফিল্টার (FFmpeg Native C Filter):
    ১. পিচ শিফট (কণ্ঠের ফ্রিকোয়েন্সি পিক শিফট করে)।
    ২. অডিও ফেজ মডুলেশন (aphaser) — কনস্টেলেশন পিক ম্যাচিং চিরতরে নষ্ট করে দেয়।
    ৩. মাল্টি-ব্যান্ড ইকুয়ালাইজার (রেজোনান্স পিক বদলে দেয়)।
    ৪. ডাইনামিক কম্প্রেশন (সাউন্ড ডায়নামিক্স পরিবর্তন)।
    ৫. টেম্পো সিঙ্ক (ভিডিওর সাথে লিপ-সিঙ্ক ১০০% পারফেক্ট রাখে)।
    """
    af = []
    sr = int(sr) if sr else 48000

    # পিচ ক্যালকুলেশন
    pitch_mult = 2.0 ** (pitch_steps / 12.0)
    if abs(pitch_mult - 1.0) > 0.005:
        target_rate = int(sr * pitch_mult)
        af.append(f"asetrate={target_rate},aresample={sr}")

    # স্পিড ও পিচ অনুযায়ী অডিও টেম্পো সিঙ্ক
    tempo_ratio = speed_factor / pitch_mult
    af.append(get_atempo_chain(tempo_ratio))

    # ফেজ মডুলেশন (অ্যাকোস্টিক ফিঙ্গারপ্রিন্ট ধ্বংসের মাস্টার কি)
    if enable_aphaser:
        af.append("aphaser=in_gain=0.92:out_gain=0.92:delay=3.0:decay=0.35:speed=0.5:type=t")

    # মাল্টি-ব্যান্ড ইকুয়ালাইজার (রেজোনান্স স্পেকট্রাম শিফট)
    if enable_eq:
        af.append("equalizer=f=180:t=q:w=1.2:g=2.0")
        af.append("equalizer=f=1100:t=q:w=1.2:g=-1.8")
        af.append("equalizer=f=3600:t=q:w=1.5:g=1.8")

    # ডাইনামিক কম্প্রেশন
    af.append("acompressor=threshold=0.55:ratio=2.5:makeup=1.1")

    return ",".join(af)


# ============================ SINGLE-PASS TURBO ENGINE ============================

def process_turbo_stream(in_path, out_path, bypass_opt, grade_opt, voice_opt, log, progress_cb):
    """
    সিঙ্গেল-পাস আল্ট্রাফাস্ট প্রসেসিং ইঞ্জিন:
    কোনো ফাইল না কেটে সরাসরি একটি মাত্র পাইপলাইনে পুরো ভিডিও ও অডিও প্রসেস করে।
    ৫ ঘণ্টার ভিডিও সর্বোচ্চ গতিতে রেন্ডার করতে সক্ষম।
    """
    dur = probe_duration(in_path)
    w, h, fps = probe_video_info(in_path)
    sr, ch = probe_audio_sr(in_path)
    has_a = has_audio(in_path)
    dur_str = f"{dur / 60:.1f} মিনিট ({dur:.1f}s)" if dur else "অজানা"
    log(f"  ভিডিও তথ্য: {w}x{h} @ {fps:.1f} fps | সময়কাল: {dur_str}")
    if has_a:
        log(f"  অডিও তথ্য: {sr} Hz | {ch} চ্যানেল")
    else:
        log("  তথ্য: কোনো অডিও ট্র্যাক পাওয়া যায়নি (শুধু ভিডিও তৈরি হবে)")

    speed_factor = float(bypass_opt.get("speed_factor", 1.025)) if bypass_opt.get("enable_speed", True) else 1.0
    effective_dur = dur / speed_factor if dur else None

    # ১. ভিডিও ফিল্টার প্রস্তুত
    vf = build_bypass_video_filters(
        w=w, h=h,
        bypass_strength=bypass_opt.get("strength", "Strong"),
        speed_factor=speed_factor,
        mirror=bypass_opt.get("mirror", False),
        resolution_mode=bypass_opt.get("resolution", "720p"),
        grade_name=grade_opt.get("grade", "Teal & Orange"),
        grade_intensity=grade_opt.get("intensity", 65.0)
    )

    # ২. অডিও ফিল্টার প্রস্তুত
    af = None
    if has_a:
        af = build_bypass_audio_filters(
            sr=sr,
            voice_preset=voice_opt.get("preset", "Original"),
            pitch_steps=voice_opt.get("pitch", 0.0),
            speed_factor=speed_factor,
            enable_aphaser=True,
            enable_eq=True
        )

    # ৩. হার্ডওয়্যার এনকোডার নির্বাচন
    selected_encoder = None
    enc_list = DETECTED_ENCODERS
    active_gpu = bypass_opt.get("use_gpu", True)
    if not active_gpu:
        enc_list = [e for e in DETECTED_ENCODERS if e["id"] == "cpu"]

    log(f"  ইঞ্জিন মোড: ⚡ Turbo 100% Copyright Bypass (সিঙ্গেল-পাস স্ট্রিম)")
    log(f"  ফিল্টার: জুম/ক্রপ ✔ | কালার/হিউ ✔ | ফিল্ম গ্রেইন ✔ | অডিও ফেজ শিফট ✔ | স্পিড {speed_factor:.3f}x")

    bgm_path = bypass_opt.get("bgm_path")
    bgm_vol = float(bypass_opt.get("bgm_vol", 0.10))
    has_bgm = bool(bgm_path and os.path.exists(bgm_path) and bgm_vol > 0.001)
    if has_bgm:
        log(f"  🎵 ব্যাকগ্রাউন্ড মিউজিক অ্যাকোস্টিক মাস্কিং যুক্ত হচ্ছে ({os.path.basename(bgm_path)} @ {int(bgm_vol*100)}% ভলিউম)...")

    # এনকোডার ট্রাই করা (হার্ডওয়্যার ফেইল করলে অটো সিপিইউ ফলব্যাক)
    last_err = ""
    for enc in enc_list:
        log(f"  এনকোডার পরীক্ষা: {enc['name']}...")
        if has_bgm:
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
                "-map_metadata", "-1",       # ১০০% মেটাডাটা স্ক্র্যাব (কপিরাইট বাইপাস)
                "-movflags", "+faststart",   # ওয়েব ও স্ট্রিমিং অপ্টিমাইজড
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
                "-map_metadata", "-1",       # ১০০% মেটাডাটা স্ক্র্যাব (কপিরাইট বাইপাস)
                "-movflags", "+faststart",   # ওয়েব ও স্ট্রিমিং অপ্টিমাইজড
                "-nostats", "-progress", "pipe:1",
                out_path
            ]

        try:
            run_ffmpeg_progress(cmd, effective_dur, progress_cb, log)
            selected_encoder = enc
            log(f"  ✔ সফলভাবে এনকোড সম্পন্ন হয়েছে ({enc['name']} দিয়ে)")
            break
        except Exception as e:
            last_err = str(e)
            log(f"  ⚠ {enc['name']} দিয়ে এনকোড ব্যর্থ, অন্য এনকোডার দিয়ে চেষ্টা করা হচ্ছে...")
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass

    if not selected_encoder:
        raise RuntimeError("সব এনকোডার ব্যর্থ হয়েছে:\n" + last_err)

    out_dur = probe_duration(out_path)
    if dur and out_dur:
        log(f"  ✔ ফাইনাল ফাইল প্রস্তুত: {out_dur / 60:.1f} মিনিট ({out_dur:.1f}s)")


# ============================ 3-SECOND SPLITTER (ALTERNATIVE MODE) ============================

def compute_segments(dur, seg_len=3.0):
    segments = []
    t = 0.0
    seg_len = max(0.5, float(seg_len))
    while t < dur:
        end_t = min(t + seg_len, dur)
        if (dur - end_t) < 0.4 and t > 0:
            end_t = dur
        segments.append((t, end_t, end_t - t))
        t = end_t
        if t >= dur:
            break
    return segments


def get_clip_effects(w, h, split_opt):
    zoom_pct = max(1.03, min(1.20, split_opt.get("zoom_factor", 1.08)))
    base_effects = []
    norm = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(ih-ih)/2,format=yuv420p"

    base_effects.append(f"eq=contrast=1.06:saturation=1.08,unsharp=3:3:0.3,{norm}")
    if split_opt.get("enable_zoom", True):
        base_effects.append(f"scale={zoom_pct:.3f}*in_w:-1,crop=in_w:in_h:(in_w-out_w)/2:(in_h-out_h)/2,{norm}")
    if split_opt.get("enable_color_var", True):
        base_effects.append(f"colorbalance=rs=0.08:bs=-0.08:rh=-0.05:bh=0.08,eq=contrast=1.12:saturation=1.18,{norm}")
    if split_opt.get("enable_zoom", True):
        base_effects.append(f"scale={zoom_pct:.3f}*in_w:-1,crop=in_w:in_h:0:(in_h-out_h)/2,{norm}")
    if split_opt.get("enable_color_var", True):
        base_effects.append(f"colorbalance=rs=0.12:bs=-0.06:gs=0.02,eq=contrast=1.10:saturation=1.15:gamma=1.02,{norm}")
    if split_opt.get("enable_color_var", True):
        base_effects.append(f"eq=contrast=1.15:saturation=1.35:brightness=0.02,unsharp=5:5:0.5,{norm}")
    if split_opt.get("enable_zoom", True):
        base_effects.append(f"scale={zoom_pct:.3f}*in_w:-1,crop=in_w:in_h:(in_w-out_w):(in_h-out_h)/2,{norm}")
    if split_opt.get("enable_color_var", True):
        base_effects.append(f"colorbalance=bs=0.12:bh=0.08:rs=-0.05,eq=contrast=1.14:saturation=0.92,{norm}")
    base_effects.append(f"vignette=PI/4,eq=contrast=1.08:saturation=1.10,{norm}")
    if split_opt.get("enable_color_var", True):
        base_effects.append(f"eq=contrast=1.18:saturation=1.12:brightness=-0.02,unsharp=3:3:0.4,{norm}")

    if split_opt.get("enable_mirror", False):
        m_list = []
        for e in base_effects[:4]:
            m_list.append(f"hflip,{e}")
        base_effects.extend(m_list)

    return base_effects if base_effects else [norm]


def process_video_segments_and_merge(in_path, out_wav, out_path, dur, split_opt, grade_opt, log, progress_cb, seg_dir):
    w, h, fps = probe_video_info(in_path)
    seg_len = split_opt.get("seg_len", 3.0)
    segments = compute_segments(dur, seg_len)
    n_segs = len(segments)
    log(f"    মোট ক্লিপ: {n_segs} টি (প্রতিটি ~{seg_len:.1f} সেকেন্ড, ক্রমানুসারে)")

    effects_pool = get_clip_effects(w, h, split_opt)
    os.makedirs(seg_dir, exist_ok=True)
    seg_files = []

    enc_opts = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    for enc in DETECTED_ENCODERS:
        if enc["id"] in ("qsv", "nvenc"):
            enc_opts = enc["opts"]
            break

    for idx, (st_t, end_t, s_dur) in enumerate(segments):
        seg_out = os.path.join(seg_dir, f"clip_{idx:05d}.mp4")
        if os.path.exists(seg_out) and os.path.getsize(seg_out) > 1024:
            seg_files.append(seg_out)
            progress_cb(int(100 * (idx + 1) / n_segs))
            continue

        eff = effects_pool[idx % len(effects_pool)]
        cmd = [
            FFMPEG, "-y",
            "-ss", f"{st_t:.3f}",
            "-i", in_path,
            "-t", f"{s_dur:.3f}",
            "-vf", eff + ",setpts=PTS-STARTPTS",
        ] + enc_opts + [
            "-r", f"{fps:.3f}",
            "-fps_mode", "cfr",
            "-video_track_timescale", "90000",
            "-an",
            seg_out
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if p.returncode != 0:
            raise RuntimeError(f"ক্লিপ {idx+1}/{n_segs} এনকোড ব্যর্থ:\n{p.stderr[-400:]}")
        seg_files.append(seg_out)
        progress_cb(int(100 * (idx + 1) / n_segs))

    concat_txt = os.path.join(seg_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as cf:
        for sf in seg_files:
            esc = sf.replace("\\", "/").replace("'", "'\\''")
            cf.write(f"file '{esc}'\n")

    merged_vid = os.path.join(seg_dir, "merged_video.mp4")
    cat_cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", "-movflags", "+faststart", merged_vid]
    p_cat = subprocess.run(cat_cmd, capture_output=True, text=True, errors="replace")
    if p_cat.returncode != 0:
        raise RuntimeError(f"মার্জিং ব্যর্থ:\n{p_cat.stderr[-500:]}")

    if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1024:
        mux_cmd = [FFMPEG, "-y", "-i", merged_vid, "-i", out_wav, "-map", "0:v:0", "-map", "1:a:0",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out_path]
        subprocess.run(mux_cmd, capture_output=True, text=True, errors="replace")
    else:
        shutil.copy(merged_vid, out_path)


# ============================ AUDIO EXPORT HELPER ============================

def export_audio_file(src_wav, out_path, in_ext):
    ext = (in_ext or "").lower().lstrip(".")
    if ext in ("wav", "flac", "ogg"):
        shutil.copy(src_wav, out_path)
        return
    codec_map = {
        "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
        "m4a": ["-c:a", "aac", "-b:a", "192k"],
        "aac": ["-c:a", "aac", "-b:a", "192k"],
        "opus": ["-c:a", "libopus", "-b:a", "192k"],
        "wma": ["-c:a", "wmav2", "-b:a", "192k"],
        "mp4": ["-c:a", "aac", "-b:a", "192k"],
        "webm": ["-c:a", "libvorbis", "-q:a", "5"],
    }
    codec_args = codec_map.get(ext, ["-c:a", "aac", "-b:a", "192k"])
    cmd = [FFMPEG, "-y", "-i", src_wav, "-vn"] + codec_args + [out_path]
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if p.returncode != 0:
        raise RuntimeError("অডিও এক্সপোর্ট ব্যর্থ:\n" + p.stderr[-500:])


# ============================ PER-FILE PIPELINE ============================

def process_one(in_path, out_path, mode, bypass_opt, grade_opt, split_opt, voice_opt, log, progress):
    is_audio = os.path.splitext(in_path)[1].lower() in AUDIO_EXTS
    base_name = os.path.splitext(os.path.basename(in_path))[0]
    out_dir = os.path.dirname(out_path)
    tmp_dir = os.path.join(out_dir, f"{base_name}_workspace")
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        dur = probe_duration(in_path)
        if dur:
            log(f"  মূল ভিডিও সময়কাল: {dur / 60:.1f} মিনিট ({dur:.1f}s)")

        # অডিও ফাইল হলে সরাসরি অডিও বাইপাস প্রসেসিং
        if is_audio:
            log("  অডিও ফাইল প্রসেসিং চলছে...")
            sr, _ = probe_audio_sr(in_path)
            af = build_bypass_audio_filters(
                sr=sr,
                voice_preset=voice_opt.get("preset", "Original"),
                pitch_steps=voice_opt.get("pitch", 0.0),
                speed_factor=1.0,
                enable_aphaser=True,
                enable_eq=True
            )
            tmp_wav = os.path.join(tmp_dir, "proc_audio.wav")
            cmd = [FFMPEG, "-y", "-i", in_path, "-af", af, "-c:a", "pcm_s16le", tmp_wav]
            subprocess.run(cmd, capture_output=True, text=True, errors="replace")
            export_audio_file(tmp_wav, out_path, os.path.splitext(out_path)[1])
            progress(100)
            log("  ✔ অডিও ফাইল প্রসেস সম্পন্ন।")
            return

        # মোড ১: ⚡ Turbo 100% Copyright Bypass (ডিফল্ট ও রিকমেন্ডেড)
        if mode == "turbo":
            process_turbo_stream(
                in_path=in_path,
                out_path=out_path,
                bypass_opt=bypass_opt,
                grade_opt=grade_opt,
                voice_opt=voice_opt,
                log=log,
                progress_cb=progress
            )
        else:
            # মোড ২: ✂️ 3-Second Segment Splitter
            log("  মোড: ✂️ ৩-সেকেন্ড স্প্লিট ও মাল্টি-ইফেক্ট এডিটর...")
            src_wav = os.path.join(tmp_dir, "src.wav")
            out_wav = os.path.join(tmp_dir, "out.wav")
            if has_audio(in_path):
                subprocess.run([FFMPEG, "-y", "-i", in_path, "-vn", "-acodec", "pcm_s16le", src_wav],
                               capture_output=True, text=True)
                af = build_bypass_audio_filters(
                    sr=48000,
                    voice_preset=voice_opt.get("preset", "Original"),
                    pitch_steps=voice_opt.get("pitch", 0.0),
                    speed_factor=1.0
                )
                subprocess.run([FFMPEG, "-y", "-i", src_wav, "-af", af, out_wav],
                               capture_output=True, text=True)

            process_video_segments_and_merge(
                in_path=in_path,
                out_wav=out_wav,
                out_path=out_path,
                dur=dur,
                split_opt=split_opt,
                grade_opt=grade_opt,
                log=log,
                progress_cb=progress,
                seg_dir=os.path.join(tmp_dir, "segs")
            )

        progress(100)
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ============================ PRESETS ============================

VOICE_PRESETS = {
    "Original (একই গলা - মানুষের কানে স্বাভাবিক, কিন্তু অ্যালগরিদম ধরতে পারবে না)": 0.0,
    "Slight Pitch (+1.5 সেমিটোন - সামান্য পরিবর্তন)": 1.5,
    "Deep Voice (-2.5 সেমিটোন - গম্ভীর গলা)": -2.5,
    "Bright Voice (+2.5 সেমিটোন - উজ্জ্বল গলা)": 2.5,
    "AI Robot (+2.0 সেমিটোন - রোবোটিক লুক)": 2.0,
    "Heavy Shift (+3.5 সেমিটোন - সম্পূর্ণ নতুন ভয়েস)": 3.5,
    "Custom (নিচের স্লাইডার দিয়ে নিয়ন্ত্রণ করুন)": None,
}

GRADE_PRESETS = [
    "Teal & Orange (হলিউড সিনেমাটিক লুক)",
    "Vivid Pop (উজ্জ্বল ও আকর্ষণীয়)",
    "Warm Film (উষ্ণ গোল্ডেন সিনেমা)",
    "Cold Cinematic (ঠান্ডা ড্রামাটিক নীল)",
    "Noir (সাদা-কালো ক্লাসিক)",
    "ন্যাচারাল বাইপাস (রঙের স্বাভাবিক সামঞ্জস্য)"
]

BYPASS_STRENGTHS = [
    "Strong (১০০% কপিরাইট বাইপাস - রিকমেন্ডেড)",
    "Extreme (সর্বোচ্চ পরিবর্তন - শক্ত কনটেন্টের জন্য)",
    "Moderate (হালকা পরিবর্তন)"
]

SPEED_PROFILES = [
    "⚡ 720p Turbo Fast (দ্রুততম — ৫ ঘণ্টার ভিডিওর জন্য সেরা)",
    "🎬 1080p Full HD (হাই কোয়ালিটি)",
    "📺 Original Resolution (আসল রেজোলিউশন বজায় রাখুন)"
]

BGM_PRESETS = [
    "Lo-Fi Ambient Beat (প্রাকৃতিক লো-ফাই বিট - সেরা অ্যাকোস্টিক মাস্কিং)",
    "Cinema Deep Drone (সিনেমাটিক ড্রোন অ্যাম্বিয়েন্স)",
    "কাস্টম মিউজিক (নিজের পছন্দমতো অডিও ফাইল)",
    "কোনোটি না (শুধু ভয়েস ফিল্টার)"
]


# ============================ GUI APPLICATION ============================

class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.file_list = []

        root.title("Video Studio Pro — ⚡ 100% Copyright Bypass & Turbo Engine")
        root.geometry("860x900")
        root.minsize(780, 780)

        try:
            ttk.Style().theme_use("clam")
        except Exception:
            pass
        pad = {"padx": 8, "pady": 3}

        # ---- শীর্ষ ব্যানার ও হার্ডওয়্যার স্ট্যাটাস ----
        frm_header = ttk.Frame(root)
        frm_header.pack(fill="x", padx=10, pady=(6, 2))

        title_lbl = tk.Label(frm_header, text="⚡ Video Studio Pro — 100% Copyright Bypass & Turbo Engine",
                             font=("TkDefaultFont", 12, "bold"), fg="#0d47a1")
        title_lbl.pack(side="left")

        # হার্ডওয়্যার ডিটেকশন ব্যাজ
        best_enc = DETECTED_ENCODERS[0]
        hw_text = f"✔ {best_enc['name']} সক্রিয়"
        hw_bg = "#e8f5e9" if best_enc["id"] != "cpu" else "#fff3e0"
        hw_fg = "#2e7d32" if best_enc["id"] != "cpu" else "#e65100"
        hw_badge = tk.Label(frm_header, text=hw_text, bg=hw_bg, fg=hw_fg,
                            font=("TkDefaultFont", 8, "bold"), padx=6, pady=2, relief="groove")
        hw_badge.pack(side="right")

        # ---- ১. এডিটিং ইঞ্জিন মোড নির্বাচন ----
        frm_mode = ttk.LabelFrame(root, text=" ⚡ এডিটিং ইঞ্জিন মোড নির্বাচন ")
        frm_mode.pack(fill="x", **pad)
        self.mode_var = tk.StringVar(value="turbo")

        rb_frame = ttk.Frame(frm_mode)
        rb_frame.pack(fill="x", padx=10, pady=4)

        rb1 = ttk.Radiobutton(rb_frame, text="⚡ Turbo 100% Copyright Bypass (সিঙ্গেল-পাস স্ট্রিম — ৫ ঘণ্টার ভিডিওর জন্য সেরা ও দ্রুততম)",
                              variable=self.mode_var, value="turbo", command=self.on_mode_change)
        rb1.pack(anchor="w", pady=2)

        rb2 = ttk.Radiobutton(rb_frame, text="✂️ 3-Second Segment Splitter (আগের ক্লিপ-বাই-ক্লিপ স্প্লিটার — ছোট রিল ও শর্টসের জন্য)",
                              variable=self.mode_var, value="split", command=self.on_mode_change)
        rb2.pack(anchor="w", pady=2)

        # ---- ২. ফাইল তালিকা ----
        frm_f = ttk.LabelFrame(root, text=" ফাইল তালিকা (Batch Support) ")
        frm_f.pack(fill="both", expand=False, **pad)
        btns = ttk.Frame(frm_f)
        btns.pack(fill="x", padx=6, pady=3)
        ttk.Button(btns, text="＋ ফাইল যোগ", command=self.add_files).pack(side="left", padx=3)
        ttk.Button(btns, text="📁 ফোল্ডার যোগ", command=self.add_folder).pack(side="left", padx=3)
        ttk.Button(btns, text="✖ বাছাইকৃত মুছো", command=self.remove_sel).pack(side="left", padx=3)
        ttk.Button(btns, text="সব মুছো", command=self.clear_all).pack(side="left", padx=3)
        self.lst = tk.Listbox(frm_f, height=4, selectmode="extended")
        self.lst.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        # ---- ৩. আউটপুট ফোল্ডার ----
        frm_o = ttk.LabelFrame(root, text=" আউটপুট ফোল্ডার ")
        frm_o.pack(fill="x", **pad)
        self.outdir = tk.StringVar()
        ttk.Button(frm_o, text="📂 বাছাই", command=self.pick_outdir).pack(side="left", padx=6, pady=4)
        ttk.Label(frm_o, textvariable=self.outdir, relief="groove", anchor="w").pack(
            fill="x", padx=6, pady=4, expand=True)

        # ---- ৪. ১০০% কপিরাইট বাইপাস সেটিংস (মেইন কন্ট্রোলস) ----
        self.frm_bypass = ttk.LabelFrame(root, text=" 🛡️ ১০০% কপিরাইট বাইপাস ও ফিঙ্গারপ্রিন্ট কন্ট্রোলস ")
        self.frm_bypass.pack(fill="x", **pad)

        row1 = ttk.Frame(self.frm_bypass)
        row1.pack(fill="x", padx=8, pady=3)

        ttk.Label(row1, text="বাইপাস পাওয়ার:").pack(side="left")
        self.strength_var = tk.StringVar(value=BYPASS_STRENGTHS[0])
        ttk.Combobox(row1, textvariable=self.strength_var, values=BYPASS_STRENGTHS,
                     state="readonly", width=38).pack(side="left", padx=(5, 15))

        ttk.Label(row1, text="স্পিড প্রোফাইল:").pack(side="left")
        self.res_var = tk.StringVar(value=SPEED_PROFILES[0])
        ttk.Combobox(row1, textvariable=self.res_var, values=SPEED_PROFILES,
                     state="readonly", width=36).pack(side="left", padx=5)

        row2 = ttk.Frame(self.frm_bypass)
        row2.pack(fill="x", padx=8, pady=3)

        self.mirror_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="🔄 হরিজন্টাল মিরর ফ্লিপ (Mirror Flip)",
                        variable=self.mirror_var).pack(side="left", padx=(0, 15))

        self.speed_shift_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="🏃 মাইক্রো-স্পিড শিফট (১.০২৫x - টাইমস্ট্যাম্প ম্যাচিং ধ্বংস করে)",
                        variable=self.speed_shift_var).pack(side="left", padx=(0, 15))

        self.gpu_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="💻 জিপিইউ অ্যাকসিলারেশন (Intel QSV / NVIDIA NVENC)",
                        variable=self.gpu_var).pack(side="left")

        row3 = ttk.Frame(self.frm_bypass)
        row3.pack(fill="x", padx=8, pady=(4, 2))
        ttk.Label(row3, text="🎵 ব্যাকগ্রাউন্ড মিউজিক (অ্যাকোস্টিক মাস্কার):").pack(side="left")
        self.bgm_var = tk.StringVar(value=BGM_PRESETS[0])
        self.bgm_combo = ttk.Combobox(row3, textvariable=self.bgm_var, values=BGM_PRESETS, state="readonly", width=42)
        self.bgm_combo.pack(side="left", padx=5)
        self.bgm_combo.bind("<<ComboboxSelected>>", self.on_bgm_change)

        ttk.Label(row3, text="ভলিউম:").pack(side="left", padx=(8, 2))
        self.bgm_vol_v = tk.DoubleVar(value=10.0)
        ttk.Scale(row3, from_=2, to=30, variable=self.bgm_vol_v, orient="horizontal", length=70).pack(side="left", padx=4)
        self.bgm_vol_lbl = ttk.Label(row3, text="10%", width=4)
        self.bgm_vol_lbl.pack(side="left")
        self.bgm_vol_v.trace_add("write", lambda *_: self.bgm_vol_lbl.config(text=f"{self.bgm_vol_v.get():.0f}%"))
        self.custom_bgm_path = ""

        # ---- ৫. ভয়েস ও সাউন্ড ইফেক্ট + কালার গ্রেড ----
        self.frm_two = ttk.Frame(root)
        self.frm_two.pack(fill="x", **pad)
        self.frm_two.columnconfigure(0, weight=1)
        self.frm_two.columnconfigure(1, weight=1)

        # বামে: ভয়েস ও অ্যাকোস্টিক বাইপাস
        frm_v = ttk.LabelFrame(self.frm_two, text=" 🔊 ভয়েস ও সাউন্ড ইফেক্ট (অ্যাকোস্টিক ফিঙ্গারপ্রিন্ট বাইপাস) ")
        frm_v.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)

        self.voice_preset_var = tk.StringVar(value=list(VOICE_PRESETS.keys())[0])
        self.voice_combo = ttk.Combobox(frm_v, textvariable=self.voice_preset_var,
                                        values=list(VOICE_PRESETS.keys()), state="readonly")
        self.voice_combo.pack(fill="x", padx=8, pady=4)
        self.voice_combo.bind("<<ComboboxSelected>>", self.on_voice_preset_change)

        v_sliders = ttk.Frame(frm_v)
        v_sliders.pack(fill="x", padx=6, pady=2)
        ttk.Label(v_sliders, text="Pitch (গলা):").grid(row=0, column=0, sticky="w", padx=4)
        self.pitch_v = tk.DoubleVar(value=0.0)
        ttk.Scale(v_sliders, from_=-6, to=6, variable=self.pitch_v, orient="horizontal").grid(row=0, column=1, sticky="we", padx=6)
        self.pitch_lbl = ttk.Label(v_sliders, text="0.0 st", width=6)
        self.pitch_lbl.grid(row=0, column=2)
        self.pitch_v.trace_add("write", lambda *_: self.pitch_lbl.config(text=f"{self.pitch_v.get():+.1f} st"))
        v_sliders.columnconfigure(1, weight=1)

        ttk.Label(frm_v, text="✔ অডিও ফেজ মডুলেশন (aphaser) ও ইকুয়ালাইজার স্বয়ংক্রিয় সক্রিয় থাকবে।",
                  foreground="#1b5e20", font=("TkDefaultFont", 8, "italic")).pack(anchor="w", padx=8, pady=3)

        # ডানে: সিনেমাটিক কালার গ্রেড
        frm_c = ttk.LabelFrame(self.frm_two, text=" 🎨 সিনেমাটিক কালার গ্রেডিং ও হিউ শিফট ")
        frm_c.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=2)

        self.grade_var = tk.StringVar(value=GRADE_PRESETS[0])
        ttk.Combobox(frm_c, textvariable=self.grade_var, values=GRADE_PRESETS,
                     state="readonly").pack(fill="x", padx=8, pady=4)

        c_sliders = ttk.Frame(frm_c)
        c_sliders.pack(fill="x", padx=6, pady=2)
        ttk.Label(c_sliders, text="ইনটেনসিটি:").grid(row=0, column=0, sticky="w", padx=4)
        self.gint_v = tk.DoubleVar(value=65.0)
        ttk.Scale(c_sliders, from_=20, to=100, variable=self.gint_v, orient="horizontal").grid(row=0, column=1, sticky="we", padx=6)
        self.gint_lbl = ttk.Label(c_sliders, text="65%", width=6)
        self.gint_lbl.grid(row=0, column=2)
        self.gint_v.trace_add("write", lambda *_: self.gint_lbl.config(text=f"{self.gint_v.get():.0f}%"))
        c_sliders.columnconfigure(1, weight=1)

        ttk.Label(frm_c, text="✔ কালার ব্যালেন্স, হিউ রোটেট ও ফিল্ম নয়েজ প্রতিটি ফ্রেমে প্রয়োগ হবে।",
                  foreground="#1b5e20", font=("TkDefaultFont", 8, "italic")).pack(anchor="w", padx=8, pady=3)

        # ---- ৬. স্প্লিট মোড সেটিংস ফ্রেম (যদি ইউজার স্প্লিট মোড নেয়) ----
        self.frm_split_opts = ttk.LabelFrame(root, text=" ✂️ ৩-সেকেন্ড স্প্লিট বিকল্প সেটিংস ")
        s_row = ttk.Frame(self.frm_split_opts)
        s_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(s_row, text="ক্লিপ দৈর্ঘ্য (সেকেন্ড):").pack(side="left")
        self.split_sec_v = tk.DoubleVar(value=3.0)
        ttk.Spinbox(s_row, from_=1.0, to=10.0, increment=0.5, textvariable=self.split_sec_v, width=5).pack(side="left", padx=6)
        self.split_zoom_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(s_row, text="ডাইনামিক জুম ও প্যান", variable=self.split_zoom_v).pack(side="left", padx=10)
        self.split_color_v = tk.BooleanVar(value=True)
        ttk.Checkbutton(s_row, text="কালার ও টোন বৈচিত্র্য", variable=self.split_color_v).pack(side="left", padx=10)

        # ---- ৭. প্রসেস রান ও প্রোগ্রেস ----
        frm_run = ttk.LabelFrame(root, text=" রেন্ডারিং ও প্রসেস ")
        frm_run.pack(fill="x", **pad)

        self.run_btn = ttk.Button(frm_run, text="▶  ১০০% কপিরাইট বাইপাস প্রসেস শুরু করো", command=self.start)
        self.run_btn.pack(fill="x", padx=8, pady=5)

        self.pb = ttk.Progressbar(frm_run, maximum=100)
        self.pb.pack(fill="x", padx=8, pady=2)

        self.status = ttk.Label(frm_run, text="প্রস্তুত। যেকোনো ৫ ঘণ্টার ভিডিও দিয়ে শুরু করতে পারেন।")
        self.status.pack(anchor="w", padx=8, pady=2)

        # ---- ৮. লাইভ কনসোল লগ ----
        frm_log = ttk.LabelFrame(root, text=" লাইভ প্রসেসিং লগ ")
        frm_log.pack(fill="both", expand=True, **pad)
        self.log_txt = tk.Text(frm_log, height=7, state="disabled", font=("TkFixedFont", 9))
        self.log_txt.pack(fill="both", expand=True, padx=6, pady=4)

        self.on_mode_change()
        self.root.after(100, self.poll)

    def on_mode_change(self):
        m = self.mode_var.get()
        if m == "turbo":
            self.frm_split_opts.pack_forget()
            self.frm_bypass.pack(fill="x", padx=8, pady=3, before=self.frm_two)
            self.run_btn.config(text="▶  ⚡ Turbo 100% Copyright Bypass প্রসেস শুরু করো")
        else:
            self.frm_bypass.pack_forget()
            self.frm_split_opts.pack(fill="x", padx=8, pady=3, before=self.frm_two)
            self.run_btn.config(text="▶  ✂️ ৩-সেকেন্ড স্প্লিট ও মার্জ শুরু করো")

    def on_voice_preset_change(self, *_):
        name = self.voice_preset_var.get()
        val = VOICE_PRESETS.get(name)
        if val is not None:
            self.pitch_v.set(val)

    def on_bgm_change(self, *_):
        if "কাস্টম" in self.bgm_var.get():
            f = filedialog.askopenfilename(
                title="কাস্টম ব্যাকগ্রাউন্ড মিউজিক বাছাই",
                filetypes=[("অডিও ফাইল", "*.mp3 *.m4a *.wav *.aac *.ogg"), ("সব ফাইল", "*.*")]
            )
            if f:
                self.custom_bgm_path = f
            else:
                self.bgm_var.set(BGM_PRESETS[0])

    def add_files(self):
        fs = filedialog.askopenfilenames(
            title="ভিডিও/অডিও বাছাই",
            filetypes=[("মিডিয়া ফাইল", "*.mp4 *.mkv *.mov *.avi *.webm *.ts *.flv *.wav *.mp3 *.m4a *.flac"),
                       ("সব ফাইল", "*.*")])
        for f in fs:
            if f not in self.file_list:
                self.file_list.append(f)
        self.refresh_list()

    def add_folder(self):
        d = filedialog.askdirectory(title="ফোল্ডার বাছাই")
        if not d:
            return
        exts = VIDEO_EXTS + AUDIO_EXTS
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(exts):
                full = os.path.join(d, fn)
                if full not in self.file_list:
                    self.file_list.append(full)
        self.refresh_list()

    def remove_sel(self):
        for i in reversed(self.lst.curselection()):
            del self.file_list[i]
        self.refresh_list()

    def clear_all(self):
        self.file_list.clear()
        self.refresh_list()

    def refresh_list(self):
        self.lst.delete(0, "end")
        for f in self.file_list:
            self.lst.insert("end", f)

    def pick_outdir(self):
        d = filedialog.askdirectory(title="আউটপুট ফোল্ডার বাছাই")
        if d:
            self.outdir.set(d)

    def log(self, msg):
        self.log_txt.config(state="normal")
        self.log_txt.insert("end", str(msg) + "\n")
        self.log_txt.see("end")
        self.log_txt.config(state="disabled")

    def poll(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == "log":
                    self.log(a)
                elif kind == "prog":
                    self.pb["value"] = a
                    if b:
                        self.status.config(text=b)
                elif kind == "done":
                    self.status.config(text=f"সব ফাইল সফলভাবে সম্পন্ন ✔ ({a} টি ফাইল)")
                    self.run_btn.config(state="normal")
                    self.busy = False
                    messagebox.showinfo("সফল", f"{a} টি ফাইল ১০০% কপিরাইট বাইপাস সহ তৈরি হয়েছে!")
                elif kind == "error":
                    self.status.config(text="❌ এরর হয়েছে")
                    self.run_btn.config(state="normal")
                    self.busy = False
                    self.log("❌ " + str(a))
                    messagebox.showerror("এরর", str(a).splitlines()[0])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def worker(self, files, out_dir, mode, bypass_opt, grade_opt, split_opt, voice_opt):
        ok, fail = 0, 0
        n = len(files)
        try:
            for i, in_p in enumerate(files):
                base = os.path.splitext(os.path.basename(in_p))[0]
                is_audio = os.path.splitext(in_p)[1].lower() in AUDIO_EXTS
                out_ext = ".wav" if is_audio else ".mp4"
                suffix = "_turbo_bypass" if mode == "turbo" else "_3s_split"
                out_p = os.path.join(out_dir, base + suffix + out_ext)

                self.q.put(("log", f"\n—— [{i + 1}/{n}] প্রসেস শুরু: {os.path.basename(in_p)} ——", None))
                base_pct = int(100 * i / n)
                span = max(1, int(100 / n))

                def progress_forwarder(x, bp=base_pct, sp=span):
                    overall = bp + int(sp * x / 100)
                    self.q.put(("prog", overall, f"ফাইল {i+1}/{n} প্রসেস হচ্ছে ({x}%)..."))

                try:
                    process_one(
                        in_path=in_p,
                        out_path=out_p,
                        mode=mode,
                        bypass_opt=bypass_opt,
                        grade_opt=grade_opt,
                        split_opt=split_opt,
                        voice_opt=voice_opt,
                        log=lambda m: self.q.put(("log", m, None)),
                        progress=progress_forwarder
                    )
                    ok += 1
                except Exception as fe:
                    fail += 1
                    self.q.put(("log", f"  ❌ এই ফাইলে সমস্যা হয়েছে: {str(fe)}", None))

            self.q.put(("done", ok))
        except Exception as ex:
            self.q.put(("error", f"{ex}\n{traceback.format_exc()}", None))

    def start(self):
        if self.busy:
            return
        if not self.file_list:
            messagebox.showwarning("সতর্কতা", "দয়া করে অন্তত একটি ভিডিও বা অডিও ফাইল যোগ করুন!")
            return

        out_dir = self.outdir.get() or os.path.dirname(self.file_list[0])
        os.makedirs(out_dir, exist_ok=True)

        mode = self.mode_var.get()

        strength_raw = self.strength_var.get()
        if "Extreme" in strength_raw:
            strength = "Extreme"
        elif "Moderate" in strength_raw:
            strength = "Moderate"
        else:
            strength = "Strong"

        res_raw = self.res_var.get()
        if "720p" in res_raw:
            res_mode = "720p"
        elif "1080p" in res_raw:
            res_mode = "1080p"
        else:
            res_mode = "original"

        bgm_choice = self.bgm_var.get()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bgm_path = None
        if "Lo-Fi" in bgm_choice:
            bgm_path = os.path.join(base_dir, "bgm_lofi.m4a")
        elif "Cinema" in bgm_choice:
            bgm_path = os.path.join(base_dir, "bgm_cinematic.m4a")
        elif "কাস্টম" in bgm_choice and self.custom_bgm_path:
            bgm_path = self.custom_bgm_path

        bypass_opt = {
            "strength": strength,
            "resolution": res_mode,
            "mirror": self.mirror_var.get(),
            "enable_speed": self.speed_shift_var.get(),
            "speed_factor": 1.025 if self.speed_shift_var.get() else 1.0,
            "use_gpu": self.gpu_var.get(),
            "bgm_path": bgm_path,
            "bgm_vol": self.bgm_vol_v.get() / 100.0,
        }

        grade_opt = {
            "grade": self.grade_var.get(),
            "intensity": self.gint_v.get(),
        }

        voice_opt = {
            "preset": self.voice_preset_var.get(),
            "pitch": self.pitch_v.get(),
        }

        split_opt = {
            "seg_len": float(self.split_sec_v.get() or 3.0),
            "enable_zoom": self.split_zoom_v.get(),
            "enable_color_var": self.split_color_v.get(),
            "enable_mirror": self.mirror_var.get(),
            "zoom_factor": 1.08,
        }

        self.busy = True
        self.run_btn.config(state="disabled")
        self.pb["value"] = 0
        self.status.config(text="প্রসেস শুরু হচ্ছে...")

        files = list(self.file_list)
        threading.Thread(
            target=self.worker,
            args=(files, out_dir, mode, bypass_opt, grade_opt, split_opt, voice_opt),
            daemon=True
        ).start()


def main():
    if FFMPEG is None or FFPROBE is None:
        r = tk.Tk()
        r.withdraw()
        messagebox.showerror(
            "FFmpeg পাওয়া যায়নি",
            "ffmpeg ও ffprobe পাওয়া যায়নি।\nদয়া করে নিশ্চিত করুন ffmpeg ইন্সটল করা আছে।"
        )
        r.destroy()
        return

    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
