from database.models import Opportunity
from config import BETFAIR_COMMISSION, DEFAULT_STAKE, MIN_SUREBET_ROI, MAX_RESULTS
class SurebetEngine:
    def __init__(self,commission=BETFAIR_COMMISSION,stake=DEFAULT_STAKE,min_roi=MIN_SUREBET_ROI): self.commission=commission; self.stake=stake; self.min_roi=min_roi
    def calculate_lay_stake(self,back_odd,lay_odd): return 0 if lay_odd<=self.commission else (self.stake*back_odd)/(lay_odd-self.commission)
    def calculate(self,rows):
        out=[]
        for r in rows:
            back=float(r['back_odd']); lay=float(r['lay_price'])
            if back<=1 or lay<=1: continue
            roi=((back*(1-self.commission))/lay-1)*100
            if roi<self.min_roi: continue
            ls=self.calculate_lay_stake(back,lay); liab=ls*(lay-1); event=f"{r['home_team']} - {r['away_team']}"
            out.append(Opportunity('surebet',r['event_id'],r['league'] or '',event,r['start_time'] or '',r['market'],r['selection'],r['bookmaker'],back,lay,round(roi,3),0,round(ls,2),round(liab,2)))
        return sorted(out,key=lambda x:x.roi,reverse=True)[:MAX_RESULTS]
