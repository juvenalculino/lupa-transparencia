#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Lines to adjust: from line 100 to line 116 (1-indexed) => indices 99 to 115 inclusive.
start_idx = 99  # line 100
end_idx = 115   # line 116

for i in range(start_idx, end_idx + 1):
    line = lines[i]
    if line.startswith('    '):  # at least 4 spaces
        # Remove 4 spaces from the beginning
        lines[i] = line[4:]
    # else leave as is (should not happen)

with open(file_path, "w") as f:
    f.writelines(lines)

print("Adjusted indentation for lines 100-116")