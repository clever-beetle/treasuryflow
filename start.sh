#!/usr/bin/env bash
# File: start.sh

# 1. Inisiasi database (ini hanya akan membuat file database jika belum ada)
python -c "from app import init_db"

# 2. Jalankan aplikasi menggunakan Gunicorn
gunicorn -w 4 'app:app' -b 0.0.0.0:$PORT