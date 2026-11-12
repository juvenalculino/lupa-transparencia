#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# We'll find the tab1 and tab2 blocks by looking for the lines:
#     with tab1:
# and
#     with tab2:
# We know they are in the else block of the modo_meses radio.

# First, let's find the else block for modo_meses radio (we already did this in a previous fix, but we'll do it again)
else_line_idx = None
for i, line in enumerate(lines):
    if line.rstrip() == "        else:":
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
# We'll split the else block into tab1 and tab2 sections by looking for the lines:
#     with tab1:
# and
#     with tab2:
# We'll assume the structure is:
#     with tab1:
#         ... tab1 content ...
#     with tab2:
#         ... tab2 content ...

# We'll find the lines for "with tab1:" and "with tab2:" within the else block.
tab1_line = None
tab2_line = None
for i in range(else_line_idx, block_end):
    if lines[i].strip() == "with tab1:":
        tab1_line = i
    if lines[i].strip() == "with tab2:":
        tab2_line = i

if tab1_line is None or tab2_line is None:
    print("Could not find tab1 or tab2 line")
    sys.exit(1)

# We'll assume the tab1 content goes from tab1_line+1 to tab2_line-1
# and the tab2 content goes from tab2_line+1 to block_end-1

# Now, we'll modify the tab1 content and tab2 content.

# We'll define a function to insert anomaly detection code into a tab content block.
def insert_anomaly_detection(tab_content_lines, tab_name):
    """
    Given the lines of a tab content block (without the leading 'with tabX:' line),
    insert anomaly detection code after the graph is created and before the metrics are displayed.
    Also, modify the metrics column to show insights and anomalous nodes.
    """
    # We'll look for the line that starts with "n_programas = rede_programas.number_of_nodes()"
    # or similar. Actually, we want to insert after the graph is filtered and before the metrics.
    # We'll look for the line that sets the metrics (the st.columns(3) for m1, m2, m3) and insert before that.
    # But note: the structure might be different for tab1 and tab2.

    # Let's look for the line that contains "st.columns(3)" and the metric display.
    # We'll insert anomaly detection code right before the metrics display.

    # We'll also need to change the metrics column to show insights.

    # We'll break the tab content into lines and process.

    # We'll find the line index of the metric display (the line with "m1, m2, m3 = st.columns(3)")
    metric_cols_line = None
    for i, line in enumerate(tab_content_lines):
        if "m1, m2, m3 = st.columns(3)" in line:
            metric_cols_line = i
            break

    if metric_cols_line is None:
        # If we can't find the metric columns, we'll try to insert after the graph filtering.
        # Look for the line that sets minimo_compartilhados or the line after the if n_programas block.
        # For simplicity, we'll insert at the end of the tab content (but before the export buttons?).
        # We'll instead return the original lines and print a warning.
        print(f"Warning: Could not find metric columns in {tab_name}. Anomaly detection not inserted.")
        return tab_content_lines

    # We'll insert the anomaly detection code right before the metric_cols_line.
    # We'll also need to change the metrics column block (which starts at metric_cols_line and goes for a few lines).

    # Let's first capture the lines from metric_cols_line to the end of the metrics display.
    # We'll look for the line that ends the metrics display (the line after the last st.metric or the column block).
    # We'll assume the metrics display is a block of lines that starts with the columns line and ends before the next major section.

    # We'll find the end of the metrics display by looking for a line that is not indented as part of the columns block.
    # But note: the metrics display is inside the columns, so we'll look for the line that is at the same indentation as the columns line.

    # Actually, the metrics display is:
    #     with met_col:
    #         st.subheader("Métricas da Rede")
    #         for label, value in metricas_formatadas:
    #             st.metric(label, value)
    # We'll change this block to include insights.

    # Instead of trying to replace the entire block, we'll insert the anomaly detection code before the metrics display
    # and then change the metrics display block to show insights.

    # We'll insert the anomaly detection code as a block of lines.

    anomaly_detection_code = [
        "        # ANOMALY DETECTION\n",
        "        graph_anomalies = anomaly_detection.detect_anomalies_in_graph(rede_programas)\n",
        "        insights = anomaly_detection.generate_anomaly_insights(graph_anomalies)\n",
        "\n"
    ]

    # We'll insert this code at the metric_cols_line (so it goes before the metrics display).
    # But note: we want to insert after the graph is created and before the metrics.
    # The metric_cols_line is the start of the metrics display, so inserting before it is correct.

    # However, we must adjust the indentation. The anomaly detection code should be at the same indentation level as the tab content.
    # We'll assume the tab content is indented by 4 spaces (because it's inside the with tab: block).
    # We'll keep the same indentation.

    # We'll create the lines to insert with the same indentation as the tab content lines.
    # We'll look at the first line of tab_content_lines to get the indentation.
    if tab_content_lines:
        first_line_indent = len(tab_content_lines[0]) - len(tab_content_lines[0].lstrip())
    else:
        first_line_indent = 4  # default

    # Adjust the anomaly detection code to have the same indentation.
    anomaly_detection_code = [
        " " * first_line_indent + line if not line.startswith(" " * first_line_indent) else line
        for line in anomaly_detection_code
    ]

    # Insert the code
    new_tab_content = tab_content_lines[:metric_cols_line] + anomaly_detection_code + tab_content_lines[metric_cols_line:]

    # Now, we need to change the metrics display block to show insights.
    # We'll look for the line with "with met_col:" inside the new_tab_content.
    # We'll change the block that follows.

    # Find the line with "with met_col:"
    met_col_line = None
    for i, line in enumerate(new_tab_content):
        if line.strip() == "with met_col:":
            met_col_line = i
            break

    if met_col_line is None:
        print(f"Warning: Could not find met_col line in {tab_name}. Metrics not updated for insights.")
        return new_tab_content

    # We'll change the lines from met_col_line to the end of the met_col block.
    # We'll look for the end of the met_col block: the next line that is at the same indentation as the met_col line and not empty.
    met_col_indent = len(new_tab_content[met_col_line]) - len(new_tab_content[met_col_line].lstrip())
    met_col_end = None
    for i in range(met_col_line + 1, len(new_tab_content)):
        if new_tab_content[i].strip() == '':
            continue
        indent = len(new_tab_content[i]) - len(new_tab_content[i].lstrip())
        if indent <= met_col_indent:
            met_col_end = i
            break
    if met_col_end is None:
        met_col_end = len(new_tab_content)

    # Now, we have the met_col block from met_col_line to met_col_end (exclusive of met_col_end).
    # We'll replace it with a new block that shows metrics and insights.

    # We'll keep the same structure but add an insights section.

    # The original met_col block might look like:
    #     with met_col:
    #         st.subheader("Métricas da Rede")
    #         for label, value in metricas_formatadas:
    #             st.metric(label, value)
    # We'll change it to:
    #     with met_col:
    #         st.subheader("Métricas da Rede")
    #         for label, value in metricas_formatadas:
    #             st.metric(label, value)
    #         st.subheader("Insights de Anomalia")
    #         for insight in insights:
    #             st.info(insight)
    #         if graph_anomalies:
    #             st.subheader("Nós Anômalos Detectados")
    #             anomaly_data = []
    #             for node, score, reason in graph_anomalies:
    #                 label = rede_programas.nodes[node].get('label', node)
    #                 anomaly_data.append({
    #                     "Nó": label,
    #                     "ID": node,
    #                     "Score": score,
    #                     "Motivo": reason
    #                 })
    #             st.dataframe(pd.DataFrame(anomaly_data))

    # We'll build the new met_col block lines.
    new_met_col_block = [
        "    with met_col:\n",
        "        st.subheader(\"Métricas da Rede\")\n",
        "        for label, value in metricas_formatadas:\n",
        "            st.metric(label, value)\n",
        "        st.subheader(\"Insights de Anomalia\")\n",
        "        for insight in insights:\n",
        "            st.info(insight)\n",
        "        if graph_anomalies:\n",
        "            st.subheader(\"Nós Anômalos Detectados\")\n",
        "            anomaly_data = []\n",
        "            for node, score, reason in graph_anomalies:\n",
        "                label = rede_programas.nodes[node].get('label', node)\n",
        "                anomaly_data.append({\n",
        "                    \"Nó\": label,\n",
        "                    \"ID\": node,\n",
        "                    \"Score\": score,\n",
        "                    \"Motivo\": reason\n",
        "                })\n",
        "            st.dataframe(pd.DataFrame(anomaly_data))\n"
    ]

    # Replace the old met_col block with the new one.
    new_tab_content = new_tab_content[:met_col_line] + new_met_col_block + new_tab_content[met_col_end:]

    return new_tab_content

# Now, extract the tab1 and tab2 content, modify them, and put them back.

# Tab1 content: from tab1_line+1 to tab2_line-1
tab1_content = lines[tab1_line+1:tab2_line]
# Tab2 content: from tab2_line+1 to block_end-1
tab2_content = lines[tab2_line+1:block_end]

# Modify tab1 content
new_tab1_content = insert_anomaly_detection(tab1_content, "tab1")
# Modify tab2 content
new_tab2_content = insert_anomaly_detection(tab2_content, "tab2")

# Now, rebuild the else block:
#   lines[0:else_line_idx+1]  # up to and including the else line
#   then the tab1 line
#   then the new tab1 content
#   then the tab2 line
#   then the new tab2 content
#   then lines[block_end:] (the rest of the file)

new_lines = lines[:else_line_idx+1]  # includes the else line
new_lines.append(lines[tab1_line])   # the "with tab1:" line
new_lines.extend(new_tab1_content)
new_lines.append(lines[tab2_line])   # the "with tab2:" line
new_lines.extend(new_tab2_content)
new_lines.extend(lines[block_end:])

# Write the file
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated successfully with anomaly detection in tabs.")