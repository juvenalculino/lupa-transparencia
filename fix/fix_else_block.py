#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the line with "else:" that is preceded by a line with "if modo_meses == \"Todos os meses\":"
# We'll search for the pattern.
else_line_idx = None
for i in range(1, len(lines)):
    if lines[i].strip() == "else:" and "if modo_meses == \"Todos os meses\":"
            in lines[i-1]:
        else_line_idx = i
        break

if else_line_idx is None:
    # Try a more general search: find an else: line that has an if line before it with modo_meses
    for i in range(1, len(lines)):
        if lines[i].strip() == "else:" and "modo_meses == \"Todos os meses\"" in lines[i-1]:
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

# Now, we want to modify the lines in the range [else_line_idx+1, block_end)
# We'll create a new list for this block.

new_block = []

# We'll process line by line, but we need to know the structure.
# We know the first line after else: should be the tab1, tab2 line.
# We'll set its indent to base_indent + 4.
# Then we expect a line with "with tab1:" (maybe after some blank lines? but there shouldn't be)
# We'll set that line's indent to base_indent + 4.
# Then we expect the lines inside the with tab1: block until we see a line that is at the same indent as the with tab1: line? Actually, we'll just keep the lines as they are, but we will adjust the with tab2: line and the periodo line.

# Instead, we'll do a simple approach: we know the exact lines we want to replace because we saw them.
# We'll replace from else_line_idx+1 to block_end with a new block that we construct.

# Let's extract the current block lines for reference.
current_block = lines[else_line_idx+1:block_end]
print("Current block:")
for idx, line in enumerate(current_block):
    print(f"{else_line_idx+1+idx:4}: {repr(line.rstrip())}")

# We'll build the new block as follows:
#   (indent base_indent+4) tab1, tab2 = st.tabs([...])
#   (indent base_indent+4) with tab1:
#   (indent base_indent+8) modo_grafo = "..."
#   (indent base_indent+8) meses_consulta = st.multiselect(...)
#   (indent base_indent+4) with tab2:
#   (indent base_indent+8) modo_grafo = "..."
#   (indent base_indent+8) meses_consulta = st.multiselect(...)
#   (indent base_indent+4) periodo = modo_meses

# But we need to get the actual content of the tabs line, the modo_grafo lines, and the multiselect lines from the current block.

# Let's assume the structure is exactly as we saw and extract by line offset.

# We'll try to find the line that contains "tab1, tab2 = st.tabs"
tabs_line = None
for i, line in enumerate(current_block):
    if "tab1, tab2 = st.tabs" in line:
        tabs_line = i
        break
if tabs_line is None:
    print("Could not find tabs line")
    sys.exit(1)

# The line after tabs_line should be the with tab1: line.
with_tab1_line = tabs_line + 1
# Then we expect some lines for the tab1 block until we see a line that contains "with tab2:"
with_tab2_line = None
for i in range(with_tab1_line + 1, len(current_block)):
    if "with tab2:" in current_block[i]:
        with_tab2_line = i
        break
if with_tab2_line is None:
    print("Could not find with tab2 line")
    sys.exit(1)

# Then we expect some lines for the tab2 block until we see a line that contains "periodo = modo_meses"
periodo_line = None
for i in range(with_tab2_line + 1, len(current_block)):
    if "periodo = modo_meses" in current_block[i]:
        periodo_line = i
        break
if periodo_line is None:
    print("Could not find periodo line")
    sys.exit(1)

# Now we have the indices within current_block:
#   tabs_line
#   with_tab1_line
#   with_tab2_line
#   periodo_line

# We'll build new_block:
#   Keep the tabs_line as is, but set its indent to base_indent+4.
#   Keep the with_tab1_line as is, but set its indent to base_indent+4.
#   Keep the lines from with_tab1_line+1 to with_tab2_line-1 as is (they should already be at base_indent+8?).
#   Keep the with_tab2_line as is, but set its indent to base_indent+4.
#   Keep the lines from with_tab2_line+1 to periodo_line-1 as is.
#   Keep the periodo_line as is, but set its indent to base_indent+4.

# But we must also consider that there might be blank lines. We'll preserve them.

# Let's do it.

# Helper to adjust indent of a line to a target indent (absolute number of spaces)
def set_indent(line, target_indent):
    stripped = line.lstrip()
    return " " * target_indent + stripped

# Process the block line by line
for i, line in enumerate(current_block):
    if i == tabs_line:
        new_block.append(set_indent(line, base_indent + 4))
    elif i == with_tab1_line:
        new_block.append(set_indent(line, base_indent + 4))
    elif i == with_tab2_line:
        new_block.append(set_indent(line, base_indent + 4))
    elif i == periodo_line:
        new_block.append(set_indent(line, base_indent + 4))
    else:
        # Keep the line as is (we assume its indentation is already correct relative to the block)
        new_block.append(line)

# Now replace the block in the lines
new_lines = lines[:else_line_idx+1] + new_block + lines[block_end:]

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")