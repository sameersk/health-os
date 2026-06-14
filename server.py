#!/usr/bin/env python3
"""
Health OS — Python Garmin proxy server
Replaces garmin-direct-proxy.mjs

Setup:
    pip install garminconnect
    # Create .env.local with:
    #   GARMIN_EMAIL=your@email.com
    #   GARMIN_PASSWORD=yourpassword

Run:  python server.py
Open: http://127.0.0.1:8787
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
SYNC_LOCK = threading.Lock()   # one Garmin sync at a time (client is not thread-safe)
from pathlib import Path
from urllib.parse import urlparse

# ─── Load .env ────────────────────────────────────────────────────────────────
def load_env():
    for fname in ['.env.local', '.env']:
        try:
            for line in Path(fname).read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))
        except FileNotFoundError:
            pass

load_env()

EMAIL    = os.environ.get('GARMIN_EMAIL', '')
PASSWORD = os.environ.get('GARMIN_PASSWORD', '')
PORT     = int(os.environ.get('PORT', 8787))
SESSION_FILE = Path('.garmin_session.pkl')  # pickle-cached session
CACHE_FILE   = Path('garmin_cache.json')    # last successful Garmin sync result

# ─── Garmin client (singleton, session-cached) ────────────────────────────────
_client = None

def get_client():
    global _client
    if _client is not None:
        return _client
    import pickle
    from garminconnect import Garmin

    # Try restoring a pickled session (avoids re-login on every server restart)
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, 'rb') as f:
                api = pickle.load(f)
            # Quick health-check to confirm session is still valid
            api.get_full_name()
            print("  [auth] Reused cached session")
            _client = api
            return _client
        except Exception:
            print("  [auth] Cached session expired — logging in fresh")
            SESSION_FILE.unlink(missing_ok=True)

    api = Garmin(EMAIL, PASSWORD)
    api.login()
    name = api.get_full_name() or EMAIL
    print(f"  [auth] Logged in as {name}")
    try:
        with open(SESSION_FILE, 'wb') as f:
            pickle.dump(api, f)
    except Exception:
        pass  # caching is best-effort
    _client = api
    return _client

def reset_client():
    """Force a fresh login on next call (e.g. after auth/session error)."""
    global _client
    _client = None
    SESSION_FILE.unlink(missing_ok=True)

# ─── Garmin data cache ────────────────────────────────────────────────────────
def load_cache() -> dict | None:
    """Return cached sync result, or None if missing/corrupted."""
    try:
        data = json.loads(CACHE_FILE.read_text())
        return data
    except Exception:
        return None

def save_cache(data: dict):
    """Persist sync result so restarts don't require a full re-sync."""
    try:
        payload = {**data, '_cached_at': datetime.now(timezone.utc).isoformat()}
        CACHE_FILE.write_text(json.dumps(payload, default=str))
    except Exception as e:
        print(f"  [warn] cache save: {e}")

# ─── Nutrition log (shared between web app and Cowork artifact) ───────────────
FOOD_FILE = Path('nutrition_log.json')

def load_food() -> list:
    try:
        data = json.loads(FOOD_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_food(entries: list):
    try:
        FOOD_FILE.write_text(json.dumps(entries, default=str, indent=1))
    except Exception as e:
        print(f"  [warn] food save: {e}")

def upsert_food(incoming) -> list:
    """Insert or update food entries by id. Returns full log."""
    entries = load_food()
    by_id = {e.get('id'): i for i, e in enumerate(entries) if e.get('id')}
    items = incoming if isinstance(incoming, list) else [incoming]
    for item in items:
        if not isinstance(item, dict) or not item.get('text'):
            continue
        if not item.get('id'):
            item['id'] = f"f{int(time.time()*1000)}_{len(entries)}"
        if not item.get('date'):
            item['date'] = datetime.now().strftime('%Y-%m-%d')
        idx = by_id.get(item['id'])
        if idx is not None:
            entries[idx] = {**entries[idx], **item}   # merge (e.g. add nutrition later)
        else:
            entries.append(item)
            by_id[item['id']] = len(entries) - 1
    save_food(entries)
    return entries

# ─── Date helpers ─────────────────────────────────────────────────────────────
def ds(n: int) -> str:
    """Date string N days ago: ds(0)=today, ds(1)=yesterday."""
    return str(date.today() - timedelta(days=n))

def safe(fn, label='', default=None):
    """Call fn(), log errors, return default on failure."""
    try:
        return fn()
    except Exception as e:
        print(f"  [warn] {label}: {e}")
        return default

# ─── Data normalisation helpers ───────────────────────────────────────────────
def norm_sleep(raw: dict, date_str: str) -> dict | None:
    """
    Normalise a get_sleep_data() response into the compact format
    the Health OS web app expects.
    """
    if not raw:
        return None
    # garminconnect wraps the summary in dailySleepDTO
    dto = raw.get('dailySleepDTO') or raw
    # Use (x or 0) — Garmin sometimes returns None explicitly, not a missing key
    deep_s  = dto.get('deepSleepSeconds')  or 0
    light_s = dto.get('lightSleepSeconds') or 0
    rem_s   = dto.get('remSleepSeconds')   or 0
    seconds = (dto.get('sleepTimeSeconds')
               or dto.get('totalSleepSeconds')
               or (deep_s + light_s + rem_s))
    if not seconds or seconds < 3600:
        return None
    hours = round(seconds / 3600, 2)

    # Sleep score — lives in different places across firmware versions
    score = None
    scores = dto.get('sleepScores')
    if isinstance(scores, dict):
        score = scores.get('overall', {}).get('value') if isinstance(scores.get('overall'), dict) else scores.get('totalDuration', {}).get('value')
    if score is None:
        score = dto.get('sleepScore') or dto.get('sleepScoreDTO', {}).get('value')

    # HRV — avgOvernightHrv lives at the TOP level of the response, not in dailySleepDTO
    hrv = (raw.get('avgOvernightHrv') if isinstance(raw, dict) else None) \
          or dto.get('averageHRV') or dto.get('avgOvernightHrv') \
          or (dto.get('hrvData') or {}).get('nightlyAverageHrv')

    # Stage percentages (already extracted above as deep_s / light_s / rem_s)

    # Convert Unix ms timestamp → ISO string so JS .localeCompare() works in the web app
    raw_ts = dto.get('sleepStartTimestampGMT') or dto.get('sleepStartTimestampLocal')
    if isinstance(raw_ts, (int, float)) and raw_ts > 1e9:
        sleep_start = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    else:
        sleep_start = raw_ts  # already a string or None

    return {
        'date':               date_str,
        'sleep_start':        sleep_start,
        'sleep_hours':        hours,
        'avg_overnight_hrv':  hrv,
        'sleep_score':        score,
        'deep_sleep_percent': round(deep_s / seconds * 100, 1) if seconds else None,
        'rem_sleep_percent':  round(rem_s  / seconds * 100, 1) if seconds else None,
        'light_sleep_percent':round(light_s / seconds * 100, 1) if seconds else None,
        'avg_sleep_stress':   dto.get('avgSleepStress'),
    }

def get_steps(api, start_date: str, end_date: str) -> list:
    """
    Fetch step data — handles API differences across garminconnect versions:
      get_daily_steps(start, end)  — range query (preferred)
      get_steps_data(start, end)   — some versions; others only take 1 arg
    """
    # Try range-based method first
    for method_name in ('get_daily_steps', 'get_steps_data'):
        fn = getattr(api, method_name, None)
        if not fn:
            continue
        try:
            result = fn(start_date, end_date)
            if result is not None:
                return result
        except TypeError:
            # Method might only accept 1 arg — skip silently
            pass
        except Exception as e:
            print(f"  [warn] {method_name}: {e}")
    return []

def norm_steps(raw) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        steps = item.get('totalSteps') or item.get('steps')
        if steps is None:
            continue
        out.append({
            'calendarDate': item.get('calendarDate') or item.get('date'),
            'totalSteps':   steps,
            'stepGoal':     item.get('stepGoal') or item.get('dailyStepGoal'),
            'totalDistance':item.get('totalDistance'),
        })
    return out

def norm_activities(raw) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for a in raw:
        out.append({
            'id':              a.get('activityId') or a.get('id'),
            'name':            a.get('activityName') or a.get('name') or 'Activity',
            'type':            (a.get('activityType') or {}).get('typeKey') if isinstance(a.get('activityType'), dict) else a.get('activityType') or a.get('type', ''),
            'start_time':      a.get('startTimeLocal') or a.get('startTimeGMT') or a.get('start_time'),
            'duration_seconds':a.get('duration') or a.get('elapsedDuration') or a.get('duration_seconds', 0),
            'calories':        a.get('calories'),
            'avg_hr_bpm':      a.get('averageHR') or a.get('avgHr') or a.get('avg_hr_bpm'),
            'max_hr_bpm':      a.get('maxHR') or a.get('maxHr'),
            'distance_meters': a.get('distance'),
        })
    return out

def norm_body_battery(raw) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        charged = item.get('charged') or item.get('bodyBatteryChargedValue')
        drained = item.get('drained') or item.get('bodyBatteryDrainedValue')
        # Derive daily stress score: sum of absolute stress-event drains
        stress_drain = 0
        for ev in (item.get('events') or []):
            if ev.get('type') == 'STRESS' and (ev.get('body_battery_impact') or 0) < 0:
                stress_drain += abs(ev.get('body_battery_impact', 0))
        out.append({
            'date':         item.get('date') or item.get('calendarDate'),
            'charged':      charged,
            'drained':      drained,
            'stress_drain': stress_drain if stress_drain else None,
        })
    return [x for x in out if x['date']]

def norm_body_comp(raw) -> dict | None:
    """Extract the most recent body comp reading that has full data."""
    if not raw:
        return None
    entries = raw.get('dateWeightList') or []
    # Prefer entries from smart scale (have body fat / muscle mass), else fallback to any weight
    full = [e for e in entries if e.get('muscleMass') and e.get('bodyFat')]
    partial = [e for e in entries if e.get('weight')]
    best = (full or partial or [None])[-1]   # most recent
    if not best:
        return None
    weight_kg = (best.get('weight') or 0) / 1000        # Garmin stores grams
    body_fat  = best.get('bodyFat')                      # %
    muscle_kg = (best.get('muscleMass') or 0) / 1000    # stored in grams
    lean_kg   = muscle_kg or (weight_kg * (1 - (body_fat or 0) / 100) if body_fat else None)
    return {
        'date':       best.get('calendarDate'),
        'weight_kg':  round(weight_kg, 1) if weight_kg else None,
        'bmi':        round(best.get('bmi') or 0, 1) or None,
        'body_fat':   body_fat,
        'lean_kg':    round(lean_kg, 1) if lean_kg else None,
        'muscle_kg':  round(muscle_kg, 1) if muscle_kg else None,
        'visceral_fat': best.get('visceralFat'),
    }

def compute_zone_minutes(activities: list, days: int = 30) -> dict:
    """
    Estimate time in HR Zones 1–3 and 4–5 across the last N days
    using activity type and average HR as proxy.
    (Garmin doesn't expose per-activity zone breakdown without an extra API call.)
    """
    cutoff = date.today() - timedelta(days=days)
    z13 = z45 = 0.0
    for a in activities:
        start = a.get('start_time', '') or ''
        try:
            act_date = date.fromisoformat(start[:10])
        except ValueError:
            continue
        if act_date < cutoff:
            continue
        mins = (a.get('duration_seconds') or 0) / 60
        t = (a.get('type') or '').lower()
        avg_hr = a.get('avg_hr_bpm') or 0
        # Classify by activity type + avg HR
        if t in ('strength_training', 'yoga', 'pilates', 'flexibility'):
            z13 += mins * 0.80
            z45 += mins * 0.05
        elif t in ('running', 'treadmill_running', 'trail_running'):
            if avg_hr >= 160:
                z13 += mins * 0.20; z45 += mins * 0.70
            elif avg_hr >= 140:
                z13 += mins * 0.45; z45 += mins * 0.40
            else:
                z13 += mins * 0.75; z45 += mins * 0.10
        elif t in ('cycling', 'indoor_cycling', 'virtual_ride'):
            if avg_hr >= 155:
                z13 += mins * 0.25; z45 += mins * 0.60
            else:
                z13 += mins * 0.60; z45 += mins * 0.20
        elif t in ('badminton', 'tennis', 'squash', 'basketball'):
            z13 += mins * 0.40; z45 += mins * 0.40
        elif t in ('breathwork', 'meditation'):
            z13 += mins * 0.90
        else:
            z13 += mins * 0.60; z45 += mins * 0.15
    return {'z1_3_minutes': round(z13), 'z4_5_minutes': round(z45)}

# ─── Main sync (all data in one call) ─────────────────────────────────────────
def sync_all(req_body: dict) -> dict:
    api = get_client()
    errors = []
    result = {}

    print("  [sync]  → profile")
    result['profile'] = safe(api.get_user_profile, 'profile')

    # RHR — try last 5 days until we get a reading
    print("  [sync]  → rhr")
    result['rhr'] = None
    for i in range(1, 6):
        rhr_raw = safe(lambda d=ds(i): api.get_rhr_day(d), f'rhr day -{i}')
        if not rhr_raw:
            continue
        v = (rhr_raw.get('restingHeartRate')
             or (rhr_raw.get('allMetrics', {})
                 .get('metricsMap', {})
                 .get('WELLNESS_RESTING_HEART_RATE', [{}])[0]
                 .get('value')))
        if v is not None:
            result['rhr'] = {'value': v, 'date': ds(i)}
            break

    # Body battery — 30 days (includes stress events for daily stress score)
    print("  [sync]  → body battery (30d)")
    bb_raw = safe(lambda: api.get_body_battery(ds(30), ds(0)), 'body_battery', [])
    result['body_battery'] = norm_body_battery(bb_raw)

    # Steps — 30 days
    print("  [sync]  → steps (30d)")
    st_raw = safe(lambda: get_steps(api, ds(30), ds(0)), 'steps', [])
    result['steps'] = norm_steps(st_raw)

    # Activities — last 100 (enough for 30-day zone calculation)
    print("  [sync]  → activities (100)")
    ac_raw = safe(lambda: api.get_activities(0, 100), 'activities', [])
    acts_normalised = norm_activities(ac_raw)
    result['activities'] = {'activities': acts_normalised}
    result['zone_minutes_30d'] = compute_zone_minutes(acts_normalised, days=30)

    # Body composition — lean mass is the 9th WHOOP healthspan metric
    print("  [sync]  → body composition")
    bc_raw = safe(lambda: api.get_body_composition(ds(90), ds(0)), 'body_comp')
    result['body_comp'] = norm_body_comp(bc_raw)

    # VO2 max — try recent days until Garmin returns a value
    print("  [sync]  → VO2 max")
    vo2 = None
    for i in range(0, 30):
        mm = safe(lambda d=ds(i): api.get_max_metrics(d), f'vo2 {ds(i)}')
        if mm:
            items = mm if isinstance(mm, list) else [mm]
            for it in items:
                g = (it or {}).get('generic') or {}
                v = g.get('vo2MaxPreciseValue') or g.get('vo2MaxValue')
                if v:
                    vo2 = {'value': round(float(v), 1), 'date': ds(i)}
                    break
        if vo2:
            break
    result['vo2'] = vo2

    # HRV baseline — Garmin's personal balanced range (best practice: score HRV
    # against the individual's own baseline, not population norms)
    print("  [sync]  → HRV baseline")
    hrv_raw = safe(lambda: api.get_hrv_data(ds(1)), 'hrv_baseline')
    if hrv_raw:
        hs = hrv_raw.get('hrvSummary') or hrv_raw
        bl = hs.get('baseline') or {}
        result['hrv_baseline'] = {
            'weekly_avg': hs.get('weeklyAvg'),
            'last_night': hs.get('lastNightAvg'),
            'balanced_low': bl.get('balancedLow'),
            'balanced_upper': bl.get('balancedUpper'),
            'low_upper': bl.get('lowUpper'),
            'status': hs.get('status'),
        }

    # Daily stats — 7 days of all-day stress + RHR (for stress domain + trends)
    print("  [sync]  → daily stress/RHR (7d)")
    daily = []
    for i in range(1, 8):
        st = safe(lambda d=ds(i): api.get_stats(d), f'stats {ds(i)}')
        if st:
            daily.append({
                'date': ds(i),
                'avg_stress': st.get('averageStressLevel'),
                'max_stress': st.get('maxStressLevel'),
                'rhr': st.get('restingHeartRate'),
                'steps': st.get('totalSteps'),
            })
    result['daily_stats'] = daily

    # Sleep — 30 nights sequential (the slow part — ~30s)
    print("  [sync]  → sleep (30 nights) — this takes ~30s…")
    sleep = []
    for i in range(1, 31):
        raw = safe(lambda d=ds(i): api.get_sleep_data(d), f'sleep {ds(i)}')
        s = norm_sleep(raw, ds(i))
        if s:
            sleep.append(s)
    result['sleep'] = sleep

    result['errors'] = errors
    return result

# ─── HTTP handler ─────────────────────────────────────────────────────────────
MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js':   'text/javascript; charset=utf-8',
    '.mjs':  'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.webmanifest': 'application/manifest+json',
    '.svg':  'image/svg+xml',
    '.png':  'image/png',
    '.css':  'text/css; charset=utf-8',
    '.ico':  'image/x-icon',
}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Compact logging
        status = str(args[1]) if len(args) > 1 else '?'
        print(f"  [{status}] {args[0]}")

    def send_cors(self, status: int):
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, x-app-token')
        self.send_header('X-Content-Type-Options', 'nosniff')

    def send_json(self, status: int, data):
        body = json.dumps(data, default=str).encode('utf-8')
        self.send_cors(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_cors(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/health':
            self.send_json(200, {
                'ok': True,
                'garminConfigured': bool(EMAIL and PASSWORD),
                'mockGarmin': False,
            })
            return

        if path == '/api/food':
            entries = load_food()
            pending = [e for e in entries if not e.get('nutrition')]
            self.send_json(200, {'result': entries, 'pending': len(pending)})
            return

        if path == '/api/cache':
            cached = load_cache()
            if cached:
                age_s = None
                try:
                    from datetime import datetime, timezone
                    cached_at = datetime.fromisoformat(cached.get('_cached_at',''))
                    age_s = int((datetime.now(timezone.utc) - cached_at).total_seconds())
                except Exception:
                    pass
                self.send_json(200, {'result': cached, 'cached_at': cached.get('_cached_at'), 'age_seconds': age_s})
            else:
                self.send_json(404, {'error': 'No cache yet — run a Sync first.'})
            return

        # Static file serving
        requested = 'health-operating-system.html' if path in ('/', '') else path.lstrip('/')
        file_path = Path('.') / requested
        # Safety: don't serve files outside cwd
        try:
            file_path = file_path.resolve()
            cwd = Path('.').resolve()
            if not str(file_path).startswith(str(cwd)):
                self.send_json(403, {'error': 'Forbidden'})
                return
        except Exception:
            self.send_json(400, {'error': 'Bad path'})
            return

        if file_path.exists() and file_path.is_file():
            data = file_path.read_bytes()
            ctype = MIME.get(file_path.suffix, 'application/octet-stream')
            self.send_cors(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_json(404, {'error': f'Not found: {requested}'})

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = {}
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except Exception:
                pass

        path = urlparse(self.path).path

        # Nutrition log — accepts {text,date,nutrition?,id?} or {entries:[...]}
        if path == '/api/food':
            payload = body.get('entries', body)
            entries = upsert_food(payload)
            self.send_json(200, {'result': entries, 'saved': True})
            return

        # Main sync endpoint
        if path == '/api/garmin/sync':
            t0 = time.time()
            print("  [sync] Starting full Garmin sync…")
            try:
                with SYNC_LOCK:
                    data = sync_all(body)
                elapsed = round(time.time() - t0, 1)
                print(f"  [sync] Done in {elapsed}s — sleep:{len(data.get('sleep',[]))}, steps:{len(data.get('steps',[]))}, acts:{len(data.get('activities',{}).get('activities',[]))}, errors:{len(data.get('errors',[]))}")
                save_cache(data)   # persist for next startup
                self.send_json(200, {'result': data})
            except Exception as e:
                print(f"  [sync] Error: {e}")
                if 'auth' in str(e).lower() or '401' in str(e) or 'token' in str(e).lower():
                    reset_client()
                self.send_json(500, {'error': str(e)})
            return

        # Individual endpoints (used by the web app's fallback path)
        if path.startswith('/api/garmin/'):
            endpoint = path.split('/')[-1]
            try:
                api = get_client()
                s_date = body.get('start_date', ds(15))
                e_date = body.get('end_date', ds(1))
                dispatch = {
                    'user-profile':    lambda: api.get_user_profile(),
                    'rhr-day':         lambda: api.get_rhr_day(body.get('date', ds(1))),
                    'sleep-summary':   lambda: norm_sleep(api.get_sleep_data(body.get('date', ds(1))), body.get('date', ds(1))),
                    'daily-steps':     lambda: norm_steps(get_steps(api, s_date, e_date)),
                    'body-battery':    lambda: norm_body_battery(api.get_body_battery(body.get('start_date', ds(14)), body.get('end_date', ds(0)))),
                    'activities':      lambda: {'activities': norm_activities(api.get_activities(body.get('start', 0), body.get('limit', 40)))},
                    'vo2max-trend':    lambda: api.get_max_metrics(ds(1)),
                }
                fn = dispatch.get(endpoint)
                if fn:
                    self.send_json(200, {'result': fn()})
                else:
                    self.send_json(404, {'error': f'Unknown endpoint: {endpoint}'})
            except Exception as e:
                print(f"  [error] {endpoint}: {e}")
                if 'auth' in str(e).lower() or '401' in str(e):
                    reset_client()
                self.send_json(500, {'error': str(e)})
            return

        # AI endpoints — /api/ai/coach and /api/ai/nutrition
        if path.startswith('/api/ai/'):
            kind = path.split('/')[-1]   # 'coach' or 'nutrition'
            try:
                text = call_ai(kind, body)
                self.send_json(200, {'result': {'text': text}})
            except Exception as e:
                print(f"  [ai error] {kind}: {e}")
                self.send_json(500, {'error': str(e)})
            return

        self.send_json(404, {'error': 'Not found'})


# ─── AI helper ────────────────────────────────────────────────────────────────
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-3-5-haiku-latest')

def call_ai(kind: str, body: dict) -> str:
    """
    Call the Anthropic API for coach or nutrition responses.
    Raises if no key is configured or the call fails.
    """
    if not ANTHROPIC_KEY:
        raise RuntimeError(
            'Add ANTHROPIC_API_KEY=sk-ant-... to your .env.local and restart the server.'
        )
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            'Run: pip install anthropic  — then restart the server.'
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    if kind == 'nutrition':
        food_text = body.get('foodText', '')
        system = (
            'You are a precision nutrition analyst. '
            'Estimate macros and key micronutrients for the food described. '
            'Return ONLY a JSON object — no markdown, no prose — with these fields:\n'
            '{"calories":N,"protein_g":N,"carbs_g":N,"fat_g":N,"fiber_g":N,'
            '"sodium_mg":N,"omega3_g":N,"vitamin_d_iu":N,"calcium_mg":N,'
            '"iron_mg":N,"magnesium_mg":N,"zinc_mg":N,"vitamin_b12_ug":N,'
            '"vitamin_c_mg":N,"folate_ug":N,"potassium_mg":N,'
            '"confidence":"high|medium|low",'
            '"improvements":["string","string"]}\n'
            'Use null for unknown values. Be evidence-based and realistic.'
        )
        user = f'Food: {food_text}'
    else:
        # Coach — body contains the full context dict from coachContext()
        ctx = body.get('context', body)
        system = (
            'You are a personal health coach reviewing Garmin wearable data. '
            'Be specific, data-driven, and concise. Avoid generic advice. '
            'Focus on what the numbers actually say. '
            'Format your response as:\n'
            'Status: [1-2 sentences]\n'
            'Training: [specific recommendation]\n'
            'Food today: [specific suggestion]\n'
            'Supplements: [evidence-based only]\n'
            'Watch out: [1 flag if any]'
        )
        user = f'Health data: {json.dumps(ctx, default=str)}'

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=600,
        system=system,
        messages=[{'role': 'user', 'content': user}],
    )
    return response.content[0].text


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not EMAIL or not PASSWORD:
        print()
        print('  ┌─────────────────────────────────────────────────────┐')
        print('  │  Health OS — first-time setup                       │')
        print('  └─────────────────────────────────────────────────────┘')
        print()
        print('  No Garmin credentials found in .env.local')
        print('  (Or copy .env.example → .env.local and fill in your details)')
        print()
        import getpass as _gp
        _email = input('  Garmin email: ').strip()
        _pass  = _gp.getpass('  Garmin password: ').strip()
        if not _email or not _pass:
            print()
            print('  [error] Credentials required. Exiting.')
            sys.exit(1)
        # Persist for next run
        _save = input('\n  Save to .env.local for next time? [Y/n]: ').strip().lower()
        if _save != 'n':
            Path('.env.local').write_text(
                f'GARMIN_EMAIL={_email}\n'
                f'GARMIN_PASSWORD={_pass}\n'
                'PORT=8787\n'
                '\n# AI coaching (optional)\n'
                '# Get your key from: https://console.anthropic.com\n'
                'ANTHROPIC_API_KEY=\n'
            )
            print('  Saved to .env.local\n')
        global EMAIL, PASSWORD
        EMAIL, PASSWORD = _email, _pass

    print(f'\n  Health OS — Python server')
    print(f'  Garmin account : {EMAIL}')
    print(f'  URL            : http://127.0.0.1:{PORT}')
    print(f'  Press Ctrl+C to stop\n')

    # ── Background auto-sync: keeps the cache fresh with no browser/Cowork involvement ──
    SYNC_INTERVAL_MIN = int(os.environ.get('SYNC_INTERVAL_MIN', '180'))

    def cache_age_minutes():
        c = load_cache()
        if not c or not c.get('_cached_at'):
            return None
        try:
            from datetime import datetime, timezone
            t = datetime.fromisoformat(c['_cached_at'])
            return (datetime.now(timezone.utc) - t).total_seconds() / 60
        except Exception:
            return None

    def auto_sync_loop():
        while True:
            age = cache_age_minutes()
            due = age is None or age >= SYNC_INTERVAL_MIN
            if due and SYNC_LOCK.acquire(blocking=False):
                try:
                    print(f'  [auto-sync] cache age {round(age) if age is not None else "∞"}m ≥ {SYNC_INTERVAL_MIN}m — syncing…')
                    data = sync_all({})
                    save_cache(data)
                    print(f'  [auto-sync] done — sleep:{len(data.get("sleep", []))}, errors:{len(data.get("errors", []))}')
                except Exception as e:
                    print(f'  [auto-sync] failed: {e}')
                finally:
                    SYNC_LOCK.release()
            time.sleep(15 * 60)  # re-check every 15 min

    threading.Thread(target=auto_sync_loop, daemon=True, name='auto-sync').start()
    print(f'  Auto-sync      : every {SYNC_INTERVAL_MIN} min (set SYNC_INTERVAL_MIN in .env.local to change)\n')

    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n  Stopped.')
