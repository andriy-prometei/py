#!/usr/bin/bash

git config --global --add safe.directory /mnt/android/_dl/py

# 1. Налаштувати credential helper (зберігатиме username + token у файлі \~/.git-credentials)
#git config --global credential.helper store

# 2. Перевірити, що налаштування збереглося
#git config --global --get credential.helper
# має вивести: store


echo "→ Перехід до /mnt/android/_dl/py"
cd /mnt/android/_dl/py || { echo "Не можу перейти в /mnt/android/_dl/py"; exit 1; }

echo "→ git add -A ."
git add -A .

echo "→ git commit (якщо є зміни)"
git commit -m "auto $(date '+%Y-%m-%d %H:%M:%S')" || true

echo "→ git push"
git push || { echo "push не вдався"; exit 1; }

echo "Готово."

