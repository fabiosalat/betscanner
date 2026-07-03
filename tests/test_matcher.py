from matching.event_matcher import EventMatcher

def test_matcher_inter_milan():
    odds={'home_team':'Inter Milan','away_team':'AC Milan','start_time':'2026-06-01T20:00:00+00:00'}
    bf={'event_name':'Internazionale v Milan','start_time':'2026-06-01T20:05:00+00:00','market':'MATCH_ODDS'}
    assert EventMatcher(min_score=80).score_event(odds,bf) >= 80
