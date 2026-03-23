async function sendAction(which, state) {
  const idField = which === 'A' ? document.getElementById('deviceAId') : document.getElementById('deviceBId');
  const resultEl = which === 'A' ? document.getElementById('resultA') : document.getElementById('resultB');
  const statusEl = which === 'A' ? document.getElementById('statusA') : document.getElementById('statusB');
  const deviceId = idField.value.trim();
  if (!deviceId) {
    statusEl.textContent = ' — missing deviceId';
    return;
  }

  statusEl.textContent = ' — sending...';
  resultEl.textContent = '';

  try {
    const resp = await fetch(`/api/devices/${encodeURIComponent(deviceId)}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'setPowerState', value: { state }, clientId: 'web-app' })
    });

    const data = await resp.json().catch(() => ({}));
    statusEl.textContent = ` — ${resp.status}`;
    resultEl.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    statusEl.textContent = ' — error';
    resultEl.textContent = String(err);
  }
}

async function sendAll(state) {
  const ids = [];
  const a = document.getElementById('deviceAId').value.trim();
  const b = document.getElementById('deviceBId').value.trim();
  if (a) ids.push({ id: a, name: 'A' });
  if (b) ids.push({ id: b, name: 'B' });

  const statusAll = document.getElementById('statusAll');
  const resultAll = document.getElementById('resultAll');
  if (!ids.length) {
    statusAll.textContent = ' — no deviceIds provided';
    return;
  }

  statusAll.textContent = ' — sending...';
  resultAll.textContent = '';

  const results = {};

  await Promise.all(ids.map(async (d) => {
    try {
      const resp = await fetch(`/api/devices/${encodeURIComponent(d.id)}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'setPowerState', value: { state }, clientId: 'web-app' })
      });
      const data = await resp.json().catch(() => ({}));
      results[d.name || d.id] = { status: resp.status, data };
    } catch (err) {
      results[d.name || d.id] = { error: String(err) };
    }
  }));

  statusAll.textContent = ' — done';
  resultAll.textContent = JSON.stringify(results, null, 2);
}

document.addEventListener('DOMContentLoaded', () => {
  const onBtn = document.getElementById('allOnBtn');
  const offBtn = document.getElementById('allOffBtn');
  if (onBtn) onBtn.addEventListener('click', () => sendAll('On'));
  if (offBtn) offBtn.addEventListener('click', () => sendAll('Off'));
});
