import os
import re

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                    elif inst == "depression8q":
                        # We don't have a detailed partial for 8Q, but could add if needed
                        pass
            except Exception as e:
                print(f"DEBUG: Error fetching detailed answers: {e}")"""

new_logic = """                    elif inst == "depression8q":
                        # We don't have a detailed partial for 8Q, but could add if needed
                        pass
                    elif inst == "basic":
                        if isinstance(val, str):
                            if val.startswith("live:"): 
                                l = val.split(":", 1)[1]
                                cga_general["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                            elif val.startswith("height:"): cga_general["height"] = val.split(":", 1)[1]
                            elif val.startswith("waist:"): cga_general["waist"] = val.split(":", 1)[1]
            except Exception as e:
                print(f"DEBUG: Error fetching detailed answers: {e}")"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
