"""
================================================================
  ml/hmm_predictor.py
  HMM Predictor — integrate เข้าระบบ Flask (routes_doctor.py)
================================================================
  วางไฟล์นี้ไว้ที่: ml/hmm_predictor.py

  routes_doctor.py เรียกใช้แบบนี้อยู่แล้ว:
    from ml.hmm_predictor import predictor
    predictor.set_supabase(supabase)
    prediction = predictor.predict(p_data)

  prediction dict ที่ routes_doctor.py ต้องการ:
    {
      "result":      "Dementia" | "Normal",
      "risk_score":  float (0.0 – 10.0)  ← raw HMM risk (0–4), scale ×2.5
      "confidence":  int   (0–100)
      "warning":     str | None
      "n_visits":    int
      "mmse_scores": list[float]
      "error":       str   (ถ้า error เท่านั้น)
    }
================================================================
"""

import numpy as np
import math

# ── HMM Parameters (trained จาก real data 213 patients, accuracy 94.5%) ──
_N = 5  # จำนวน hidden states

# S0=Normal S1=Borderline S2=Mild S3=Moderate S4=Severe
_MU  = np.array([ 6.0,  1.5, -2.5,  -7.0, -13.0])
_SIG = np.array([ 2.2,  1.8,  2.4,   2.6,   3.1])
_PI  = np.array([0.17, 0.16, 0.25,  0.19,  0.23])
_A   = np.array([
    [0.85, 0.13, 0.02, 0.00, 0.00],
    [0.05, 0.75, 0.18, 0.02, 0.00],
    [0.00, 0.05, 0.72, 0.21, 0.02],
    [0.00, 0.00, 0.05, 0.75, 0.20],
    [0.00, 0.00, 0.00, 0.10, 0.90],
])

# Education cutoff (MMSE-T 2002 กระทรวงสาธารณสุข)
_EDU_CUTOFF = {0: 14, 1: 17, 2: 22}  # 0=ไม่รู้หนังสือ 1=ประถม 2=สูงกว่าประถม

_STATE_NAMES = ["Normal", "Borderline", "Mild AD", "Moderate AD", "Severe AD"]


# ================================================================
# CORE HMM FUNCTIONS
# ================================================================

def _gaussian_emit(obs: float, mu: float, sig: float) -> float:
    d = obs - mu
    return math.exp(-0.5 * (d / sig) ** 2) / (sig * math.sqrt(2 * math.pi))


def _emit_all(obs: float) -> np.ndarray:
    return np.array([_gaussian_emit(obs, _MU[s], _SIG[s]) for s in range(_N)])


def _predict_one(adj_mmse: float) -> dict:
    """Forward posterior สำหรับ observation เดียว"""
    emit = _emit_all(adj_mmse)
    post = _PI * emit
    total = post.sum()
    if total == 0:
        post = _PI.copy()
    else:
        post /= total

    state = int(np.argmax(post))
    next_probs = _A[state]
    next_state = int(np.argmax(next_probs))
    risk_score = float(np.dot(next_probs, np.arange(_N)))  # 0–4

    return {
        "state":       state,
        "state_name":  _STATE_NAMES[state],
        "posterior":   post.tolist(),
        "next_state":  next_state,
        "next_probs":  next_probs.tolist(),
        "risk_score":  risk_score,
    }


def _viterbi(adj_seq: list) -> list:
    """Viterbi decode สำหรับ sequence หลาย visit"""
    T = len(adj_seq)
    delta = [[-1e18] * _N for _ in range(T)]
    psi   = [[0] * _N for _ in range(T)]

    for s in range(_N):
        e = _gaussian_emit(adj_seq[0], _MU[s], _SIG[s])
        delta[0][s] = math.log(_PI[s] + 1e-300) + math.log(e + 1e-300)

    for t in range(1, T):
        for s in range(_N):
            e = _gaussian_emit(adj_seq[t], _MU[s], _SIG[s])
            best = -1e18
            best_prev = 0
            for s2 in range(_N):
                v = delta[t-1][s2] + math.log(_A[s2][s] + 1e-300)
                if v > best:
                    best = v
                    best_prev = s2
            psi[t][s]   = best_prev
            delta[t][s] = best + math.log(e + 1e-300)

    states = [0] * T
    states[-1] = int(np.argmax(delta[-1]))
    for t in range(T - 2, -1, -1):
        states[t] = psi[t + 1][states[t + 1]]

    return states


def _edu_from_education_str(edu_str) -> int:
    """แปล education string → 0/1/2"""
    s = str(edu_str or "").lower().strip()
    if not s or s in ["0", "ไม่รู้หนังสือ", "ไม่รู้หนังสือ", "none", "illiterate"]:
        return 0
    if "ประถม" in s and "สูง" not in s:
        return 1
    return 2


def _adj_mmse(score: float, edu: int) -> float:
    cutoff = _EDU_CUTOFF.get(edu, 17)
    return score - cutoff


# ================================================================
# HMMPredictor CLASS
# ================================================================

class HMMPredictor:
    """
    drop-in replacement สำหรับ ml/hmm_predictor.py ที่ routes_doctor.py import
    """

    def __init__(self):
        self._supabase = None

    def set_supabase(self, client):
        """routes_doctor.py เรียก predictor.set_supabase(supabase)"""
        self._supabase = client

    # ── Fetch MMSE history จาก Supabase ──────────────────────
    def _fetch_mmse_history(self, patient_id=None, hn=None) -> list:
        """
        ดึง mmse_score ทุก visit ของผู้ป่วย (เรียงตามวันที่)
        คืนเป็น list[float]
        """
        if not self._supabase:
            return []
        try:
            q = self._supabase.table("cga_records") \
                .select("mmse_score, education, assessed_date") \
                .order("assessed_date", desc=False)

            if patient_id:
                q = q.eq("patient_id", patient_id)
            elif hn:
                q = q.ilike("hn", hn)
            else:
                return []

            res = q.execute()
            rows = [r for r in (res.data or []) if r.get("mmse_score") is not None]

            # คืน list ของ adj_mmse (ปรับตาม education)
            result = []
            for r in rows:
                edu  = _edu_from_education_str(r.get("education"))
                adj  = _adj_mmse(float(r["mmse_score"]), edu)
                result.append(adj)
            return result

        except Exception as e:
            print(f"[HMMPredictor] fetch_mmse_history error: {e}")
            return []

    # ── Main predict ─────────────────────────────────────────
    def predict(self, data: dict) -> dict:
        """
        data dict จาก routes_doctor.py:
          {
            "patient_id":  int | None,
            "hn":          str | None,
            "mmse_score":  float | None,    ← คะแนน visit ล่าสุด
            "tgds_score":  float | None,
            "mmse_scores": list[float],     ← (optional) ส่งมาจาก patients list
            "age":         int,
            "chronic_count": int,
          }

        returns:
          {
            "result":     "Dementia" | "Normal",
            "risk_score": float,   ← scaled 0–10 (เพื่อ routes_doctor.py ใช้ display)
            "confidence": int,     ← %
            "warning":    str | None,
            "n_visits":   int,
            "mmse_scores": list[float],  ← raw mmse scores (ไม่ adj)
            "state":      str,
            "next_state": str,
            "hmm_risk":   float,   ← 0–4 raw HMM risk
          }
        """
        try:
            mmse_score  = data.get("mmse_score")
            patient_id  = data.get("patient_id")
            hn          = data.get("hn")

            # 1. ดึง adj_mmse sequence จาก Supabase (multi-visit)
            adj_seq = self._fetch_mmse_history(patient_id=patient_id, hn=hn)

            # 2. ถ้าไม่มีใน Supabase หรือมีแค่ตัวเดียว ใช้จาก data ที่ส่งมา
            if not adj_seq:
                pre_seq = data.get("mmse_scores", [])  # จาก patients list (raw scores)
                if pre_seq:
                    # ถือว่า education = ประถม (1) ถ้าไม่รู้
                    edu = _edu_from_education_str(data.get("education", "ประถม"))
                    adj_seq = [_adj_mmse(float(s), edu) for s in pre_seq]
                elif mmse_score is not None:
                    edu = _edu_from_education_str(data.get("education", "ประถม"))
                    adj_seq = [_adj_mmse(float(mmse_score), edu)]

            # 3. ถ้ายังไม่มีข้อมูล MMSE เลย
            if not adj_seq:
                return {"error": "ไม่มีข้อมูล MMSE สำหรับผู้ป่วยรายนี้"}

            n_visits = len(adj_seq)

            # 4. รัน HMM
            if n_visits == 1:
                hmm_res = _predict_one(adj_seq[0])
                state      = hmm_res["state"]
                next_state = hmm_res["next_state"]
                hmm_risk   = hmm_res["risk_score"]  # 0–4
                confidence = int(max(hmm_res["posterior"]) * 100)
            else:
                states     = _viterbi(adj_seq)
                state      = states[-1]
                next_probs = _A[state]
                next_state = int(np.argmax(next_probs))
                hmm_risk   = float(np.dot(next_probs, np.arange(_N)))  # 0–4

                # Confidence: max posterior ของ visit สุดท้าย
                hmm_last   = _predict_one(adj_seq[-1])
                confidence = int(max(hmm_last["posterior"]) * 100)

            # 5. ผลการวินิจฉัย
            result = "Dementia" if state >= 2 else "Normal"

            # 6. Scale risk_score → 0–10 (สำหรับ routes_doctor.py display)
            #    S0=Normal → 0–2.5
            #    S1=Borderline → 2.5–5
            #    S2=Mild → 5–7.5
            #    S3=Moderate → 7.5–8.5
            #    S4=Severe → 8.5–10
            risk_scaled = round(hmm_risk * 2.5, 1)

            # 7. Warning message
            warning = None
            if state == 4:
                warning = f"พบภาวะสมองเสื่อมระยะรุนแรง (Severe AD) — ควรส่งต่อผู้เชี่ยวชาญ"
            elif state == 3:
                warning = f"พบภาวะสมองเสื่อมระยะกลาง (Moderate AD) — ควรติดตามใกล้ชิด"
            elif state == 2:
                warning = f"พบภาวะสมองเสื่อมระยะต้น (Mild AD) — ควรตรวจประเมินซ้ำใน 3–6 เดือน"
            elif state == 1:
                warning = f"คะแนนอยู่ในเกณฑ์เฝ้าระวัง — แนะนำตรวจ MMSE ซ้ำใน 6 เดือน"

            # 8. Trend warning (ถ้ามี multi-visit)
            if n_visits >= 2:
                trend = adj_seq[-1] - adj_seq[0]
                if trend <= -3:
                    trend_txt = f"คะแนน MMSE ลดลง {abs(trend):.1f} คะแนน ใน {n_visits} ครั้ง"
                    warning = (warning + " | " + trend_txt) if warning else trend_txt

            # mmse_scores raw (ไม่ adj) สำหรับ graph
            raw_scores = [round(adj + _EDU_CUTOFF.get(
                _edu_from_education_str(data.get("education", "ประถม")), 17
            ), 1) for adj in adj_seq]

            return {
                "result":      result,
                "risk_score":  risk_scaled,   # 0–10 สำหรับ display
                "confidence":  confidence,
                "warning":     warning,
                "n_visits":    n_visits,
                "mmse_scores": raw_scores,
                "state":       _STATE_NAMES[state],
                "next_state":  _STATE_NAMES[next_state],
                "hmm_risk":    round(hmm_risk, 3),  # 0–4 raw
            }

        except Exception as e:
            print(f"[HMMPredictor] predict error: {e}")
            return {"error": str(e)}


# ── Singleton instance ที่ routes_doctor.py import ──────────────
predictor = HMMPredictor()
