#!/bin/bash

DIR="${1:-.}"

echo "Directory: $DIR"
echo "---------------------------------------"

# Total apparent size
APPARENT=$(du -sh "$DIR" | awk '{print $1}')
echo "Apparent size:      $APPARENT"

# Actual disk usage (allocated size)
# -S flag makes du show the **actual** allocated space ignoring subdirs overhead
ACTUAL=$(du -Ssh "$DIR" | awk '{print $1}')
echo "Allocated size:     $ACTUAL"

# Number of files
FILES=$(find "$DIR" -type f | wc -l)
echo "Total files:        $FILES"

echo "---------------------------------------"
read -n 1 -s -r -p "Press any key to exit..."
echo
