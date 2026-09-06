import os
import re

with open('templates/nurse/summary.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Add TGDS breakdown
tgds_breakdown = """
              <div class="space-y-1 p-3 bg-slate-50 rounded-xl mb-4 border border-slate-100 max-h-32 overflow-y-auto">
                  {% for i in range(1, 16) %}
                  {% set ans = tgds_details.get(i|string, '-') %}
                  <div class="flex justify-between items-center text-xs">
                      <span class="text-slate-500">ข้อ {{ i }}</span>
                      <span class="text-slate-800 font-bold {{ 'text-red-600' if ans == 'ใช่' else '' }}">{{ ans }}</span>
                  </div>
                  {% endfor %}
              </div>
"""

# Replace in TGDS
old_tgds = """<div class="p-3 bg-slate-50 rounded-xl mb-4 flex justify-between items-center border border-slate-100">
                  <span class="text-xs text-slate-500">ผลประเมิน 2Q:</span>      
                  <span class="text-sm font-bold {{ 'text-red-600' if dep_2q != 'ไม่มี, ไม่มี' else 'text-slate-800' }}">{{ dep_2q|default('ปกติ') }}</span>
              </div>"""

new_tgds = old_tgds + tgds_breakdown
content = content.replace(old_tgds, new_tgds)


# Add 8Q breakdown
q8_breakdown = """
              <div class="space-y-1 p-3 bg-slate-50 rounded-xl mb-4 border border-slate-100 max-h-32 overflow-y-auto">
                  {% for i in range(1, 9) %}
                  {% set ans = q8_details.get(i|string, '-') if q8_details else '-' %}
                  <div class="flex justify-between items-center text-xs">
                      <span class="text-slate-500">ข้อ {{ i }}</span>
                      <span class="text-slate-800 font-bold {{ 'text-red-600' if ans == 'มี' else '' }}">{{ ans }}</span>
                  </div>
                  {% endfor %}
              </div>
"""

old_8q = """<span class="text-5xl font-black {{ 'text-green-600' if q8_score == 0 else ('text-orange-600' if q8_score < 9 else 'text-red-600') }}">{{ q8_score|default(0) }}</span>
                  <span class="text-lg text-slate-400 font-medium">คะแนน</span>
              </div>"""

new_8q = old_8q + q8_breakdown
content = content.replace(old_8q, new_8q)

with open('templates/nurse/summary.html', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
