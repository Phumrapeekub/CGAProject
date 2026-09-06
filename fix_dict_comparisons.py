import os
import re

with open('templates/doctor/medical_patients_detail.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove my previous messy hacks
content = re.sub(r'\{% set _m = .*? %\}', '', content)
content = re.sub(r'\{% set _t = .*? %\}', '', content)
content = re.sub(r'\{% set _q = .*? %\}', '', content)

# I will use mmse_val, tgds_val, twoq_val for numbers.
# Replace mmse < 24 with mmse_val < 24
content = re.sub(r'mmse\s*<\s*24', 'mmse_val < 24', content)
# Fix the mmse display
content = re.sub(r'\{\{ \(mmse\.score_total if mmse is mapping else mmse\) \}\}', '{{ mmse_val }}', content)

# Replace tgds >= 6 with tgds_val >= 6
content = re.sub(r'tgds\s*>=\s*6', 'tgds_val >= 6', content)
content = re.sub(r'\{\{ \(tgds\.total_score if tgds is mapping else tgds\) \}\} / 15', '{{ tgds_val }} / 15', content)
content = re.sub(r'\{\{ \(tgds\.total_score if tgds is mapping else tgds\) \}\}/15', '{{ tgds_val }}/15', content)

# Replace twoq > 0 with twoq_val > 0
content = re.sub(r'twoq\s*>\s*0', 'twoq_val > 0', content)
# Fix the twoq display
content = re.sub(r'\{\{ twoq \}\}/2', '{{ twoq_val }}/2', content)

# Now inject the definitions of mmse_val, tgds_val, twoq_val right after the initial set block
top_block = """{% set mmse = (scores.mmse if scores is defined and scores and scores.mmse is defined else (scores.get('mmse') if scores is mapping else 0)) %}
{% set tgds = (scores.tgds if scores is defined and scores and scores.tgds is defined else (scores.get('tgds') if scores is mapping else 0)) %}
{% set sra  = (scores.sra  if scores is defined and scores and scores.sra  is defined else (scores.get('sra')  if scores is mapping else 0)) %}
{% set twoq = (scores.twoq if scores is defined and scores and scores.twoq is defined else (scores.get('twoq') if scores is mapping else 0)) %}"""

new_block = top_block + """
{% set mmse_val = (mmse.score_total|int if mmse is mapping else mmse|int) %}
{% set tgds_val = (tgds.total_score|int if tgds is mapping else tgds|int) %}
{% set twoq_val = (twoq.yes_count|int if twoq is mapping else (twoq.score_total|int if twoq is mapping and 'score_total' in twoq else twoq|int)) %}"""

content = content.replace(top_block, new_block)

with open('templates/doctor/medical_patients_detail.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
