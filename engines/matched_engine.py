from database.models import Opportunity
from config import BETFAIR_COMMISSION, DEFAULT_STAKE, MAX_QUALIFYING_LOSS, MAX_RESULTS
class MatchedEngine:
    def __init__(self,commission=BETFAIR_COMMISSION,stake=DEFAULT_STAKE,max_ql=MAX_QUALIFYING_LOSS): self.commission=commission; self.stake=stake; self.max_ql=max_ql
    def lay_stake(self,back,lay): return 0 if lay<=self.commission else (self.stake*back)/(lay-self.commission)
    def ql_value(self,back,lay,ls):
        win=self.stake*(back-1)-ls*(lay-1); lose=ls*(1-self.commission)-self.stake; return min(win,lose)
    def calculate(self,rows):
        out=[]
        for r in rows:
            back=float(r['back_odd']); lay=float(r['lay_price'])
            if back<=1 or lay<=1: continue
            ls=self.lay_stake(back,lay); liab=ls*(lay-1); qlp=abs(self.ql_value(back,lay,ls))/self.stake*100
            if qlp>self.max_ql: continue
            event=f"{r['home_team']} - {r['away_team']}"
            out.append(Opportunity('matched',r['event_id'],r['league'] or '',event,r['start_time'] or '',r['market'],r['selection'],r['bookmaker'],back,lay,0,round(qlp,3),round(ls,2),round(liab,2)))
        return sorted(out,key=lambda x:x.qualifying_loss)[:MAX_RESULTS]
