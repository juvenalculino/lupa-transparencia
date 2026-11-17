#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# We'll replace lines 90 to 120 (0-indexed) with a corrected version.
# But first, let's find the exact start and end of the block we want to replace.
# We know the start is at line 90 (0-indexed) which is the line: "        modo_meses = st.radio("
# We'll find that line.
start_idx = None
for i, line in enumerate(lines):
    if line.strip().startswith('modo_meses = st.radio('):
        start_idx = i
        break

if start_idx is None:
    print("Could not find modo_meses line")
    sys.exit(1)

# Now we want to replace from start_idx to the line before the next dedent that indicates the end of this block.
# We'll look for a line that has less indentation than the line at start_idx (assuming the block is indented).
base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
# We'll go forward until we find a line that is not empty and has indentation <= base_indent (but not the same line).
end_idx = None
for i in range(start_idx + 1, len(lines)):
    if lines[i].strip() == '':
        continue
    indent = len(lines[i]) - len(lines[i].lstrip())
    if indent <= base_indent:
        end_idx = i
        break
if end_idx is None:
    end_idx = len(lines)

# Now we have the block from start_idx to end_idx-1.
# We'll replace it with a new block.
# We'll construct the new block as a list of strings.

new_block = []

# Keep the same base indent for the new block.
# We'll write:
#         modo_meses = st.radio(
#             "Meses do ano",
#             ["Todos os meses", "Selecionar meses"],
#             horizontal=True,
#             key="modo_meses_agregado",
#         )
#         if modo_meses == "Todos os meses":
#             meses_consulta = meses_validos
#         else:
#             tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])
#             with tab1:
#                 modo_grafo = "Programas com beneficiários em comum"
#                 meses_consulta = st.multiselect(
#                     "Escolha um ou mais meses",
#                     options=meses_validos,
#                     format_func=lambda valor: f"{valor}/{ano}",
#                     key=f"meses_agregado_{beneficio}_{ano}_tab1",
#                 )
#             with tab2:
#                 modo_grafo = "Rede de pessoa relacionada"
#                 meses_consulta = st.multiselect(
#                     "Escolha um ou mais meses",
#                     options=meses_validos,
#                     format_func=lambda valor: f"{valor}/{ano}",
#                     key=f"meses_agregado_{beneficio}_{ano}_tab2",
#                 )
#             periodo = modo_meses

# But note: the variables beneficio and ano are defined earlier in the block? They are in the outer scope.
# We'll keep the same variable names.

# Let's build the lines with the same base_indent.
indent_str = " " * base_indent

new_block.append(indent_str + "modo_meses = st.radio(\n")
new_block.append(indent_str + "    \"Meses do ano\",\n")
new_block.append(indent_str + "    [\"Todos os meses\", \"Selecionar meses\"],\n")
new_block.append(indent_str + "    horizontal=True,\n")
new_block.append(indent_str + "    key=\"modo_meses_agregado\",\n")
new_block.append(indent_str + ")\n")
new_block.append(indent_str + "if modo_meses == \"Todos os meses\":\n")
new_block.append(indent_str + "    meses_consulta = meses_validos\n")
new_block.append(indent_str + "else:\n")
new_block.append(indent_str + "    tab1, tab2 = st.tabs([\"Programas com beneficiários em comum\", \"Programas de uma pessoa\"])\n")
new_block.append(indent_str + "    with tab1:\n")
new_block.append(indent_str + "        modo_grafo = \"Programas com beneficiários em comum\"\n")
new_block.append(indent_str + "        meses_consulta = st.multiselect(\n")
new_block.append(indent_str + "            \"Escolha um ou mais meses\",\n")
new_block.append(indent_str + "            options=meses_validos,\n")
new_block.append(indent_str + "            format_func=lambda valor: f\"{valor}/{ano}\",\n")
new_block.append(indent_str + "            key=f\"meses_agregado_{beneficio}_{ano}_tab1\",\n")
new_block.append(indent_str + "        )\n")
new_block.append(indent_str + "    with tab2:\n")
new_block.append(indent_str + "        modo_grafo = \"Rede de pessoa relacionada\"\n")
new_block.append(indent_str + "        meses_consulta = st.multiselect(\n")
new_block.append(indent_str + "            \"Escolha um ou mais meses\",\n")
new_block.append(indent_str + "            options=meses_validos,\n")
new_block.append(indent_str + "            format_func=lambda valor: f\"{valor}/{ano}\",\n")
new_block.append(indent_str + "            key=f\"meses_agregado_{beneficio}_{ano}_tab2\",\n")
new_block.append(indent_str + "        )\n")
new_block.append(indent_str + "    periodo = modo_meses\n")

# Now replace
new_lines = lines[:start_idx] + new_block + lines[end_idx:]

with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully")