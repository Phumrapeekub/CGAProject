"""
================================================================================
HMM PREDICTOR (SMART VERSION) - Supporting 3 or 9 features
================================================================================
"""

import os
import numpy as np
import joblib
import json
import traceback
from typing import Optional, Dict, List, Any


class HmmPredictor:
    def __init__(self, supabase_client=None):
        self.supabase = supabase_client
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.model_path = os.path.join(self.base_path, 'models', 'hmm_best_model.joblib')
        self.scaler_path = os.path.join(self.base_path, 'models', 'hmm_scaler.joblib')
        
        self.model = None
        self.scaler = None
        self.n_features_expected = 3
        self._load_model()

    def set_supabase(self, supabase_client):
        self.supabase = supabase_client

    def _load_model(self) -> bool:
        if self.model is not None:
            return True
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                # Detect expected features from scaler
                self.n_features_expected = getattr(self.scaler, 'n_features_in_', 3)
                print(f"✅ HMM Model loaded (Expected features: {self.n_features_expected})")
                return True
            return False
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            return False

    def _compute_features_v9(self, mmse_scores: List[int]) -> List[float]:
        """Calculates 9 features from MMSE sequence for the V9 model."""
        scores = np.array(mmse_scores, dtype=float)
        n = len(scores)
        slope = 0.0
        if n > 1:
            try:
                slope = float(np.polyfit(np.arange(n), scores, 1)[0])
            except: pass
        
        return [
            float(np.mean(scores)), 
            float(np.std(scores)) if n > 1 else 0.0,
            float(np.min(scores)), float(np.max(scores)),
            slope, float(scores[0]), float(scores[-1]),
            float(scores[-1] - scores[0]), float(n)
        ]

    def get_patient_mmse_history(self, patient_id: int = None, hn: str = None) -> Dict[str, Any]:
        if not self.supabase:
            return {"error": "Supabase not connected", "mmse_scores": [], "n_visits": 0}
        try:
            query = self.supabase.table('cga_records').select('patient_id, hn, mmse_score, tgds_score, assessed_date, age')
            if patient_id: query = query.eq('patient_id', patient_id)
            elif hn: query = query.eq('hn', hn)
            else: return {"error": "Missing ID", "mmse_scores": [], "n_visits": 0}
            
            response = query.order('assessed_date', desc=False).execute()
            valid_records = [r for r in (response.data or []) if r.get('mmse_score') is not None]
            
            if not valid_records:
                return {"error": "No MMSE data", "mmse_scores": [], "n_visits": 0}
            
            return {
                'patient_id': valid_records[0].get('patient_id'),
                'hn': valid_records[0].get('hn'),
                'mmse_scores': [r['mmse_score'] for r in valid_records],
                'tgds_scores': [r.get('tgds_score') for r in valid_records],
                'n_visits': len(valid_records),
                'age': valid_records[-1].get('age'),
                'last_tgds': valid_records[-1].get('tgds_score')
            }
        except Exception as e:
            print(f"❌ DB Error: {e}")
            return {"error": str(e), "mmse_scores": [], "n_visits": 0}

    def predict(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        if not self.model and not self._load_model():
            return {"error": "Model not loaded"}

        try:
            mmse_scores = []
            history = {}
            
            # 1. Get History if ID is provided
            if 'patient_id' in patient_data or 'hn' in patient_data:
                history = self.get_patient_mmse_history(patient_id=patient_data.get('patient_id'), hn=patient_data.get('hn'))
                mmse_scores = history.get('mmse_scores', [])
            
            # 2. Fallback to direct scores
            if not mmse_scores:
                mmse_scores = patient_data.get('mmse_scores', [])
                if isinstance(mmse_scores, str): mmse_scores = json.loads(mmse_scores)
                if not mmse_scores and 'mmse_score' in patient_data:
                    mmse_scores = [patient_data['mmse_score']]

            if not mmse_scores:
                return {"error": "ข้อมูลไม่ครบถ้วน", "label": "รอการวิเคราะห์", "risk_score": 0}

            # 3. Prepare Feature Matrix X based on Model Type
            if self.n_features_expected == 9:
                # Sequence statistics model
                features = self._compute_features_v9(mmse_scores)
                X = [features]
            else:
                # Point-in-time model [age, mmse, chronic]
                age = float(patient_data.get('age') or history.get('age') or 60)
                chronic = float(patient_data.get('chronic_count') or 0)
                X = [[age, float(s), chronic] for s in mmse_scores]

            # 4. Predict
            X_scaled = self.scaler.transform(X)
            probs_seq = self.model.predict_proba(X_scaled)
            probs = probs_seq[-1] # Take latest state probability
            
            prob_dementia = probs[1]
            prediction = 1 if prob_dementia >= 0.5 else 0
            
            return {
                "result": "Dementia" if prediction == 1 else "Non-Dementia",
                "label": "เสี่ยงสมองเสื่อม" if prediction == 1 else "ปกติ",
                "risk_score": round(prob_dementia * 10, 1),
                "confidence": round(float(probs[prediction] * 100), 2),
                "mmse_scores": mmse_scores,
                "n_visits": len(mmse_scores),
                "tgds_score": patient_data.get('tgds_score') or history.get('last_tgds'),
                "warning": "⚠️ ทำนายจากการตรวจครั้งเดียว" if len(mmse_scores) == 1 else None
            }
        except Exception as e:
            traceback.print_exc()
            return {"error": str(e)}

    def predict_from_cga_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return self.predict(record)

predictor = HmmPredictor()
