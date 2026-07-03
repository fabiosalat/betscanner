# BetScanner

Dashboard personale Flask per cercare opportunità di **surebet** e **matched betting** confrontando bookmaker italiani con Betfair Exchange.

## Cosa include

- Flask + Bootstrap + DataTables
- SQLite locale
- Refresh manuale
- OddsPapi adapter
- Betfair Exchange adapter con certificati
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

Gli adapter OddsPapi/Betfair sono isolati nei file `services/oddspapi_service.py` e `services/betfair_service.py`. Al primo test reale potrebbe servire ritoccare endpoint o naming dei mercati in base al piano/API esatta del provider.
