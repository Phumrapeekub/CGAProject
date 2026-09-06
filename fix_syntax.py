import os

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Delete lines 1135 to 1138
# We want to keep lines up to 1134, then add:
#         if q8_val == 0:
#             q8_val = temp_score
# Then the except block

new_lines = lines[:1135]
new_lines.append('        if q8_val == 0:\n')
new_lines.append('            q8_val = temp_score\n')
new_lines.extend(lines[1139:])

with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
    f.writelines(new_lines)
