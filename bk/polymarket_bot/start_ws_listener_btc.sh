#!/bin/bash

SCRIPT="ws-listener-btc.py"
PIDFILE="ws-listener-btc.pid"

# Якщо PID-файл існує — перевіряємо чи процес живий
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "ws-listener.py вже запущений з PID $PID"
        exit 0
    else
        echo "PID-файл існує, але процес не працює — видаляю"
        rm -f "$PIDFILE"
    fi
fi

# Запускаємо у фоні
echo "Запускаю ws-listener.py у фоні..."
nohup py "$SCRIPT" > ws-listener-btc.log 2>&1 &

# Зберігаємо PID
echo $! > "$PIDFILE"

echo "ws-listener.py запущено. PID=$(cat $PIDFILE)"
