#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "가상환경 생성 중..."
  python3 -m venv venv
  venv/bin/pip install -q -r requirements.txt
fi

exec venv/bin/python app.py
