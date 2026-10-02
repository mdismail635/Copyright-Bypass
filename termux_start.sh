#!/data/data/com.termux/files/usr/bin/bash
# Video Studio Pro — Termux Launcher Script
clear
cd "$(dirname "$0")"

echo "========================================================"
echo "   ⚡ Video Studio Pro — Mobile Server চালু হচ্ছে...    "
echo "========================================================"
echo ""
echo "  ব্রাউজারে ওপেন করুন:"
echo "  👉  http://localhost:5000  বা  http://127.0.0.1:5000  👈"
echo ""

# FFmpeg ঠিক আছে কি না চেক
if ! ffmpeg -version &> /dev/null; then
    echo "⚠️ FFmpeg ব্রোকেন লাইব্রেরি সনাক্ত হয়েছে! সিস্টেম আপগ্রেড করা হচ্ছে..."
    pkg upgrade -y
fi

# Flask ইনস্টল আছে কি না চেক ও অটো-ইন্সটল
if ! python3 -c "import flask" &> /dev/null; then
    echo "⚠️ Flask লাইব্রেরি পাওয়া যায়নি! স্বয়ংক্রিয়ভাবে কম্পাইল ও ইন্সটল করা হচ্ছে..."
    pkg install clang -y
    python3 -m pip install wheel --break-system-packages
    python3 -m pip install flask --break-system-packages
fi

# ২ সেকেন্ড পরে ফোনের ডিফল্ট ব্রাউজারে অটো ওপেন
if command -v termux-open-url &> /dev/null; then
    (sleep 2 && termux-open-url "http://localhost:5000") &
fi

python3 mobile_app.py
