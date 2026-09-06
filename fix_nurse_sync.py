import os
import re

with open('nurse/routes_nurse.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """            "smoke": {'no':'','quit':'','yes':''}.get(data_map['smoke'], ''),
            "alcohol": {'none':'','no':'','social':'','daily':''}.get(data_map['alcohol'], ''),
            "height": data_map.get('height'),
            "waist": data_map.get('waist'),
            "living_status": data_map.get('live')
        }"""

new_block = """            "smoke": {'no':'','quit':'','yes':''}.get(data_map['smoke'], ''),
            "alcohol": {'none':'','no':'','social':'','daily':''}.get(data_map['alcohol'], '')
        }"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('nurse/routes_nurse.py', 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print("SUCCESS: Removed invalid columns from _sync_to_cga_records")
else:
    print("FAILED: Could not find target block")
