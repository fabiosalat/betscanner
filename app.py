import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request, jsonify, send_file
from openpyxl import Workbook
from config import SECRET_KEY, MAX_RESULTS, missing_api_credentials
from database.init_db import init_db
from database.repository import Repository
from services.scanner import QuoteScanner

Path('logs').mkdir(exist_ok=True)
handler = RotatingFileHandler('logs/betscanner.log', maxBytes=10_000_000, backupCount=5)
logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler()])

app = Flask(__name__)
app.secret_key = SECRET_KEY
init_db()
repo = Repository()

@app.route('/')
def index():
    return render_template('index.html',
        surebets=repo.top_opportunities('surebet', MAX_RESULTS),
        matched=repo.top_opportunities('matched', MAX_RESULTS),
        last_refresh=repo.get_last_refresh(),
        counts=repo.counts(),
        bookmakers=repo.top_bookmakers(10),
        missing_credentials=missing_api_credentials()
    )

@app.route('/refresh', methods=['POST', 'GET'])
def refresh():
    missing = missing_api_credentials()
    if missing:
        result = {"status": "missing_credentials", "message": "Credenziali API mancanti", "missing": missing}
        if request.headers.get('accept') == 'application/json' or request.args.get('json') == '1':
            return jsonify(result), 200
        return render_template('index.html',
            surebets=repo.top_opportunities('surebet', MAX_RESULTS),
            matched=repo.top_opportunities('matched', MAX_RESULTS),
            last_refresh=repo.get_last_refresh(),
            counts=repo.counts(),
            bookmakers=repo.top_bookmakers(10),
            missing_credentials=missing,
            refresh_result=result
        ), 200
    result = QuoteScanner().refresh()
    if request.headers.get('accept') == 'application/json' or request.args.get('json') == '1':
        return jsonify(result)
    return redirect(url_for('index'))

@app.route('/search')
def search():
    q = request.args.get('q', '')
    rows = repo.search_opportunities(q, MAX_RESULTS) if q else []
    return render_template('search.html', query=q, rows=rows, last_refresh=repo.get_last_refresh())

@app.route('/event/<int:event_id>')
def event_detail(event_id):
    return render_template('event.html', event=repo.get_event(event_id), odds=repo.get_event_odds(event_id), betfair=repo.get_event_betfair_odds(event_id))

@app.route('/export/<kind>')
def export(kind):
    if kind not in {'surebet', 'matched'}:
        return 'Tipo export non valido', 400
    rows = [dict(r) for r in repo.top_opportunities(kind, 500)]
    path = Path('instance') / f'{kind}.xlsx'
    workbook = Workbook()
    sheet = workbook.active
    if rows:
        headers = list(rows[0])
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
    workbook.save(path)
    return send_file(path, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)
