import os

with open('doctor/routes_doctor.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = """                    elif inst == "8q":
                        q8_details[f"q8_{q_no}"] = val
                        # Capture sub-question/remarks for Q3
                        if q_no == 3:
                            remarks = row.get("remarks")
                            if remarks:
                                q8_details["q3_sub"] = 1 if "cannot_control" in str(remarks).lower() else 0
                        # Try to find q3_sub if stored as a separate question_no or field
                        if row.get("answer_text") == "cannot_control":
                            q8_details["q3_sub"] = 1
                        elif row.get("answer_text") == "can_control":
                            q8_details["q3_sub"] = 0

                # B) Formal scores from assessment_scores table"""

new_logic = """                    elif inst == "8q":
                        q8_details[f"q8_{q_no}"] = val
                        # Capture sub-question/remarks for Q3
                        if q_no == 3:
                            remarks = row.get("remarks")
                            if remarks:
                                q8_details["q3_sub"] = 1 if "cannot_control" in str(remarks).lower() else 0
                        # Try to find q3_sub if stored as a separate question_no or field
                        if row.get("answer_text") == "cannot_control":
                            q8_details["q3_sub"] = 1
                        elif row.get("answer_text") == "can_control":
                            q8_details["q3_sub"] = 0
                    elif inst == "basic":
                        if val and isinstance(val, str):
                            if val.startswith("live:"):
                                l = val.split(":", 1)[1]
                                basic_extras["living_status"] = "alone" if l == "alone" else "family" if l == "caregiver" else l
                            elif val.startswith("height:"):
                                basic_extras["height"] = val.split(":", 1)[1]
                            elif val.startswith("waist:"):
                                basic_extras["waist"] = val.split(":", 1)[1]
            except Exception as e:
                print(f"DEBUG: Error processing local DB answers: {e}")

                # B) Formal scores from assessment_scores table"""

content = content.replace(old_logic, new_logic)

with open('doctor/routes_doctor.py', 'w', encoding='utf-8', newline='') as f:
    f.write(content)
