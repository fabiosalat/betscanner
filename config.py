import os
import tempfile
from dotenv import load_dotenv
load_dotenv()
def env(name, default=""):
    return os.getenv(name) or default
APP_NAME = "BetScanner"
SPORT = "soccer"
ODDSPAPI_SPORT_ID = int(env("ODDSPAPI_SPORT_ID", "10"))
ODDSPAPI_LANGUAGE = env("ODDSPAPI_LANGUAGE", "en")
ODDSPAPI_STATUS_ID = int(env("ODDSPAPI_STATUS_ID", "0"))
BETFAIR_EVENT_TYPE_SOCCER = "1"
LOOKAHEAD_HOURS = int(env("LOOKAHEAD_HOURS", "72"))
BETFAIR_COMMISSION = float(env("BETFAIR_COMMISSION", "0.02"))
DEFAULT_STAKE = float(env("DEFAULT_STAKE", "100"))
MIN_SUREBET_ROI = float(env("MIN_SUREBET_ROI", "0.8"))
MAX_QUALIFYING_LOSS = float(env("MAX_QUALIFYING_LOSS", "5"))
MAX_RESULTS = int(env("MAX_RESULTS", "25"))
FUZZY_SCORE = int(env("FUZZY_SCORE", "90"))
MAX_TIME_DIFF_MINUTES = int(env("MAX_TIME_DIFF_MINUTES", "20"))
RETRY_COUNT = int(env("RETRY_COUNT", "3"))
REQUEST_TIMEOUT = int(env("REQUEST_TIMEOUT", "20"))
ODDSPAPI_RATE_LIMIT_COOLDOWN_SECONDS = int(env("ODDSPAPI_RATE_LIMIT_COOLDOWN_SECONDS", "900"))
ODDSPAPI_REQUEST_COOLDOWN_SECONDS = float(env("ODDSPAPI_REQUEST_COOLDOWN_SECONDS", "2.1"))
ODDSPAPI_MAX_BOOKMAKERS = int(env("ODDSPAPI_MAX_BOOKMAKERS", "2"))
ODDSPAPI_ALLOWED_TOURNAMENTS = [item.strip().lower() for item in env("ODDSPAPI_ALLOWED_TOURNAMENTS", "world cup,coppa del mondo,wimbledon").split(",") if item.strip()]
DB_PATH = env("DB_PATH", "instance/database.db")
BOOKMAKERS = ["Sisal IT","Snai IT","Eurobet IT","Planetwin365 IT","Betflag IT","Bet365 IT","EPLAY24 IT"]
SUPPORTED_MARKETS = ["MATCH_ODDS","MATCH_ODDS_HT","DOUBLE_CHANCE","BTTS","BTTS_HT","OVER_UNDER_05","OVER_UNDER_15","OVER_UNDER_25","OVER_UNDER_35","OVER_UNDER_45","OVER_UNDER_HT_05","OVER_UNDER_HT_15"]
ODDSPAPI_KEY = env("ODDSPAPI_KEY")
BETFAIR_APP_KEY = env("BETFAIR_APP_KEY")
BETFAIR_SSOID = env("BETFAIR_SSOID")
BETFAIR_USERNAME = env("BETFAIR_USERNAME")
BETFAIR_PASSWORD = env("BETFAIR_PASSWORD")
BETFAIR_CERT = env("BETFAIR_CERT")
BETFAIR_KEY = env("BETFAIR_KEY")
BETFAIR_CERT_FILE = env("BETFAIR_CERT_FILE", os.path.join(tempfile.gettempdir(), "betscanner-betfair", "client-2048.crt"))
BETFAIR_KEY_FILE = env("BETFAIR_KEY_FILE", os.path.join(tempfile.gettempdir(), "betscanner-betfair", "client-2048.key"))
TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")
SECRET_KEY = env("SECRET_KEY", "dev-secret")

def missing_api_credentials():
    missing = []
    if not ODDSPAPI_KEY:
        missing.append("ODDSPAPI_KEY")
    if not BETFAIR_APP_KEY:
        missing.append("BETFAIR_APP_KEY")
    if not BETFAIR_SSOID:
        for key, value in {
            "BETFAIR_USERNAME": BETFAIR_USERNAME,
            "BETFAIR_PASSWORD": BETFAIR_PASSWORD,
        }.items():
            if not value:
                missing.append(key)
        if not ((BETFAIR_CERT and BETFAIR_KEY) or (os.path.exists(BETFAIR_CERT_FILE) and os.path.exists(BETFAIR_KEY_FILE))):
            missing.extend(["BETFAIR_CERT", "BETFAIR_KEY"])
    return missing
