import os
import numpy as np
import joblib
import sklearn # Ensure sklearn is available

class HmmPredictor:
    def __init__(self):
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.normpath(os.path.join(self.base_path, 'models', 'hmm_best_model.joblib'))
        self.scaler_path = os.path.normpath(os.path.join(self.base_path, 'models', 'hmm_scaler.joblib'))
        
        self.model = None
        self.scaler = None
        print(f"DEBUG: AI Path initialized. Model: {self.model_path}")

    def _load_model(self):
        if self.model is not None:
            return True
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                print(f"✅ HMM Model and Scaler loaded successfully from {self.base_path}")
                return True
            else:
                msg = f"❌ HMM Model or Scaler file not found. Checked: {self.model_path}"
                print(msg)
                return False
        except Exception as e:
            print(f"❌ Error loading HMM model: {e}")
            return False

    def predict(self, patient_data):
        if not self._load_model():
            return {"error": "Model not loaded"}

        try:
            # Preparing 9 features (Example mapping, should match training order)
            # 1. Age
            # 2. MMSE Score
            # 3. TGDS Score
            # 4. Incontinence (Binary)
            # 5. Sleep Problem (Binary)
            # 6. Hearing Problem (Binary)
            # 7. Vision Problem (Binary)
            # 8. Suicide Risk (Binary)
            # 9. BMI or Chronic Count (Using 0 as placeholder if missing)
            
            def to_bin(val):
                v = str(val or "").lower()
                if v in ['yes', 'มี', 'true', '1', 'abnormal', 'ผิดปกติ']: return 1
                return 0

            features = [
                float(patient_data.get('age') or 60),
                float(patient_data.get('mmse_score') or 0),
                float(patient_data.get('tgds_score') or 0),
                to_bin(patient_data.get('incontinence')),
                to_bin(patient_data.get('sleep_problem')),
                to_bin(patient_data.get('hearing_left')),
                to_bin(patient_data.get('vision_left')),
                to_bin(patient_data.get('suicide_risk')),
                float(patient_data.get('chronic_count') or 0)
            ]

            # Scale and Predict
            features_scaled = self.scaler.transform([features])
            prediction = self.model.predict(features_scaled)
            
            # Probability (If model supports it)
            prob = 0
            if hasattr(self.model, "predict_proba"):
                prob = self.model.predict_proba(features_scaled)[0][prediction[0]]
            
            classes = ['Non-Dementia', 'Dementia']
            result = classes[prediction[0]]
            
            return {
                "result": result,
                "label": "ปกติ" if result == 'Non-Dementia' else "เสี่ยงสมองเสื่อม",
                "risk_score": float(prob * 100) if prob > 0 else (90.0 if result == 'Dementia' else 10.0),
                "confidence": round(float(prob * 100), 2) if prob > 0 else None
            }
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            return {"error": str(e)}

# Singleton instance
predictor = HmmPredictor()
