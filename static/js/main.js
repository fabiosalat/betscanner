document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.datatable').forEach(table => new DataTable(table, { pageLength: 25, order: [] }));

  const form = document.getElementById('refreshForm');
  if (!form) return;

  const button = document.getElementById('refreshBtn');
  const loading = document.getElementById('loading');
  const alert = document.getElementById('refreshAlert');

  form.addEventListener('submit', async event => {
    event.preventDefault();
    button.disabled = true;
    loading.classList.remove('d-none');
    alert.className = 'alert d-none';

    try {
      const response = await fetch(`${form.action}?json=1`, {
        method: form.method || 'POST',
        headers: { Accept: 'application/json' },
      });
      const payload = await response.json();
      console[response.ok && payload.status !== 'error' ? 'info' : 'error']('BetScanner refresh result', payload);
      alert.textContent = payload.message || 'Refresh completato';
      alert.className = `alert ${payload.status === 'error' ? 'alert-danger' : payload.status === 'rate_limited' ? 'alert-warning' : 'alert-info'}`;
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
