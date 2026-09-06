import os
import re

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to un-indent the fallback block and change "if q8_val == 0:"
# First find where "if q8_val == 0:" is
pattern = r"(\s*)if q8_val == 0:\s*# 2\. Fallback:[\s\S]*?q8_val = temp_score"
match = re.search(pattern, content)
if match:
    indent = match.group(1)
    old_block = match.group(0)
    
    # We want to remove "if q8_val == 0:" and just run the code, then assign if q8_val == 0
    # Let's extract the inside of the if block
    inside_pattern = r"if q8_val == 0:\n[\s\S]*?cur\.execute\(([\s\S]*?q8_val = temp_score)"
    inside_match = re.search(inside_pattern, old_block)
    
    if inside_match:
        # Strip one level of indentation (4 spaces) from the inside block
        lines = old_block.split('\n')
        new_lines = []
        for line in lines[1:]: # skip "if q8_val == 0:"
            if line.startswith(indent + "    "):
                new_lines.append(line.replace(indent + "    ", indent, 1))
            else:
                new_lines.append(line)
        
        # Replace the last line "q8_val = temp_score" with conditional
        for i in reversed(range(len(new_lines))):
            if "q8_val = temp_score" in new_lines[i]:
                new_lines[i] = indent + "if q8_val == 0:\n" + indent + "    q8_val = temp_score"
                break
                
        new_block = "\n".join(new_lines)
        content = content.replace(old_block, new_block)
        with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        print("SUCCESS")
    else:
        print("FAILED inside match")
else:
    print("FAILED pattern match")
