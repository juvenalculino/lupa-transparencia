#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Find the else line for the modo_meses radio
else_line_idx = None
for i, line in enumerate(lines):
    if line.rstrip() == "        else:":
        else_line_idx = i
        break

if else_line_idx is None:
    print("Could not find the else line for modo_meses")
    sys.exit(1)

# Base indent of the else line
base_indent = len(lines[else_line_idx]) - len(lines[else_line_idx].lstrip())
print(f"Else line at index {else_line_idx}, base indent: {base_indent}")

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

print(f"Else block content is from line {else_line_idx+1} to {block_end-1} (inclusive)")

# Build the new content for the else block (from the line after the else to the line before block_end)
new_block = []

# Helper to create a line with a given indent (absolute number of spaces)
def make_line(indent, content):
    return " " * indent + content + "\n"

# The new else block content:
new_block.append(make_line(base_indent + 4, 'tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])'))
new_block.append(make_line(base_indent + 4, 'with tab1:'))
new_block.append(make_line(base_indent + 8, 'modo_grafo = "Programas com beneficiários em comum"'))
new_block.append(make_line(base_indent + 8, 'meses_consulta = st.multiselect('))
new_block.append(make_line(base_indent + 12, '"Escolha um ou mais meses",'))
new_block.append(make_line(base_indent + 12, 'options=meses_validos,'))
new_block.append(make_line(base_indent + 12, 'format_func=lambda valor: f"{valor}/{ano}",'))
new_block.append(make_line(base_indent + 12, 'key=f"meses_agregado_{beneficio}_{ano}_tab1",'))
new_block.append(make_line(base_indent + 8, ')'))
new_block.append(make_line(base_indent + 4, 'with tab2:'))
new_block.append(make_line(base_indent + 8, 'modo_grafo = "Rede de pessoa relacionada"'))
new_block.append(make_line(base_indent + 8, 'meses_consulta = st.multiselect('))
new_block.append(make_line(base_indent + 12, '"Escolha um ou mais meses",'))
new_block.append(make_line(base_indent + 12, 'options=meses_validos,'))
new_block.append(make_line(base_indent + 12, 'format_func=lambda valor: f"{valor}/{ano}",'))
new_block.append(make_line(base_indent + 12, 'key=f"meses_agregado_{beneficio}_{ano}_tab2",'))
new_block.append(make_line(base_indent + 8, ')'))
new_block.append(make_line(base_indent + 4, 'periodo = modo_meses'))

# Now, replace the lines from else_line_idx+1 to block_end-1 with the new_block
new_lines = lines[:else_line_idx+1] + new_block + lines[block_end:]

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")