document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.datatable').forEach(table => new DataTable(table, { pageLength: 25, order: [] }));

  const form = document.getElementById('refreshForm');
  if (!form) return;

  const button = document.getElementById('refreshBtn');
  const loading = document.getElementById('loading');
  const alert = document.getElementById('refreshAlert');
  const bookmakersSelect = document.getElementById('bookmakersSelect');
  const bookmakersHelp = document.getElementById('bookmakersHelp');
  const maxBookmakers = Number(bookmakersSelect?.dataset.maxSelected || 5);

  const selectedBookmakers = () => Array.from(bookmakersSelect?.selectedOptions || []);
  const updateBookmakersState = () => {
    const count = selectedBookmakers().length;
    const valid = count > 0 && count <= maxBookmakers;
    button.disabled = !valid;
    if (bookmakersHelp) {
      bookmakersHelp.textContent = valid
        ? `Selezionati ${count}/${maxBookmakers}`
        : `Seleziona da 1 a ${maxBookmakers} bookmaker`;
      bookmakersHelp.classList.toggle('text-danger', !valid);
    }
    return valid;
  };

  bookmakersSelect?.addEventListener('change', event => {
    const selected = selectedBookmakers();
    if (selected.length > maxBookmakers) {
      event.target.options[event.target.selectedIndex].selected = false;
    }
    updateBookmakersState();
  });
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
