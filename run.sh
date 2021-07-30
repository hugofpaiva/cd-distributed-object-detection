#!/bin/bash
DEFAULT_NUMBER_WORKERS=2

workers=${1:-$DEFAULT_NUMBER_WORKERS}

redis-server --daemonize yes

source venv/bin/activate

python3 server.py &
sleep 5

for i in $(seq 1 $workers); do
    python3 worker.py &
    sleep 2
done

curl -F 'video=@moliceiro.m4v' http://localhost:5000
