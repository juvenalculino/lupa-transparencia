#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# We want to replace lines 99 to 109 (1-indexed) which are indices 98 to 108 (0-indexed)
start_idx = 98   # line 99
end_idx = 108    # line 109 (inclusive? we want to replace up to line 109, so we will replace indices 98 to 108 inclusive, which is 11 lines)

# Compute the indentation of the line at start_idx (the original line 99)
original_line = lines[start_idx]
indent = len(original_line) - len(original_line.lstrip())

# Build the new block
new_block = []

# Line 99: tabs line
new_block.append(" " * indent + "tab1, tab2 = st.tabs([\"Programas com beneficiários em comum\", \"Programas de uma pessoa\"])\n")
# Line 100: with tab1:
new_block.append(" " * indent + "    with tab1:\n")
# Line 101: modo_grafo for tab1
new_block.append(" " * indent + "        modo_grafo = \"Programas com beneficiários em comum\"\n")
# Line 102: start of multiselect for tab1
new_block.append(" " * indent + "        meses_consulta = st.multiselect(\n")
# Line 103: label
new_block.append(" " * indent + "            \"Escolha um ou mais meses\",\n")
# Line 104: options
new_block.append(" " * indent + "            options=meses_validos,\n")
# Line 105: format_func
new_block.append(" " * indent + "            format_func=lambda valor: f\"{valor}/{ano}\",\n")
# Line 106: key for tab1
new_block.append(" " * indent + "            key=f\"meses_agregado_{beneficio}_{ano}_tab1\",\n")
# Line 107: closing parenthesis
new_block.append(" " * indent + "        )\n")
# Line 108: with tab2:
new_block.append(" " * indent + "    with tab2:\n")
# Line 109: modo_grafo for tab2
new_block.append(" " * indent + "        modo_grafo = \"Rede de pessoa relacionada\"\n")
# Line 110: start of multiselect for tab2
new_block.append(" " * indent + "        meses_consulta = st.multiselect(\n")
# Line 111: label
new_block.append(" " * indent + "            \"Escolha um ou mais meses\",\n")
# Line 112: options
new_block.append(" " * indent + "            options=meses_validos,\n")
# Line 113: format_func
new_block.append(" " * indent + "            format_func=lambda valor: f\"{valor}/{ano}\",\n")
# Line 114: key for tab2
new_block.append(" " * indent + "            key=f\"meses_agregado_{beneficio}_{ano}_tab2\",\n")
# Line 115: closing parenthesis
new_block.append(" " * indent + "        )\n")
# Line 116: periodo = modo_meses (after the tabs, at the same indentation as the tabs line)
new_block.append(" " * indent + "    periodo = modo_meses\n")

# Now, replace the old block with the new block
new_lines = lines[:start_idx] + new_block + lines[end_idx+1:]

# Write the file
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")