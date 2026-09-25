const $ = (id) => document.getElementById(id);
const escapeHtml = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const setLoading = (el, text = 'Chargement…') => { el.classList.add('loading'); el.textContent = text; };

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin'
  });
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

// ============ ANALYSE CHEVAL ============
function renderAnalysis(data) {
  const horse = data.horse || {};
  $('analysis').classList.remove('loading');
  $('analysis').innerHTML = `
    <div class="horse-hero">
      <div class="horse-avatar">♞</div>
      <div><h3>${escapeHtml(horse.name)}</h3><p>${escapeHtml(data.summary)}</p></div>
      <div class="form-score"><strong>${horse.form ?? 0}</strong><small>FORME /100</small></div>
    </div>
    <div class="horse-metrics">
      <span><b>${escapeHtml(horse.distance || '—')}</b><small>Distance</small></span>
      <span><b>${escapeHtml(horse.surface || '—')}</b><small>Surface</small></span>
      <span><b>${horse.speed ?? '—'}</b><small>Vitesse</small></span>
      <span><b>${horse.stamina ?? '—'}</b><small>Endurance</small></span>
    </div>
    <div class="last-runs">
      <small>Dernières performances</small>
      <div>${(horse.last_runs || []).map(r => `<span>${escapeHtml(r)}</span>`).join('')}</div>
    </div>
  `;
  $('agents').innerHTML = (data.agents || []).map(a => `
    <div class="agent-row">
      <div class="agent-symbol">✦</div>
      <div class="agent-info">
        <strong>${escapeHtml(a.name)}</strong>
        <small>${escapeHtml(a.specialty)}</small>
        <div class="progress"><i style="width:${Math.min(100, Number(a.score) || 0)}%"></i></div>
      </div>
      <b class="agent-score">${a.score ?? 0}</b>
    </div>
  `).join('');
}

async function loadAnalysis() {
  try {
    setLoading($('analysis'));
    renderAnalysis(await api(`/api/analysis?horse=${encodeURIComponent($('horse').value)}`));
  } catch {
    $('analysis').textContent = 'Impossible de charger cette analyse.';
  }
}

// ============ TRACKS ============
async function loadTracks() {
  try {
    const data = await api('/api/tracks');
    $('trackCount').textContent = data.tracks.length;
    $('tracks').innerHTML = data.tracks.map(t => `
      <div class="track-row">
        <div class="track-icon">⌖</div>
        <div><strong>${escapeHtml(t.name)}</strong><small>${escapeHtml(t.surface)} · ${escapeHtml(t.state)}</small></div>
        <span class="track-link">Météo →</span>
      </div>
    `).join('');
  } catch {
    $('tracks').innerHTML = '<div class="empty-state">Sources momentanément indisponibles.</div>';
  }
}

// ============ CAPABILITIES ============
async function loadCapabilities() {
  $('capabilities').innerHTML = '<div class="empty-state">Diagnostic en cours…</div>';
  try {
    const data = await api('/api/capabilities');
    const sources = Object.entries(data.sources || {});
    if ($('sourceCount')) $('sourceCount').textContent = sources.length;
    $('capabilities').innerHTML = sources.map(([key, s]) => `
      <div class="capability-row">
        <span class="cap-dot ${s.status === 'available' ? 'ok' : 'warning'}"></span>
        <div><strong>${escapeHtml(s.label)}</strong><small>${s.status === 'available' ? 'Disponible' : 'Connecteur requis'}</small></div>
        <code>${escapeHtml(key)}</code>
      </div>
    `).join('');
  } catch {
    $('capabilities').innerHTML = '<div class="empty-state">Diagnostic indisponible.</div>';
  }
}

// ============ MULTITASK ============
if ($('taskForm')) {
  $('taskForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const task = $('task').value.trim();
    if (!task) return;
    const result = $('taskResult');
    result.classList.remove('hidden');
    result.innerHTML = '<div class="empty-state">Les agents travaillent…</div>';
    try {
      const data = await api('/api/multitask', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task})
      });
      result.innerHTML = `
        <div class="result-title">Mission terminée <span>${escapeHtml(data.horse || '')}</span></div>
        <p>${escapeHtml(data.summary)}</p>
        <div class="plan">${(data.plan || []).map(n => `<span>${escapeHtml(n)}</span>`).join('')}</div>
        <small class="disclaimer">${escapeHtml(data.disclaimer || '')}</small>
      `;
    } catch {
      result.innerHTML = '<div class="error-state">La mission n\'a pas pu être exécutée.</div>';
    }
  });
}

// ============ CHAT AVEC PUTER.JS ============
if ($('chatForm')) {
  $('chatForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const input = $('message');
    const text = input.value.trim();
    if (!text) return;

    // Message utilisateur
    $('messages').insertAdjacentHTML('beforeend',
      `<div class="message user">${escapeHtml(text)}</div>`);
    input.value = '';

    // Message d'attente
    const pending = document.createElement('div');
    pending.className = 'message bot';
    pending.textContent = 'Réflexion en cours…';
    $('messages').appendChild(pending);
    $('messages').scrollTop = $('messages').scrollHeight;

    try {
      // Vérifier que Puter.js est chargé
      if (typeof puter === 'undefined') {
        pending.textContent = 'Puter.js non chargé. Rechargez la page.';
        return;
      }

      // Appel IA — AUCUNE CLÉ API NÉCESSAIRE
      const response = await puter.ai.chat(text, {
        model: 'claude-sonnet-4.5'
      });

      let reply = '';
      if (typeof response === 'string') {
        reply = response;
      } else if (response?.message?.content) {
        const content = response.message.content;
        reply = Array.isArray(content)
          ? content.map(c => c.text || '').join('')
          : String(content);
      } else if (response?.text) {
        reply = response.text;
      } else {
        reply = 'Réponse vide.';
      }

      pending.textContent = reply;
    } catch (err) {
      pending.textContent = 'Erreur : ' + (err.message || err);
    }
    $('messages').scrollTop = $('messages').scrollHeight;
  });
}

// ============ BOUTONS ============
if ($('horse')) $('horse').addEventListener('change', loadAnalysis);
if ($('loadTracks')) $('loadTracks').addEventListener('click', loadTracks);
if ($('loadCapabilities')) $('loadCapabilities').addEventListener('click', loadCapabilities);

if ($('refreshBtn')) {
  $('refreshBtn').addEventListener('click', () => {
    if ($('analysis')) loadAnalysis();
    if ($('tracks')) loadTracks();
    if ($('capabilities')) loadCapabilities();
  });
}

// ============ INIT ============
if ($('today')) {
  $('today').textContent = new Intl.DateTimeFormat('fr-FR',
    {day:'numeric', month:'long', year:'numeric'}).format(new Date());
}

(async function init() {
  try {
    const data = await api('/api/agents');
    if ($('agentCount')) $('agentCount').textContent = Object.keys(data.agents || {}).length;
  } catch {
    if ($('agentCount')) $('agentCount').textContent = '—';
  }
  if ($('analysis')) loadAnalysis();
  if ($('tracks')) loadTracks();
  if ($('capabilities')) loadCapabilities();
})();