import os
import re

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Initialize q8_details
content = content.replace("q8_val = 0\n    try:", "q8_val = 0\n    q8_details = {}\n    try:")

# 2. Populate q8_details from ans8q
old_loop = """            for r in ans8q:
                if r['instrument'] == 'depression8Q':
                    try:
                        q_idx = int(r['question_no'])
                        if r['answer_text'] == 'yes':
                            temp_score += q8_weights.get(q_idx, 0)
                            if q_idx == 3: q3_v = 'yes'
                    except: pass
                elif r['instrument'] == 'depression8Q_sub':
                    q3_s = r['answer_text']"""

new_loop = """            for r in ans8q:
                if r['instrument'] == 'depression8Q':
                    try:
                        q_idx = int(r['question_no'])
                        q8_details[str(q_idx)] = 'มี' if r['answer_text'] == 'yes' else 'ไม่มี'
                        if r['answer_text'] == 'yes':
                            temp_score += q8_weights.get(q_idx, 0)
                            if q_idx == 3: q3_v = 'yes'
                    except: pass
                elif r['instrument'] == 'depression8Q_sub':
                    q3_s = r['answer_text']"""
                    
content = content.replace(old_loop, new_loop)

# 3. Pass q8_details to render_template
old_render = "q8_score=q8_val, full_info=full_info, ai_result=ai_result)"
new_render = "q8_score=q8_val, q8_details=q8_details, full_info=full_info, ai_result=ai_result)"
content = content.replace(old_render, new_render)

with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
