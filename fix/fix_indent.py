#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the start of the else block: we look for the line that contains "        else:" (with exactly 8 spaces at the start?)
# Actually, we know the line number from earlier: line 460 (0-indexed 459) is the else line.
# But let's search for it to be safe.
start_idx = None
for i, line in enumerate(lines):
    if line.rstrip() == "        else:":
        start_idx = i
        break

if start_idx is None:
    print("Else block start not found")
    sys.exit(1)

# Find the end of the else block: we look for the line that is just before the helper functions.
end_idx = None
for i, line in enumerate(lines[start_idx:], start=start_idx):
    if "# Helper functions for graph export" in line:
        end_idx = i
        break

if end_idx is None:
    print("Helper functions line not found")
    sys.exit(1)

# Now we have the else block from start_idx to end_idx (exclusive of end_idx)
else_block = lines[start_idx:end_idx]

# We want to replace the else_block with a new version that uses tabs instead of radio.
# First, let's extract the content of the else_block without the leading "        else:" line.
# The else_block[0] is the "        else:" line.
# The rest is the indented block (should be indented by 4 spaces relative to the else line? Actually, the else line is at some indent level, and the block inside is indented by 4 more spaces.
# We'll assume the else line is indented by N spaces, and the block inside is indented by N+4 spaces.
# We'll compute N from the else line.
else_line = else_block[0]
indent_len = len(else_line) - len(else_line.lstrip())
# The inner block should be indented by indent_len + 4 spaces.
inner_indent = " " * (indent_len + 4)

# Now, we want to split the inner block into two parts: the part for tab1 and the part for tab2.
# We know the inner block currently has an if-else structure.
# We'll find the line that is exactly "else:" at the inner indent level.
inner_block_lines = else_block[1:]  # skip the else line

# Find the line that is exactly inner_indent + "else:"
else_line_inner = None
for i, line in enumerate(inner_block_lines):
    if line.rstrip() == inner_indent + "else:":
        else_line_inner = i
        break

if else_line_inner is None:
    print("Inner else line not found")
    sys.exit(1)

# Split the inner block into if_part and else_part (excluding the else line itself)
if_part = inner_block_lines[:else_line_inner]
else_part = inner_block_lines[else_line_inner+1:]  # skip the else line

# Now, we build the new else_block:
# We keep the else_line (the "        else:") as is.
# Then we replace the if-else block with a tab block.
# The tab block should be at the same indentation level as the old if-else block (i.e., inner_indent).
# We'll create:
#     tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])
#     with tab1:
#         modo_grafo = "Programas com beneficiários em comum"
#         [if_part content, but we need to adjust indentation: currently if_part is at inner_indent, we want to add 4 more spaces?]
#     with tab2:
#         modo_grafo = "Rede de pessoa relacionada"
#         [else_part content, similarly adjusted]

# However, note that the if_part and else_part currently contain the code that was inside the if and else blocks, respectively.
# They are already indented by inner_indent (because they were inside the if-else block which was at inner_indent).
# When we put them inside a with block, we need to add another level of indentation (4 spaces).
# So we will add 4 spaces to each line of if_part and else_part.

# But wait: look at the original code: the if_part starts with a line that is at inner_indent, and that line is the "if not anos_rede:" line.
# In the new structure, we want:
#     with tab1:
#         modo_grafo = "Programas com beneficiários em comum"
#         if not anos_rede:
#             ...   [this should be indented by 8 spaces relative to the with tab1: line? Actually, the with tab1: line is at inner_indent, then we add 4 spaces for the content inside the with block, then the if statement should be at inner_indent + 4 + 4? Let's think.

# Instead, let's keep the same relative indentation: we will keep if_part and else_part as they are, and then we will wrap them in the with blocks, adding 4 spaces to the with block lines and then 4 spaces to the content inside the with blocks? Actually, the with block line itself should be at inner_indent, and then the content inside the with block should be at inner_indent + 4.

# So we will do:
# new_inner_block = []
# new_inner_block.append(inner_indent + 'tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])\n')
# new_inner_block.append(inner_indent + '    with tab1:\n')
# new_inner_block.append(inner_indent + '        modo_grafo = "Programas com beneficiários em comum"\n')
# for line in if_part:
#     # line already has inner_indent at the beginning? Actually, the lines in if_part are exactly as they appeared in the file, which includes the inner_indent at the beginning.
#     # We want to add 4 more spaces to indent them relative to the with tab1: line.
#     new_inner_block.append(inner_indent + '    ' + line)
# new_inner_block.append(inner_indent + '    with tab2:\n')
# new_inner_block.append(inner_indent + '        modo_grafo = "Rede de pessoa relacionada"\n')
# for line in else_part:
#     new_inner_block.append(inner_indent + '    ' + line)

# However, note that the if_part and else_part lines already have the inner_indent at the beginning. So if we add inner_indent + '    ' + line, we are doubling the inner_indent.

# Let's instead strip the inner_indent from each line in if_part and else_part, then add the desired indentation.

# Actually, it's easier: we know that the if_part and else_part are exactly the lines that were inside the if and else blocks, and they are already indented by inner_indent relative to the else line.
# We want to keep the same relative indentation inside the with blocks, so we should add 4 spaces (for the with block) to the existing indentation.
# So we can do: for each line in if_part, we keep it as is (because it already has the inner_indent) and then we add 4 spaces at the beginning? No, that would be too much.

# Let's take a step back and write the new block as a string and then replace.

# We'll construct the new else_block lines:

new_else_block = []
new_else_block.append(else_line)  # the "        else:" line

# Now add the tab block
new_else_block.append(inner_indent + 'tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])\n')
new_else_block.append(inner_indent + '    with tab1:\n')
new_else_block.append(inner_indent + '        modo_grafo = "Programas com beneficiários em comum"\n')
# Now add the if_part lines, but we need to indent them an additional 4 spaces (because they are inside the with tab1: block)
for line in if_part:
    # line already has inner_indent at the beginning? Let's check: the original if_part lines were inside the if block, which was at the same indentation level as the else block's inner block.
    # Actually, the else block's inner block (the lines after the else:) are at inner_indent.
    # The if block inside that is at inner_indent, and the else block inside that is at inner_indent.
    # So the if_part lines are exactly at inner_indent (they start with inner_indent).
    # We want to put them inside a with tab1: block, which is at inner_indent, and then the content inside the with block should be at inner_indent + 4.
    # So we need to add 4 spaces to the beginning of each line in if_part.
    new_else_block.append(inner_indent + '    ' + line)
new_else_block.append(inner_indent + '    with tab2:\n')
new_else_block.append(inner_indent + '        modo_grafo = "Rede de pessoa relacionada"\n')
for line in else_part:
    new_else_block.append(inner_indent + '    ' + line)

# Now, replace the old else_block with the new_else_block in the lines
new_lines = lines[:start_idx] + new_else_block + lines[end_idx:]

# Write the file
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")