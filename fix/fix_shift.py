#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the line with "else:" that is preceded by a line containing "if modo_meses == \"Todos os meses\":"
else_line_idx = None
for i in range(1, len(lines)):
    if lines[i].strip() == "else:" and "if modo_meses == \"Todos os meses\":" in lines[i-1]:
        else_line_idx = i
        break

if else_line_idx is None:
    print("Could not find the else line for modo_meses")
    sys.exit(1)

base_indent = len(lines[else_line_idx]) - len(lines[else_line_idx].lstrip())
print(f"Else line index: {else_line_idx}, base indent: {base_indent}")

# Find the end of the else block: look for the first line after else_line_idx that has indent <= base_indent and is not empty
block_end = None
for i in range(else_line_idx + 1, len(lines)):
    if lines[i].strip() == '':
        continue
    indent = len(lines[i]) - len(lines[i].lstrip())
    if indent <= base_indent:
        block_end = i
        break
if block_end is None:
    block_end = len(lines)

print(f"Else block ends at line {block_end} (exclusive)")

# Now, we want to re-indent the lines in the range [else_line_idx+1, block_end) so that they are at base_indent + 4
# (i.e., one level deeper than the else line) but we must keep the structure: the first line should be the tabs line,
# then the with tab1: line, then the content of tab1, then with tab2: line, then content of tab2, then the periodo line.
# However, the current lines might be over-indented. We'll simply set the indentation of each line to base_indent + 4
# plus the relative indentation within the block? Actually, we want to keep the relative indentation of the lines within the block.
# So we will compute the current indentation of each line relative to the else line, and then set the new indentation to base_indent + 4 + (current_indent - (base_indent + 4))? 
# Wait, the current lines are already indented by some amount. We want to shift the entire block left by 4 spaces if it is over-indented by 4.

# Let's compute the indentation of the first line after the else line.
first_line_indent = len(lines[else_line_idx+1]) - len(lines[else_line_idx+1].lstrip())
# We expect the first line after else to be the tabs line, which should be at base_indent + 4.
# If it is at base_indent + 8, then we need to subtract 4 from all lines in the block.
shift = first_line_indent - (base_indent + 4)
print(f"Shift needed: {shift}")

# If shift is 0, the block is already correctly indented.
# If shift is positive, we need to remove that many spaces from the beginning of each line in the block.
# If shift is negative, we need to add spaces (but that shouldn't happen).

new_lines = []
for i, line in enumerate(lines):
    if i >= else_line_idx+1 and i < block_end:
        # This line is inside the else block.
        if shift > 0:
            # Remove shift spaces from the beginning, but only if the line has at least that many spaces.
            if len(line) - len(line.lstrip()) >= shift:
                line = line[shift:]
            else:
                # If not enough spaces, we leave it as is (but this shouldn't happen)
                pass
        # If shift is negative, we would add spaces, but we don't expect that.
    new_lines.append(line)

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")