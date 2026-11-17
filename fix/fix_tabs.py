#!/usr/bin/env python3
import os
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the start of the radio assignment: we look for the line that contains "modo_grafo = st.radio("
start_idx = None
for i, line in enumerate(lines):
    if "modo_grafo = st.radio(" in line:
        start_idx = i
        break

if start_idx is None:
    print("Radio assignment not found")
    sys.exit(1)

# Find the end of the else block: we look for the line that is just before the helper functions.
# We know the helper functions start at line 904 (0-indexed line 903) with the string "# Helper functions for graph export"
end_idx = None
for i, line in enumerate(lines):
    if "# Helper functions for graph export" in line:
        end_idx = i   # we want to replace up to (but not including) this line
        break

if end_idx is None:
    print("Helper functions line not found")
    sys.exit(1)

# The block we want to replace is from start_idx to end_idx (exclusive of end_idx)
old_block = lines[start_idx:end_idx]

# Now, we want to remove the radio assignment (the first 6 lines of old_block) and then split the rest into if and else.
# The radio assignment is 6 lines: from start_idx to start_idx+6
radio_lines = old_block[0:6]
if_else_block = old_block[6:]   # This is the if-else block (starting at the if statement)

# Now, split the if_else_block into if_block and else_block by finding the line that contains "else:"
else_line_idx = None
for i, line in enumerate(if_else_block):
    if line.strip() == "else:":
        else_line_idx = i
        break

if else_line_idx is None:
    print("Else line not found")
    sys.exit(1)

if_block = if_else_block[0:else_line_idx]   # from the start of the if_else_block to the line before the else
else_block = if_else_block[else_line_idx+1:]   # from the line after the else to the end

# Build the new tab block
new_block = []
new_block.append('tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])\n')
new_block.append('    with tab1:\n')
new_block.append('        modo_grafo = "Programas com beneficiários em comum"\n')
for line in if_block[1:]:
    if line.startswith('    '):
        new_block.append('        ' + line[4:])
    else:
        new_block.append('        ' + line)
new_block.append('    with tab2:\n')
new_block.append('        modo_grafo = "Rede de pessoa relacionada"\n')
for line in else_block[1:]:
    if line.startswith('    '):
        new_block.append('        ' + line[4:])
    else:
        new_block.append('        ' + line)

# Now, replace the old_block in the lines with the new_block
new_lines = lines[:start_idx] + new_block + lines[end_idx:]

# Write the file
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")