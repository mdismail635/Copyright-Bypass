#!/data/data/com.termux/files/usr/bin/bash
# Video Studio Pro — Termux Setup Script
clear
echo "========================================================"
echo "   ⚡ Video Studio Pro — Termux Auto Setup Installer   "
echo "========================================================"
echo ""
echo "[1/4] ফোনের স্টোরেজ পারমিশন চাওয়া হচ্ছে..."
termux-setup-storage
sleep 2

echo ""
echo "[2/4] Termux প্যাকেজ আপডেট করা হচ্ছে..."
pkg update -y

echo ""
echo "[3/4] Python, pip ও FFmpeg ইন্সটল করা হচ্ছে..."
pkg install python python-pip ffmpeg -y

echo ""
echo "[4/4] Flask লাইব্রেরি ইন্সটল করা হচ্ছে..."
pip install flask --break-system-packages || pip install flask || python3 -m pip install flask --break-system-packages

echo ""
echo "========================================================"
echo "   🎉 সেটআপ সফলভাবে সম্পন্ন হয়েছে!"
echo "   এখন অ্যাপ চালু করতে কমান্ড দিন:"
echo "   bash termux_start.sh"
echo "========================================================"
