"""
ml/hmm_predictor.py
===================
วางที่  your_project/ml/hmm_predictor.py
ต้องมี  your_project/hmm_output/hmm_model.pkl

Usage ใน routes_doctor.py:
    from ml.hmm_predictor import predictor
    predictor.set_supabase(supabase)
    result = predictor.predict(p_data)
"""
import os, pickle
import numpy as np

_BASE = os.path.dirname(os.path.abspath(__file__))
_PKL  = os.path.join(_BASE, '..', 'hmm_output', 'hmm_model.pkl')

try:
    _b      = pickle.load(open(_PKL, 'rb'))
    _model  = _b['model']
    _s2l    = _b['state_to_label']
    _LABELS = _b['label_names']
    _N      = _b['n_states']
    _ACC    = _b['metrics']['accuracy']
    print(f'[HMM] \u2705 Model loaded  accuracy={_ACC*100:.1f}%')
except Exception as e:
    _model = None
    print(f'[HMM] \u26a0 WARNING: {e}')

_COLORS = ['#10b981', '#f59e0b', '#ef4444']
_SLUGS  = ['normal', 'mci', 'dementia']


def _cutoff(max_score: int, edu: str = '') -> int:
    ms = int(max_score) if max_score else 30
    if ms not in [23, 30]: ms = 30
    if ms == 23: return 14
    e = str(edu or '').strip().lower()
    if 'สูงกว่า' in e or 'bach' in e or 'uni' in e or 'sec' in e or 'มัธยม' in e: return 22
    elif 'ประถม' in e or 'pri' in e: return 17
    return 17


def _parse(val):
    if val is None: return None
    s = str(val).strip()
    if s in ['', '-', 'nan', 'หูตึงประเมินไม่ได้', 'ไม่พูด ไม่รับรู้']: return None
    if '/' in s:
        try: return int(s.split('/')[0])
        except: return None
    try: return int(float(s))
    except: return None


def predict(mmse_scores: list, max_score: int = 30, edu: str = 'ประถม') -> dict:
    if _model is None:
        return {'error': 'Model not loaded', 'result': 'Unknown',
                'risk_score': 0, 'confidence': 0, 'warning': None,
                'n_visits': 0, 'mmse_scores': []}
    c   = _cutoff(max_score, edu)
    obs = np.array([s - c for s in mmse_scores], dtype=float).reshape(-1, 1)
    hs  = _model.predict(obs)
    pb  = _model.predict_proba(obs)
    p_lbl = np.zeros(_N)
    for state, lbl in _s2l.items():
        p_lbl[lbl] += pb[-1][state]
    pred       = _s2l[int(hs[-1])]
    confidence = float(p_lbl[pred])
    risk_score = float(np.dot(p_lbl, [0, 1, 2]))
    warning = state_path = None
    if len(hs) > 1:
        seq        = [_s2l[int(h)] for h in hs]
        state_path = ' \u2192 '.join(_LABELS[s] for s in seq)
        if seq[-1] - seq[-2] >= 2:
            warning = f'\u26a0 Rapid decline: {_LABELS[seq[-2]]} \u2192 {_LABELS[seq[-1]]}'
    return {
        'result':          _LABELS[pred],
        'risk_score':      round(risk_score * 5, 2),
        'confidence':      round(confidence * 100),
        'warning':         warning,
        'n_visits':        len(mmse_scores),
        'mmse_scores':     mmse_scores,
        'predicted_label': _LABELS[pred],
        'label_index':     pred,
        'label_slug':      _SLUGS[pred],
        'label_color':     _COLORS[pred],
        'risk_level':      'HIGH' if pred == 2 else ('MEDIUM' if pred == 1 else 'LOW'),
        'state_probs':     {_LABELS[i]: round(float(p_lbl[i]), 4) for i in range(_N)},
        'state_path':      state_path,
        'model_accuracy':  round(_ACC, 4),
    }


class _Predictor:
    def __init__(self): self._db = None

    @property
    def is_loaded(self): return _model is not None
    @property
    def accuracy(self): return _ACC

    def set_supabase(self, client): self._db = client

    def predict(self, p_data: dict) -> dict:
        edu   = p_data.get('education') or p_data.get('edu') or 'ประถม'
        max_s = int(p_data.get('max_score') or 30)
        if max_s not in [23, 30]: max_s = 30
        scores = []

        hist = p_data.get('mmse_scores') or []
        if isinstance(hist, list) and hist:
            scores = [s for s in hist if s is not None]

        if not scores and self._db and p_data.get('patient_id'):
            try:
                res = (self._db.table('cga_records')
                       .select('mmse_score,max_score,education,assessed_date')
                       .eq('patient_id', p_data['patient_id'])
                       .order('assessed_date').execute())
                for row in (res.data or []):
                    s = _parse(row.get('mmse_score'))
                    if s is not None:
                        scores.append(s)
                        max_s = int(row.get('max_score') or max_s)
                        edu   = str(row.get('education') or edu)
            except Exception as ex:
                print(f'[HMM] DB error: {ex}')

        if not scores:
            s = _parse(p_data.get('mmse_score'))
            if s is not None: scores = [s]

        if not scores:
            return {'error': 'ไม่มีค่า MMSE score', 'result': 'Unknown',
                    'risk_score': 0, 'confidence': 0, 'warning': None,
                    'n_visits': 0, 'mmse_scores': []}

        return predict(scores, max_score=max_s, edu=edu)

    def predict_from_supabase_row(self, row: dict) -> dict:
        s = _parse(row.get('mmse_score'))
        if s is None: return {'error': 'No mmse_score'}
        return predict([s], max_score=int(row.get('max_score') or 30),
                       edu=str(row.get('education') or ''))

    def predict_from_supabase_history(self, rows: list) -> dict:
        scores, max_s, edu = [], 30, ''
        for row in rows:
            s = _parse(row.get('mmse_score'))
            if s is not None:
                scores.append(s)
                max_s = int(row.get('max_score') or max_s)
                edu   = str(row.get('education') or edu)
        if not scores: return {'error': 'No valid MMSE scores'}
        return predict(scores, max_score=max_s, edu=edu)


predictor = _Predictor()


if __name__ == '__main__':
    print("="*55)
    print("  HMM Predictor \u2014 Quick Test")
    print("="*55)
    print(f"  Model loaded : {predictor.is_loaded}")
    print(f"  Accuracy     : {predictor.accuracy*100:.1f}%\n")
    tests = [
        ([27], 30, 'สูงกว่าประถม', 'adj=+5 \u2192 Normal'),
        ([18], 30, 'สูงกว่าประถม', 'adj=-4 \u2192 MCI'),
        ([10], 30, 'ประถม',        'adj=-7 \u2192 Dementia'),
        ([12], 23, 'ไม่ได้เรียน',  'adj=-2 \u2192 MCI (MaxScore=23)'),
        ([17, 10, 5], 30, 'ประถม', 'Trajectory decline'),
    ]
    for sc, ms, edu, note in tests:
        r = predict(sc, max_score=ms, edu=edu)
        ok = '\u2705' if 'error' not in r else '\u274c'
        print(f"  {ok} {note}")
        print(f"     scores={sc}  max={ms}  cutoff={_cutoff(ms,edu)}")
        print(f"     result={r['result']}  risk={r['risk_score']}  conf={r['confidence']}%")
        if r.get('state_path'): print(f"     path: {r['state_path']}")
        print()
