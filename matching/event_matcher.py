from datetime import datetime, timezone
from rapidfuzz import fuzz
from config import FUZZY_SCORE, MAX_TIME_DIFF_MINUTES
from matching.normalizer import normalize_team_name, parse_betfair_event_name

def parse_dt(value):
    if not value: return None
    if isinstance(value, datetime): return value
    try: return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except ValueError: return None
class EventMatcher:
    def __init__(self,min_score=FUZZY_SCORE,max_minutes=MAX_TIME_DIFF_MINUTES): self.min_score=min_score; self.max_minutes=max_minutes
    def _time_ok(self,a,b):
        da,db=parse_dt(a),parse_dt(b)
        if not da or not db: return True
        if da.tzinfo is None: da=da.replace(tzinfo=timezone.utc)
        if db.tzinfo is None: db=db.replace(tzinfo=timezone.utc)
        return abs((da-db).total_seconds())/60 <= self.max_minutes
    def score_event(self,odds_event,bf_market):
        home=normalize_team_name(odds_event.get('home_team','')); away=normalize_team_name(odds_event.get('away_team',''))
        bh,ba=parse_betfair_event_name(bf_market.get('event_name','')); bh=normalize_team_name(bh); ba=normalize_team_name(ba)
        sd=(fuzz.token_sort_ratio(home,bh)+fuzz.token_sort_ratio(away,ba))/2
        sr=(fuzz.token_sort_ratio(home,ba)+fuzz.token_sort_ratio(away,bh))/2
        if not self._time_ok(odds_event.get('start_time'),bf_market.get('start_time')): return 0
        return max(sd,sr)
    def find_best(self,odds_event,bf_markets,market):
        best=None; best_score=0
        for item in [m for m in bf_markets if m.get('market')==market]:
            score=self.score_event(odds_event,item)
            if score>best_score: best=item; best_score=score
        if best and best_score>=self.min_score:
            best=dict(best); best['confidence_score']=best_score; return best
        return None
