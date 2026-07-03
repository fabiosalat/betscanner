from engines.surebet_engine import SurebetEngine
from engines.matched_engine import MatchedEngine

def test_surebet_positive():
    rows=[{'event_id':1,'league':'Serie A','home_team':'A','away_team':'B','start_time':'','bookmaker':'Sisal IT','market':'MATCH_ODDS','selection':'HOME','back_odd':2.2,'lay_price':2.05}]
    out=SurebetEngine().calculate(rows)
    assert out and out[0].roi > 0

def test_matched():
    rows=[{'event_id':1,'league':'Serie A','home_team':'A','away_team':'B','start_time':'','bookmaker':'Sisal IT','market':'MATCH_ODDS','selection':'HOME','back_odd':2.0,'lay_price':2.02}]
    out=MatchedEngine().calculate(rows)
    assert out
