#!/bin/bash

# Папки
DIRS=("results" "funding_results")

# Назва архіву
ARCHIVE="archive_$(date +%Y-%m-%d_%H-%M-%S).zip"

# Збираємо файли і архівуємо
FILES=$(find "${DIRS[@]}" -type f -mtime -3 2>/dev/null)

if [ -n "$FILES" ]; then
    find "${DIRS[@]}" -type f -mtime -3 2>/dev/null | zip -9 "$ARCHIVE" -@
    echo "Архів створено: $ARCHIVE"
else
    echo "Немає файлів за останні 3 дні"
fi
