from database.db import get_connection
SCHEMA = [
'CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, odds_event_id TEXT UNIQUE, league TEXT, home_team TEXT NOT NULL, away_team TEXT NOT NULL, start_time TEXT, normalized_home TEXT, normalized_away TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)',
'CREATE TABLE IF NOT EXISTS odds (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, bookmaker TEXT NOT NULL, market TEXT NOT NULL, selection TEXT NOT NULL, odd REAL NOT NULL, oddspapi_market_id TEXT, oddspapi_outcome_id TEXT, market_name TEXT, selection_name TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(event_id, bookmaker, market, selection), FOREIGN KEY(event_id) REFERENCES events(id))',
'CREATE TABLE IF NOT EXISTS oddspapi_markets (market_id TEXT PRIMARY KEY, market_name TEXT, market_type TEXT, period TEXT, handicap REAL, raw_json TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)',
'CREATE TABLE IF NOT EXISTS oddspapi_outcomes (market_id TEXT NOT NULL, outcome_id TEXT NOT NULL, outcome_name TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(market_id, outcome_id), FOREIGN KEY(market_id) REFERENCES oddspapi_markets(market_id))',
'CREATE TABLE IF NOT EXISTS betfair_odds (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, betfair_market_id TEXT, market TEXT NOT NULL, selection TEXT NOT NULL, lay_price REAL, lay_size REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(event_id, market, selection), FOREIGN KEY(event_id) REFERENCES events(id))',
'CREATE TABLE IF NOT EXISTS opportunities (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, event_id INTEGER NOT NULL, league TEXT, event_name TEXT, start_time TEXT, market TEXT NOT NULL, selection TEXT NOT NULL, bookmaker TEXT NOT NULL, back_odd REAL NOT NULL, lay_odd REAL NOT NULL, roi REAL, qualifying_loss REAL, lay_stake REAL, liability REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(type, event_id, market, selection, bookmaker), FOREIGN KEY(event_id) REFERENCES events(id))',
'CREATE TABLE IF NOT EXISTS opportunities_history (id INTEGER PRIMARY KEY AUTOINCREMENT, hash TEXT UNIQUE, type TEXT NOT NULL, event_id INTEGER, league TEXT, event_name TEXT, start_time TEXT, market TEXT, selection TEXT, bookmaker TEXT, back_odd REAL, lay_odd REAL, roi REAL, qualifying_loss REAL, lay_stake REAL, liability REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)',
'CREATE TABLE IF NOT EXISTS event_mapping (id INTEGER PRIMARY KEY AUTOINCREMENT, odds_event_id TEXT, betfair_market_id TEXT, betfair_event_id TEXT, market TEXT, confidence_score REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(odds_event_id, market))',
'CREATE TABLE IF NOT EXISTS refresh_history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, duration REAL, events_count INTEGER, api_calls INTEGER, status TEXT, message TEXT)',
'CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)',
'CREATE TABLE IF NOT EXISTS bookmaker_stats (bookmaker TEXT PRIMARY KEY, surebet_count INTEGER DEFAULT 0, matched_count INTEGER DEFAULT 0, average_roi REAL DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)',
'CREATE TABLE IF NOT EXISTS league_stats (league TEXT PRIMARY KEY, surebet_count INTEGER DEFAULT 0, matched_count INTEGER DEFAULT 0, average_roi REAL DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)']
INDEXES = ["CREATE INDEX IF NOT EXISTS idx_events_start_time ON events(start_time)","CREATE INDEX IF NOT EXISTS idx_odds_event_market ON odds(event_id, market)","CREATE INDEX IF NOT EXISTS idx_odds_bookmaker ON odds(bookmaker)","CREATE INDEX IF NOT EXISTS idx_odds_oddspapi_ids ON odds(oddspapi_market_id, oddspapi_outcome_id)","CREATE INDEX IF NOT EXISTS idx_betfair_event_market ON betfair_odds(event_id, market)","CREATE INDEX IF NOT EXISTS idx_opportunities_type ON opportunities(type)","CREATE INDEX IF NOT EXISTS idx_opportunities_roi ON opportunities(roi)","CREATE INDEX IF NOT EXISTS idx_opportunities_ql ON opportunities(qualifying_loss)"]
ODDS_COLUMNS = {"oddspapi_market_id": "TEXT", "oddspapi_outcome_id": "TEXT", "market_name": "TEXT", "selection_name": "TEXT"}
def init_db():
    with get_connection() as conn:
        for sql in SCHEMA: conn.execute(sql)
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(odds)").fetchall()}
        for name, type_ in ODDS_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE odds ADD COLUMN {name} {type_}")
        for sql in INDEXES: conn.execute(sql)
        conn.commit()
if __name__ == "__main__": init_db()
