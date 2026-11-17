#!/usr/bin/env python3
import sys

file_path = "/home/programador/Documentos/grafo/app.py"

with open(file_path, "r") as f:
    lines = f.readlines()

# We'll find the line index where the imports end.
# We know the imports are at the top, and they end before the function definitions.
# We'll look for the first line that is not an import and not a blank line or comment.
# But note: there might be comments and blank lines between imports and the function definitions.
# We'll instead look for the line that starts with 'def ' or 'st.set_page_config' (which is after the imports).
# However, note that the current file has the st.set_page_config and st.title after the imports.

# Let's find the line index of the first non-import, non-blank line that is not a comment.
# We'll consider a line as an import if it starts with 'import' or 'from'.
# We'll also consider a line as blank if it's empty or only whitespace.
# We'll consider a line as a comment if it starts with '#'.

# We'll iterate until we find a line that is not an import, not blank, and not a comment.
import_end_idx = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == '':
        import_end_idx = i + 1
        continue
    if stripped.startswith('#'):
        import_end_idx = i + 1
        continue
    if stripped.startswith('import ') or stripped.startswith('from '):
        import_end_idx = i + 1
        continue
    # If we get here, this line is not an import, not blank, not a comment.
    break

# Now, import_end_idx is the index of the first line that is not an import (or the end of the file if all lines are imports).
# We want to insert our new imports after the last import line (which is at index import_end_idx-1).
# But note: we might have blank lines or comments after the imports and before the function definitions.
# We want to insert after the last import, but before any code (like st.set_page_config).
# We'll insert at import_end_idx (which is the line after the last import).

# The imports we want to add:
new_imports = [
    'import io\n',
    'import json\n',
    'import matplotlib.pyplot as plt\n',
    'import anomaly_detection\n',
    '\n'  # an empty line after the imports for readability
]

# We'll check if any of these imports are already present to avoid duplicates.
# We'll create a set of the import statements we are going to add (without the newline).
new_imports_set = set([line.strip() for line in new_imports if line.strip() != ''])

# We'll now build the new lines:
#   lines[0:import_end_idx]  (the existing imports and any blank/comments after them)
#   then the new_imports (but we'll skip any that are already present)
#   then lines[import_end_idx:] (the rest of the file)

# We'll check for each new import if it's already present in the existing lines.
# We'll do a simple check: if the stripped line is in the existing lines (stripped).
# Note: this might not catch all duplicates (e.g., if the import is split) but it's good enough for now.
already_present = set()
for line in lines:
    stripped = line.strip()
    if stripped in new_imports_set:
        already_present.add(stripped)

# Now, we'll filter the new_imports to only those that are not already present.
new_imports_to_add = [line for line in new_imports if line.strip() not in already_present]

# Build the new lines.
new_lines = lines[0:import_end_idx] + new_imports_to_add + lines[import_end_idx:]

# Write the file.
with open(file_path, "w") as f:
    f.writelines(new_lines)

print("File updated with fixed imports.")