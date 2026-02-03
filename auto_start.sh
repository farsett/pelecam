#!/bin/bash

API_PATH="/home/pelengas/pelecam"
cd "$API_PATH"
echo "Запуск API . . ."
set -e
source "./camenv/bin/activate"
python -u cam.py > logs/cam_api.log &
API_PID=$!
echo "API PID: $API_PID"
