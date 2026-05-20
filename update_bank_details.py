import sys

filename = '/home/cdncode/Projects/livecodetech/livecode-backend/app/core/document_generators.py'
with open(filename, 'r') as f:
    lines = f.readlines()

start_idx = 364 # line 365
end_idx = 424 # line 424

# Insert if statement at start_idx
new_lines = lines[:start_idx]
new_lines.append('    if payment_method_val == "Bank Transfer / Offline":\n')

# Indent lines from start_idx to end_idx
for i in range(start_idx, end_idx):
    if lines[i].strip() == '':
        new_lines.append('\n')
    else:
        new_lines.append('    ' + lines[i])

new_lines.extend(lines[end_idx:])

with open(filename, 'w') as f:
    f.writelines(new_lines)

print("Update complete")
