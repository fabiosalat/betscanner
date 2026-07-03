import hashlib
import json
from typing import Iterable, Optional
from database.db import get_connection
from database.models import Event, BookmakerOdd, BetfairOdd, Opportunity

class Repository:
    def upsert_event(self, event: Event) -> int:
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO events (odds_event_id, league, home_team, away_team, start_time, normalized_home, normalized_away)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(odds_event_id) DO UPDATE SET
                    league=excluded.league, home_team=excluded.home_team, away_team=excluded.away_team,
                    start_time=excluded.start_time, normalized_home=excluded.normalized_home,
                    normalized_away=excluded.normalized_away, updated_at=CURRENT_TIMESTAMP
            """, (event.odds_event_id,event.league,event.home_team,event.away_team,event.start_time,event.normalized_home,event.normalized_away))
            row = conn.execute("SELECT id FROM events WHERE odds_event_id=?", (event.odds_event_id,)).fetchone()
            conn.commit()
            return int(row["id"])

    def insert_odds_bulk(self, odds: Iterable[BookmakerOdd]) -> None:
        rows = list(odds)
        with get_connection() as conn:
            conn.executemany("""
                INSERT INTO odds (event_id, bookmaker, market, selection, odd)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(event_id, bookmaker, market, selection) DO UPDATE SET
                    odd=excluded.odd, updated_at=CURRENT_TIMESTAMP
            """, [(o.event_id,o.bookmaker,o.market,o.selection,o.odd) for o in rows])
            conn.commit()

    def insert_betfair_odds_bulk(self, odds: Iterable[BetfairOdd]) -> None:
        rows = list(odds)
        with get_connection() as conn:
            conn.executemany("""
                INSERT INTO betfair_odds (event_id, betfair_market_id, market, selection, lay_price, lay_size)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, market, selection) DO UPDATE SET
                    betfair_market_id=excluded.betfair_market_id, lay_price=excluded.lay_price,
                    lay_size=excluded.lay_size, updated_at=CURRENT_TIMESTAMP
            """, [(o.event_id,o.betfair_market_id,o.market,o.selection,o.lay_price,o.lay_size) for o in rows])
            conn.commit()

    def clear_current_refresh_data(self):
        with get_connection() as conn:
            conn.execute("DELETE FROM odds")
            conn.execute("DELETE FROM betfair_odds")
            conn.execute("DELETE FROM opportunities")
            conn.commit()

    def get_joined_odds(self):
        with get_connection() as conn:
            return conn.execute("""
                SELECT e.id as event_id,e.league,e.home_team,e.away_team,e.start_time,
                       o.bookmaker,o.market,o.selection,o.odd as back_odd,
                       b.lay_price,b.lay_size,b.betfair_market_id
                FROM odds o
                JOIN events e ON e.id=o.event_id
                JOIN betfair_odds b ON b.event_id=o.event_id AND b.market=o.market AND b.selection=o.selection
                WHERE b.lay_price IS NOT NULL
            """).fetchall()

    def save_opportunities(self, opportunities: Iterable[Opportunity]) -> None:
        rows = list(opportunities)
        with get_connection() as conn:
            conn.executemany("""
                INSERT INTO opportunities (type,event_id,league,event_name,start_time,market,selection,bookmaker,back_odd,lay_odd,roi,qualifying_loss,lay_stake,liability)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(type,event_id,market,selection,bookmaker) DO UPDATE SET
                    back_odd=excluded.back_odd, lay_odd=excluded.lay_odd, roi=excluded.roi,
                    qualifying_loss=excluded.qualifying_loss, lay_stake=excluded.lay_stake,
                    liability=excluded.liability, updated_at=CURRENT_TIMESTAMP
            """, [(o.type,o.event_id,o.league,o.event_name,o.start_time,o.market,o.selection,o.bookmaker,o.back_odd,o.lay_odd,o.roi,o.qualifying_loss,o.lay_stake,o.liability) for o in rows])
            for o in rows:
                raw=f"{o.type}|{o.event_id}|{o.market}|{o.selection}|{o.bookmaker}|{o.back_odd:.4f}|{o.lay_odd:.4f}"
                h=hashlib.sha256(raw.encode()).hexdigest()
                conn.execute("""
                    INSERT OR IGNORE INTO opportunities_history (hash,type,event_id,league,event_name,start_time,market,selection,bookmaker,back_odd,lay_odd,roi,qualifying_loss,lay_stake,liability)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (h,o.type,o.event_id,o.league,o.event_name,o.start_time,o.market,o.selection,o.bookmaker,o.back_odd,o.lay_odd,o.roi,o.qualifying_loss,o.lay_stake,o.liability))
            conn.commit()

    def top_opportunities(self, type_: str, limit: int = 25):
        order = "roi DESC" if type_ == "surebet" else "qualifying_loss ASC"
        with get_connection() as conn:
            return conn.execute(f"SELECT * FROM opportunities WHERE type=? ORDER BY {order} LIMIT ?", (type_, limit)).fetchall()

    def search_opportunities(self, query: str, limit: int = 25):
        q = f"%{query.lower()}%"
        with get_connection() as conn:
            return conn.execute("""
                SELECT * FROM opportunities
                WHERE lower(event_name) LIKE ? OR lower(league) LIKE ? OR lower(bookmaker) LIKE ? OR lower(market) LIKE ?
                ORDER BY CASE WHEN type='surebet' THEN roi ELSE -qualifying_loss END DESC
                LIMIT ?
            """, (q,q,q,q,limit)).fetchall()

    def get_event(self, event_id:int):
        with get_connection() as conn: return conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    def get_event_odds(self, event_id:int):
        with get_connection() as conn: return conn.execute("SELECT * FROM odds WHERE event_id=? ORDER BY market,selection,bookmaker", (event_id,)).fetchall()
    def get_event_betfair_odds(self, event_id:int):
        with get_connection() as conn: return conn.execute("SELECT * FROM betfair_odds WHERE event_id=? ORDER BY market,selection", (event_id,)).fetchall()

    def save_event_mapping(self, odds_event_id, market, betfair_market_id, betfair_event_id, confidence):
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO event_mapping (odds_event_id,market,betfair_market_id,betfair_event_id,confidence_score)
                VALUES (?,?,?,?,?)
                ON CONFLICT(odds_event_id,market) DO UPDATE SET
                    betfair_market_id=excluded.betfair_market_id, betfair_event_id=excluded.betfair_event_id,
                    confidence_score=excluded.confidence_score, updated_at=CURRENT_TIMESTAMP
            """, (odds_event_id,market,betfair_market_id,betfair_event_id,confidence))
            conn.commit()

    def get_event_mapping(self, odds_event_id, market):
        with get_connection() as conn: return conn.execute("SELECT * FROM event_mapping WHERE odds_event_id=? AND market=?", (odds_event_id,market)).fetchone()

    def set_cache(self, key, value):
        if not isinstance(value, str): value = json.dumps(value, ensure_ascii=False)
        with get_connection() as conn:
            conn.execute("INSERT INTO cache (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP", (key,value))
            conn.commit()
    def get_cache(self, key) -> Optional[str]:
        with get_connection() as conn:
            row = conn.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def save_refresh_history(self,duration,events_count,api_calls,status,message):
        with get_connection() as conn:
            conn.execute("INSERT INTO refresh_history (duration,events_count,api_calls,status,message) VALUES (?,?,?,?,?)", (duration,events_count,api_calls,status,message))
            conn.commit()
    def get_last_refresh(self):
        with get_connection() as conn: return conn.execute("SELECT * FROM refresh_history ORDER BY id DESC LIMIT 1").fetchone()
    def counts(self):
        with get_connection() as conn:
            return {
                "events": conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"],
                "surebets": conn.execute("SELECT COUNT(*) c FROM opportunities WHERE type='surebet'").fetchone()["c"],
                "matched": conn.execute("SELECT COUNT(*) c FROM opportunities WHERE type='matched'").fetchone()["c"],
            }
    def refresh_stats(self):
        with get_connection() as conn:
            br=conn.execute("SELECT bookmaker,SUM(CASE WHEN type='surebet' THEN 1 ELSE 0 END) surebet_count,SUM(CASE WHEN type='matched' THEN 1 ELSE 0 END) matched_count,AVG(COALESCE(roi,0)) average_roi FROM opportunities GROUP BY bookmaker").fetchall()
            conn.execute("DELETE FROM bookmaker_stats")
            conn.executemany("INSERT INTO bookmaker_stats (bookmaker,surebet_count,matched_count,average_roi) VALUES (?,?,?,?)", [(r['bookmaker'],r['surebet_count'],r['matched_count'],r['average_roi']) for r in br])
            conn.commit()
    def top_bookmakers(self,limit=10):
        with get_connection() as conn: return conn.execute("SELECT * FROM bookmaker_stats ORDER BY surebet_count DESC,matched_count DESC,average_roi DESC LIMIT ?", (limit,)).fetchall()
