#!/bin/zsh
# Ikki marta bosing: panel brauzerda ochiladi. Yopish uchun bu oynada Ctrl+C.
cd "$(dirname "$0")"
.venv/bin/python -W ignore panel/server.py
