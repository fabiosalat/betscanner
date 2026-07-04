document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.datatable').forEach(table => new DataTable(table, { pageLength: 25, order: [] }));

  const form = document.getElementById('refreshForm');
  initCalculator();
  if (!form) return;

  const button = document.getElementById('refreshBtn');
  const loading = document.getElementById('loading');
  const alert = document.getElementById('refreshAlert');
  const bookmakerPicker = document.querySelector('.bookmaker-picker');
  const bookmakerToggle = document.getElementById('bookmakersTrigger');
  const bookmakerSummary = document.getElementById('bookmakersSummary');
  const bookmakerChecks = Array.from(document.querySelectorAll('.bookmaker-option input'));
  const bookmakersSelect = document.getElementById('bookmakersSelect');
  const bookmakersHelp = document.getElementById('bookmakersHelp');
  const maxBookmakers = Number(bookmakerPicker?.dataset.maxSelected || bookmakersSelect?.dataset.maxSelected || 5);

  const selectedBookmakers = () => bookmakerChecks.filter(check => check.checked);
  const updateBookmakersState = () => {
    const count = selectedBookmakers().length;
    const valid = count > 0 && count <= maxBookmakers;
    button.disabled = !valid;
    bookmakerSummary.textContent = count
      ? selectedBookmakers().map(check => check.value).join(', ')
      : 'Seleziona bookmaker';
    bookmakersSelect?.querySelectorAll('option').forEach(option => {
      option.selected = bookmakerChecks.some(check => check.checked && check.value === option.value);
    });
    if (bookmakersHelp) {
      bookmakersHelp.textContent = valid
        ? `Selezionati ${count}/${maxBookmakers}`
        : `Seleziona da 1 a ${maxBookmakers} bookmaker`;
      bookmakersHelp.classList.toggle('text-danger', !valid);
    }
    return valid;
  };

  bookmakerToggle?.addEventListener('click', () => {
    const open = bookmakerPicker.classList.toggle('is-open');
    bookmakerToggle.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', event => {
    if (!bookmakerPicker?.contains(event.target)) {
      bookmakerPicker?.classList.remove('is-open');
      bookmakerToggle?.setAttribute('aria-expanded', 'false');
    }
  });
  bookmakerChecks.forEach(check => check.addEventListener('change', event => {
    const selected = selectedBookmakers();
    if (selected.length > maxBookmakers) {
      event.target.checked = false;
    }
    updateBookmakersState();
  }));
  updateBookmakersState();

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!updateBookmakersState()) return;
    button.disabled = true;
    loading.classList.remove('d-none');
    alert.className = 'alert d-none';

    try {
      const response = await fetch(`${form.action}?json=1`, {
        method: form.method || 'POST',
        headers: { Accept: 'application/json' },
        body: new FormData(form),
      });
      const payload = await response.json();
      console[response.ok && payload.status !== 'error' ? 'info' : 'error']('BetScanner refresh result', payload);
      alert.textContent = payload.message || 'Refresh completato';
      alert.className = `alert ${payload.status === 'error' ? 'alert-danger' : payload.status === 'rate_limited' ? 'alert-warning' : 'alert-info'}`;
      if (response.ok && payload.status === 'ok') {
        window.location.reload();
      }
    } catch (error) {
      console.error('BetScanner refresh failed', error);
      alert.textContent = error.message || 'Errore durante il refresh';
      alert.className = 'alert alert-danger';
    } finally {
      button.disabled = false;
      loading.classList.add('d-none');
    }
  });
});

function initCalculator() {
  const dialog = document.getElementById('calculatorDialog');
  if (!dialog) return;

  const fields = {
    meta: document.getElementById('calcMeta'),
    event: document.getElementById('calcEvent'),
    market: document.getElementById('calcMarket'),
    stake: document.getElementById('calcStake'),
    backOdd: document.getElementById('calcBackOdd'),
    layOdd: document.getElementById('calcLayOdd'),
    layStake: document.getElementById('calcLayStake'),
    liability: document.getElementById('calcLiability'),
    backWin: document.getElementById('calcBackWin'),
    layWin: document.getElementById('calcLayWin'),
    net: document.getElementById('calcNet'),
  };
  let commission = 0.02;
  const money = value => Number.isFinite(value) ? `${value.toFixed(2)} €` : '-';

  const recalculate = () => {
    const stake = Number(fields.stake.value);
    const back = Number(fields.backOdd.value);
    const lay = Number(fields.layOdd.value);
    if (stake <= 0 || back <= 1 || lay <= commission) {
      [fields.layStake, fields.liability, fields.backWin, fields.layWin, fields.net].forEach(field => { field.textContent = '-'; });
      return;
    }

    const layStake = stake * back / (lay - commission);
    const liability = layStake * (lay - 1);
    const backWin = stake * (back - 1) - liability;
    const layWin = layStake * (1 - commission) - stake;
    const net = Math.min(backWin, layWin);
    fields.layStake.textContent = money(layStake);
    fields.liability.textContent = money(liability);
    fields.backWin.textContent = money(backWin);
    fields.layWin.textContent = money(layWin);
    fields.net.textContent = money(net);
    fields.net.classList.toggle('text-success', net >= 0);
    fields.net.classList.toggle('text-danger', net < 0);
  };

  [fields.stake, fields.backOdd, fields.layOdd].forEach(field => field.addEventListener('input', recalculate));
  document.querySelectorAll('.opportunity-row').forEach(row => row.addEventListener('click', event => {
    if (event.target.closest('a')) return;
    commission = Number(row.dataset.commission || 0.02);
    fields.meta.textContent = `${row.dataset.type === 'surebet' ? 'Surebet' : 'Matched'} - ${row.dataset.bookmaker}`;
    fields.event.textContent = row.dataset.event || '';
    fields.market.textContent = `${row.dataset.market || ''} / ${row.dataset.selection || ''}`;
    fields.stake.value = row.dataset.stake || '100';
    fields.backOdd.value = row.dataset.backOdd || '';
    fields.layOdd.value = row.dataset.layOdd || '';
    recalculate();
    dialog.showModal();
  }));
}
