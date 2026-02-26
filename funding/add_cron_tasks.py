import os
import subprocess

# Шляхи до скриптів
base_path = "/root/funding"
tasks = [
    {
        "script": "funding_collector.py",
        "schedule": "5,35 * * * *",
        "log": "funding_collector_.log"
    },
    {
        "script": "main0.py",
        "schedule": "0,30,55 * * * *",
        "log": "main0_.log"
    }
]

# Отримуємо існуючі завдання crontab
try:
    existing = subprocess.check_output(["crontab", "-l"], text=True)
except subprocess.CalledProcessError:
    existing = ""

lines = existing.splitlines()
new_lines = []

for task in tasks:
    # Формуємо рядок crontab
    cmd = f"{task['schedule']} /usr/bin/python3.11 {os.path.join(base_path, task['script'])} >> {os.path.join(base_path, task['log'])} 2>&1"
    # Перевіряємо, чи його вже немає
    if cmd not in lines:
        new_lines.append(cmd)

# Об'єднуємо існуючі та нові
all_lines = lines + new_lines
all_text = "\n".join(all_lines) + "\n"

# Записуємо в crontab
proc = subprocess.Popen(["crontab"], stdin=subprocess.PIPE, text=True)
proc.communicate(all_text)

print("Cron tasks added/updated successfully.")
