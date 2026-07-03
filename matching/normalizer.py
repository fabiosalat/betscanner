import re, unicodedata
from matching.team_aliases import TEAM_ALIASES
STOPWORDS={"fc","cf","sc","afc","calcio","club","the","de","la"}
def strip_accents(value:str)->str:
    return ''.join(c for c in unicodedata.normalize('NFKD',value or '') if not unicodedata.combining(c))
def clean_text(value:str)->str:
    value=strip_accents(value).lower().replace('&',' and ')
    value=re.sub(r'[^a-z0-9\s\-\.]',' ',value)
    return re.sub(r'\s+',' ',value).strip()
def normalize_team_name(name:str)->str:
    value=clean_text(name)
    value=TEAM_ALIASES.get(value,value)
    tokens=[t for t in value.split() if t not in STOPWORDS]
    normalized=' '.join(tokens).strip()
    return TEAM_ALIASES.get(normalized,normalized)
def normalize_league(league:str)->str: return re.sub(r'\s+',' ',league or '').strip()
def parse_betfair_event_name(event_name:str):
    text=event_name or ''
    for sep in [' v ',' vs ',' - ']:
        if sep in text.lower():
            parts=re.split(re.escape(sep),text,maxsplit=1,flags=re.IGNORECASE)
            return parts[0].strip(),parts[1].strip()
    return text,''
