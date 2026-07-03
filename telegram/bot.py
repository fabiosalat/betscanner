import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, MAX_RESULTS
from database.init_db import init_db
from database.repository import Repository
from services.scanner import QuoteScanner

repo = Repository()

def allowed(update: Update) -> bool:
    if not TELEGRAM_CHAT_ID:
        return True
    return str(update.effective_chat.id) == str(TELEGRAM_CHAT_ID)

async def deny(update: Update):
    await update.message.reply_text("Accesso non autorizzato.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    await update.message.reply_text("BetScanner pronto. Comandi: /refresh /surebet /matched /search <testo> /stats")

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    await update.message.reply_text("Refresh quote in corso...")
    result = QuoteScanner().refresh()
    await update.message.reply_text(f"Refresh: {result.get('status')}\nEventi: {result.get('events')}\nAPI calls: {result.get('api_calls')}\nDurata: {result.get('duration'):.2f}s\n{result.get('message','')}")

async def surebet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    book = " ".join(context.args).lower().strip()
    rows = repo.top_opportunities('surebet', MAX_RESULTS)
    if book:
        rows = [r for r in rows if book in r['bookmaker'].lower()]
    await update.message.reply_text(format_rows(rows, 'roi', 'ROI'))

async def matched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    book = " ".join(context.args).lower().strip()
    rows = repo.top_opportunities('matched', MAX_RESULTS)
    if book:
        rows = [r for r in rows if book in r['bookmaker'].lower()]
    await update.message.reply_text(format_rows(rows, 'qualifying_loss', 'QL'))

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    q = " ".join(context.args).strip()
    if not q:
        return await update.message.reply_text("Uso: /search juventus")
    rows = repo.search_opportunities(q, MAX_RESULTS)
    await update.message.reply_text(format_rows(rows, 'roi', 'Score'))

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update): return await deny(update)
    counts = repo.counts(); last = repo.get_last_refresh()
    await update.message.reply_text(f"Eventi: {counts['events']}\nSurebet: {counts['surebets']}\nMatched: {counts['matched']}\nUltimo refresh: {last['timestamp'] if last else 'Mai'}")

def format_rows(rows, metric_key, metric_label):
    if not rows:
        return "Nessun risultato."
    lines=[]
    for i,r in enumerate(rows[:25],1):
        lines.append(f"{i}) {r['event_name']}\n{r['bookmaker']} · {r['market']} · {r['selection']}\nBack {r['back_odd']} / Lay {r['lay_odd']} · {metric_label}: {r[metric_key]}\n")
    text="\n".join(lines)
    return text[:3900]

def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN non configurato")
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('refresh', refresh))
    app.add_handler(CommandHandler('surebet', surebet))
    app.add_handler(CommandHandler('matched', matched))
    app.add_handler(CommandHandler('search', search))
    app.add_handler(CommandHandler('stats', stats))
    app.run_polling()

if __name__ == '__main__':
    main()
