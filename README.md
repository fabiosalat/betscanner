# BetScanner

Dashboard personale Flask per cercare opportunità di **surebet** e **matched betting** confrontando bookmaker italiani con Betfair Exchange.

## Cosa include

- Flask + Bootstrap + DataTables
- SQLite locale
- Refresh manuale
- OddsPapi adapter
- Betfair Exchange adapter con certificati
- Catalogo mercati OddsPapi salvato in SQLite
- Selezione bookmaker OddsPapi da UI, massimo 5 per refresh
- Matching eventi con RapidFuzz
- Engine Surebet
- Engine Matched Betting
- Export Excel
- Telegram bot opzionale
- Deploy Render

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

L'app inizializza automaticamente SQLite all'avvio e risponde su `/health` con:

```json
{ "status": "ok" }
```

## Variabili ambiente

```env
ODDSPAPI_KEY=
ODDSPAPI_SPORT_ID=10
ODDSPAPI_LANGUAGE=en
ODDSPAPI_STATUS_ID=0
ODDSPAPI_MAX_BOOKMAKERS=5
ODDSPAPI_ALLOWED_TOURNAMENTS=world cup,coppa del mondo,wimbledon
ODDSPAPI_REQUEST_COOLDOWN_SECONDS=2.1
BETFAIR_APP_KEY=
BETFAIR_SSOID=
BETFAIR_USERNAME=
BETFAIR_PASSWORD=
BETFAIR_CERT=
BETFAIR_KEY=
```

Su Render inseriscile come **Environment Variables**. Se Betfair fornisce un cookie/token `ssoid` per l'ambiente di test, puoi usare `BETFAIR_SSOID` al posto di username/password/certificati. Per i certificati puoi usare `BETFAIR_CERT` e `BETFAIR_KEY` come secrets multilinea.
I certificati non devono essere salvati in `certs/` o committati: quando arrivano da env vengono scritti nella directory temporanea del servizio.

Se le credenziali API non sono configurate, la dashboard resta accessibile e il refresh manuale mostra un messaggio di fallback senza chiamare provider esterni.

## Refresh quote

Il refresh web richiede la selezione di almeno un bookmaker OddsPapi e ne accetta al massimo 5, in linea con il limite dell'endpoint OddsPapi. La UI impedisce selezioni oltre il limite e il backend valida comunque la richiesta prima di chiamare i provider.

Il catalogo globale OddsPapi `/v4/markets` e' trasversale ai bookmaker e viene salvato nelle tabelle `oddspapi_markets` e `oddspapi_outcomes`. Dopo il primo caricamento il parsing usa il catalogo locale e non richiama `/v4/markets` a ogni refresh. Le quote `/v4/odds` vengono accettate solo quando:

- la key `markets.{marketId}` esiste nel catalogo locale;
- la key `outcomes.{outcomeId}` esiste tra gli outcome di quel preciso `marketId`;
- il mercato normalizzato ha un equivalente Betfair supportato.

Ogni quota bookmaker salvata mantiene anche `oddspapi_market_id`, `oddspapi_outcome_id`, `market_name` e `selection_name`, così e' possibile auditare l'origine del dato mostrato in tabella.

## Mercati supportati

Il matching con Betfair usa codici interni stabili, non nomi localizzati. OddsPapi resta configurato in inglese (`ODDSPAPI_LANGUAGE=en`) e il portale traduce solo le label UI.

Mercati attualmente incrociati:

- `MATCH_ODDS`
- `MATCH_ODDS_HT`
- `DOUBLE_CHANCE`
- `BTTS`
- `DRAW_NO_BET`
- `CORRECT_SCORE`
- `CORRECT_SCORE_HT`
- `OVER_UNDER_05`, `15`, `25`, `35`, `45`, `55`, `65`, `75`, `85`
- `OVER_UNDER_HT_05`, `15`, `25`

I mercati OddsPapi senza equivalente Betfair verificato vengono scartati, invece di essere rimappati su mercati simili. Questo evita falsi positivi, ad esempio quote del secondo tempo o team totals mostrate come `MATCH_ODDS` o over/under full time.

## Deploy Render

1. Crea repository GitHub.
2. Carica tutti i file.
3. Render → New Web Service.
4. Collega GitHub.
5. Build command: `pip install -r requirements.txt`.
6. Start command: `gunicorn app:app`.
7. Health check: `/health`.
8. Inserisci i secrets.
9. Deploy.

## Checklist Render

- Repository GitHub collegato a Render.
- Runtime Python 3.11.
- Build command: `pip install -r requirements.txt`.
- Start command: `gunicorn app:app`.
- Health check path: `/health`.
- Environment variables configurate: `SECRET_KEY`, `ODDSPAPI_KEY`, `BETFAIR_APP_KEY` e `BETFAIR_SSOID` oppure `BETFAIR_USERNAME`, `BETFAIR_PASSWORD`, `BETFAIR_CERT`, `BETFAIR_KEY`.
- Nessun certificato o file `.env` committato.
- Refresh quote avviato solo manualmente da web o Telegram `/refresh`.

## Test

```bash
python -m pytest -q
```

## Nota tecnica

Gli adapter OddsPapi/Betfair sono isolati nei file `services/oddspapi_service.py` e `services/betfair_service.py`. Il codice non deve basarsi su `marketName` o `outcomeName` quando OddsPapi fornisce ID: il mapping deve sempre partire da `marketId` e `outcomeId` risolti contro il catalogo `/v4/markets` salvato in DB.
