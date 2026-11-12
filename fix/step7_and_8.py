#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# Step 1: Find the else block for the modo_meses radio (when modo_meses == "Selecionar meses")
# We'll look for the line: "        else:" that is after the line with "if modo_meses == \"Todos os meses\":"
else_line_idx = None
for i in range(1, len(lines)):
    if lines[i].strip() == "else:" and "if modo_meses == \"Todos os meses\":" in lines[i-1]:
        else_line_idx = i
        break

if else_line_idx is None:
    print("Could not find the else line for modo_meses")
    sys.exit(1)

# Find the end of the else block: look for the first line after else_line_idx that has indent <= base_indent and is not empty
base_indent = len(lines[else_line_idx]) - len(lines[else_line_idx].lstrip())
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

# Now, we have the else block from else_line_idx to block_end (exclusive of block_end)
# We'll split the else block into two parts: the part for tab1 and tab2 by replacing the modo_grafo if-else with tabs.

# Extract the else block lines
else_block = lines[else_line_idx:block_end]

# We'll now look for the modo_grafo if-else block inside the else_block.
# We know it starts with a line that contains "if modo_grafo == \"Programas com beneficiários em comum\":"
# and ends before the helper functions comment (which is after the else block, so we don't have to worry).

# Find the start of the modo_grafo if-else block
if_line_idx = None
for i, line in enumerate(else_block):
    if line.strip().startswith('if modo_grafo == "Programas com beneficiários em comum":'):
        if_line_idx = i
        break

if if_line_idx is None:
    print("Could not find the if line for modo_grafo")
    sys.exit(1)

# Find the end of the if-else block: look for the line after the else block of the modo_grafo if-else.
# We'll look for the line that is at the same indentation as the if line and not part of the if-else block.
# But note: the if-else block might be followed by the helper functions comment, which is after the else block we are in.
# However, we are only looking within the else_block, which ends at block_end (exclusive) and the helper functions comment is at block_end (which is not in else_block).
# So we can look for the end of the if-else block by finding the line that is at the same indentation as the if line and is not empty, after the if-else content.

# We'll instead find the line that contains the else of the modo_grafo if-else.
else_line_idx_inner = None
for i in range(if_line_idx, len(else_block)):
    if else_block[i].strip() == "else:":
        else_line_idx_inner = i
        break

if else_line_idx_inner is None:
    print("Could not find the inner else line for modo_grafo")
    sys.exit(1)

# Now, we have:
#   if_line_idx: the line with "if modo_grafo == \"Programas com beneficiários em comum\":"
#   else_line_idx_inner: the line with "else:"
# We'll assume the if block is from if_line_idx+1 to else_line_idx_inner-1
# and the else block is from else_line_idx_inner+1 to the end of the else_block (but we don't know where the else block ends).

# We'll find the end of the else block of the modo_grafo if-else by looking for the first line after else_line_idx_inner that has indent <= the indent of the else_line_idx_inner line and is not empty.
inner_else_indent = len(else_block[else_line_idx_inner]) - len(else_block[else_line_idx_inner].lstrip())
inner_block_end = None
for i in range(else_line_idx_inner + 1, len(else_block)):
    if else_block[i].strip() == '':
        continue
    indent = len(else_block[i]) - len(else_block[i].lstrip())
    if indent <= inner_else_indent:
        inner_block_end = i
        break
if inner_block_end is None:
    inner_block_end = len(else_block)

# Now, we have:
#   if_block = else_block[if_line_idx+1:else_line_idx_inner]
#   else_block_inner = else_block[else_line_idx_inner+1:inner_block_end]
# And the lines after inner_block_end (until the end of else_block) are the lines that come after the modo_grafo if-else block.
# We'll call this the trailing part.

trailing_part = else_block[inner_block_end:]

# Now, we want to replace the modo_grafo if-else block with tabs.

# We'll build the new block for the tabs.
new_block = []

# The tabs block will be at the same indentation as the if line (which is the same as the else line of the modo_meses radio?).
# We'll use the same indentation as the if line.
if_indent = len(else_block[if_line_idx]) - len(else_block[if_line_idx].lstrip())

# Helper to make a line with a given indent (absolute number of spaces)
def make_line(indent, content):
    return " " * indent + content + "\n"

# Build the tabs block
new_block.append(make_line(if_indent, 'tab1, tab2 = st.tabs(["Programas com beneficiários em comum", "Programas de uma pessoa"])'))
new_block.append(make_line(if_indent, 'with tab1:'))
new_block.append(make_line(if_indent + 4, 'modo_grafo = "Programas com beneficiários em comum"'))
# Now, we need to add the if_block content, but we need to increase the indentation by 4 (because we are inside the with tab1: block)
for line in else_block[if_line_idx+1:else_line_idx_inner]:
    # The line already has the indentation of the if_block (which is relative to the if line).
    # We want to add 4 more spaces to be inside the with tab1: block.
    new_block.append(" " * (if_indent + 4) + line.lstrip())
new_block.append(make_line(if_indent, 'with tab2:'))
new_block.append(make_line(if_indent + 4, 'modo_grafo = "Rede de pessoa relacionada"')
for line in else_block[else_line_idx_inner+1:inner_block_end]:
    new_block.append(" " * (if_indent + 4) + line.lstrip())
# Then, add the trailing part (which is after the modo_grafo if-else block) at the same indentation as the if line.
for line in trailing_part:
    new_block.append(" " * if_indent + line.lstrip())

# Now, we have the new block for the else_block (from the if line to the end of the else_block).
# We'll replace the lines from else_line_idx to block_end with:
#   the lines from else_line_idx to the if_line_idx (exclusive) [which is the lines before the if line] 
#   then the new_block
#   then the lines from block_end to the end of the file (but note: we are replacing the entire else_block, so we don't need the trailing part again? Actually, we included the trailing_part in the new_block).

# Actually, we are replacing the entire else_block (from else_line_idx to block_end) with:
#   the lines from else_line_idx to if_line_idx (exclusive) [which is the lines before the if line] 
#   then the new_block

# But note: the else_block starts at else_line_idx and goes to block_end (exclusive).
# We want to keep the lines from else_line_idx to if_line_idx (exclusive) and then replace the rest (from if_line_idx to block_end) with the new_block.

# So:
#   lines[else_line_idx:if_line_idx] (relative to the else_block start) are the lines before the if line.
#   Then we replace from if_line_idx to block_end with new_block.

# Therefore, we do:
#   new_else_block = lines[else_line_idx:if_line_idx] + new_block
#   Then, the entire new lines will be:
#       lines[0:else_line_idx] + new_else_block + lines[block_end:]

new_else_block = lines[else_line_idx:if_line_idx] + new_block
new_lines = lines[:else_line_idx] + new_else_block + lines[block_end:]

# Now, we have the file with the tabs instead of the modo_grafo radio.
# We'll write this to a temporary file and then proceed to step 8.

# But note: we are going to do step 8 in the same script, so we'll keep the new_lines and proceed.

# Step 2: Add anomaly detection in both tabs.

# We'll now look for the tab1 and tab2 blocks in the new_lines.
# We know the structure now: we have the tabs block we just inserted.

# We'll find the lines for the tabs block again in the new_lines.
# We'll look for the line: "tab1, tab2 = st.tabs([\"Programas com beneficiários em comum\", \"Programas de uma pessoa\"])"

tab_line_idx = None
for i, line in enumerate(new_lines):
    if line.strip().startswith('tab1, tab2 = st.tabs(['):
        tab_line_idx = i
        break

if tab_line_idx is None:
    print("Could not find the tabs line")
    sys.exit(1)

# We'll assume the structure is:
#   line tab_line_idx: the tabs line
#   line tab_line_idx+1: "with tab1:"
#   then the tab1 content until we see "with tab2:"
#   line with tab2: the "with tab2:" line
#   then the tab2 content until we see a line that is at the same indentation as the "with tab2:" line (or the end of the block)

# We'll find the line with "with tab1:" and "with tab2:"
with_tab1_line = None
with_tab2_line = None
for i in range(tab_line_idx, len(new_lines)):
    if new_lines[i].strip() == "with tab1:":
        with_tab1_line = i
    if new_lines[i].strip() == "with tab2:":
        with_tab2_line = i

if with_tab1_line is None or with_tab2_line is None:
    print("Could not find with tab1 or with tab2 line")
    sys.exit(1)

# Now, we have:
#   tab1 content: from with_tab1_line+1 to with_tab2_line-1
#   tab2 content: from with_tab2_line+1 to the end of the block (we'll find the end by looking for a line that is at the same indentation as the with_tab2_line line and is not empty, or the end of the file)

# We'll find the end of the tab2 block: look for the first line after with_tab2_line that has indent <= the indent of the with_tab2_line line and is not empty.
tab2_indent = len(new_lines[with_tab2_line]) - len(new_lines[with_tab2_line].lstrip())
tab2_end = None
for i in range(with_tab2_line + 1, len(new_lines)):
    if new_lines[i].strip() == '':
        continue
    indent = len(new_lines[i]) - len(new_lines[i].lstrip())
    if indent <= tab2_indent:
        tab2_end = i
        break
if tab2_end is None:
    tab2_end = len(new_lines)

# Similarly, we'll find the end of the tab1 block: it should be the line before the with_tab2_line.
# But note: the tab1 block ends at the line before the with_tab2_line.
tab1_end = with_tab2_line  # exclusive

# Now, we have:
#   tab1_content = new_lines[with_tab1_line+1:tab1_end]
#   tab2_content = new_lines[with_tab2_line+1:tab2_end]

# We'll define a function to insert anomaly detection code into a tab content block.
def insert_anomaly_detection(tab_content_lines):
    """
    Given the lines of a tab content block (without the leading 'with tabX:' line),
    insert anomaly detection code after the graph is created and before the metrics are displayed.
    Also, add a section for anomaly detection after the metrics display and before the export buttons.
    """
    # We'll look for the line that sets the nodes and edges for the agraph.
    # We'll look for the line: "nodes, edges = nx_to_agraph(rede_programas)"
    nx_to_agraph_line = None
    for i, line in enumerate(tab_content_lines):
        if line.strip().startswith('nodes, edges = nx_to_agraph(rede_programas)'):
            nx_to_agraph_line = i
            break

    if nx_to_agraph_line is None:
        # If we can't find the nx_to_agraph line, we'll try to insert after the graph is created and before the metrics.
        # We'll look for the line that starts the metrics display: "m1, m2, m3 = st.columns(3)"
        metric_cols_line = None
        for i, line in enumerate(tab_content_lines):
            if line.strip().startswith('m1, m2, m3 = st.columns(3)'):
                metric_cols_line = i
                break
        if metric_cols_line is None:
            # If we still can't find, we'll insert at the end of the tab content (but before the export buttons?).
            # We'll just return the original lines and print a warning.
            print("Warning: Could not find nx_to_agraph or metric columns line. Anomaly detection not inserted.")
            return tab_content_lines

        # We'll insert the anomaly detection code right before the metric_cols_line.
        insert_line = metric_cols_line
    else:
        # We'll insert the anomaly detection code right after the nx_to_agraph line and before the config line.
        # We'll look for the line after the nx_to_agraph line that sets the config.
        # We'll insert after the nx_to_agraph line and before the config line.
        insert_line = nx_to_agraph_line + 1

    # We'll build the anomaly detection code block.
    # We'll assume the tab content lines are indented by 4 spaces (because they are inside the with tab: block).
    # We'll get the indentation of the first line of the tab content.
    if tab_content_lines:
        first_line_indent = len(tab_content_lines[0]) - len(tab_content_lines[0].lstrip())
    else:
        first_line_indent = 4  # default

    # The anomaly detection code we want to insert:
    anomaly_code = [
        "        # ANOMALY DETECTION\n",
        "        graph_anomalies = anomaly_detection.detect_anomalies_in_graph(rede_programas)\n",
        "        insights = anomaly_detection.generate_anomaly_insights(graph_anomalies)\n",
        "\n"
    ]

    # We'll adjust the indentation of the anomaly code to match the tab content indentation.
    # We'll add the first_line_indent to each line.
    anomaly_code = [(" " * first_line_indent) + line if line.startswith(" ") else (" " * first_line_indent) + line for line in anomaly_code]

    # Insert the anomaly code at the insert_line.
    new_tab_content = tab_content_lines[:insert_line] + anomaly_code + tab_content_lines[insert_line:]

    # Now, we also want to add a section for displaying the anomalies after the metrics display and before the export buttons.
    # We'll look for the export buttons section. We'll look for the line that starts with "exp_col1, exp_col2, exp_col3 = st.columns(3)"
    # or the line that contains "st.download_button" for PNG, SVG, JSON.
    # We'll insert the anomaly display section right before the export buttons.

    # We'll look for the line that starts the export buttons columns.
    exp_cols_line = None
    for i, line in enumerate(new_tab_content):
        if line.strip().startswith('exp_col1, exp_col2, exp_col3 = st.columns(3)'):
            exp_cols_line = i
            break

    if exp_cols_line is None:
        # If we can't find the export columns, we'll try to insert before the first st.download_button.
        download_line = None
        for i, line in enumerate(new_tab_content):
            if line.strip().startswith('st.download_button'):
                download_line = i
                break
        if download_line is None:
            print("Warning: Could not find export columns or download button. Anomaly display not inserted.")
            return new_tab_content
        insert_display_line = download_line
    else:
        insert_display_line = exp_cols_line

    # We'll build the anomaly display code block.
    anomaly_display_code = [
        "        # ANOMALY DISPLAY\n",
        "        if graph_anomalies or insights[0] != \"Nenhuma anomalia significativa detectada nos dados atuais.\":\n",
        "            st.subheader(\"Detecção de Anomalias\")\n",
        "            for insight in insights:\n",
        "                st.info(insight)\n",
        "            if graph_anomalies:\n",
        "                st.subheader(\"Nós Anômalos Detectados\")\n",
        "                anomaly_data = []\n",
        "                for node, score, reason in graph_anomalies:\n",
        "                    label = rede_programas.nodes[node].get('label', node)\n",
        "                    anomaly_data.append({\n",
        "                        \"Nó\": label,\n",
        "                        \"ID\": node,\n",
        "                        \"Score\": score,\n",
        "                        \"Motivo\": reason\n",
        "                    })\n",
        "                st.dataframe(pd.DataFrame(anomaly_data))\n",
        "\n"
    ]

    # Adjust the indentation of the anomaly display code.
    anomaly_display_code = [(" " * first_line_indent) + line if line.startswith(" ") else (" " * first_line_indent) + line for line in anomaly_display_code]

    # Insert the anomaly display code at the insert_display_line.
    new_tab_content = new_tab_content[:insert_display_line] + anomaly_display_code + new_tab_content[insert_display_line:]

    return new_tab_content

# Now, we insert anomaly detection in both tabs.
new_tab1_content = insert_anomaly_detection(new_lines[with_tab1_line+1:tab1_end])
new_tab2_content = insert_anomaly_detection(new_lines[with_tab2_line+1:tab2_end])

# Now, we rebuild the new_lines with the updated tab contents.
# We'll keep the lines up to with_tab1_line, then the with_tab1_line line, then the new tab1 content,
# then the with_tab2_line line, then the new tab2 content, then the lines from tab2_end to the end.

new_lines = new_lines[:with_tab1_line+1] + new_tab1_content + new_lines[with_tab2_line:with_tab2_line+1] + new_tab2_content + new_lines[tab2_end:]

# Write the file
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully with tabs and anomaly detection.")