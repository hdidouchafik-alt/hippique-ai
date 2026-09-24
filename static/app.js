const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
const setLoading = (element, text = 'Chargement…') => { element.classList.add('loading'); element.textContent = text; };

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    credentials: 'same-origin'
  });
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  return response.json();
}

function renderAnalysis(data) {
  const horse = data.horse || {};
  $('analysis').classList.remove('loading');
  $('analysis').innerHTML = `<div class="horse-hero"><div class="horse-avatar">♞</div><div><h3>${escapeHtml(horse.name)}</h3><p>${escapeHtml(data.summary)}</p></div><div class="form-score"><strong>${horse.form ?? 0}</strong><small>FORME /100</small></div></div><div class="horse-metrics"><span><b>${escapeHtml(horse.distance || '—')}</b><small>Distance</small></span><span><b>${escapeHtml(horse.surface || '—')}</b><small>Surface</small></span><span><b>${horse.speed ?? '—'}</b><small>Vitesse</small></span><span><b>${horse.stamina ?? '—'}</b><small>Endurance</small></span></div><div class="last-runs"><small>Dernières performances</small><div>${(horse.last_runs || []).map((run) => `<span>${escapeHtml(run)}</span>`).join('')}</div></div>`;
  $('agents').innerHTML = (data.agents || []).map((agent) => `<div class="agent-row"><div class="agent-symbol">✦</div><div class="agent-info"><strong>${escapeHtml(agent.name)}</strong><small>${escapeHtml(agent.specialty)}</small><div class="progress"><i style="width:${Math.min(100, Number(agent.score) || 0)}%"></i></div></div><b class="agent-score">${agent.score ?? 0}</b></div>`).join('');
}

async function loadAnalysis() { try { setLoading($('analysis')); renderAnalysis(await api(`/api/analysis?horse=${encodeURIComponent($('horse').value)}`)); } catch (error) { $('analysis').textContent = 'Impossible de charger cette analyse.'; } }

async function loadTracks() { try { const data = await api('/api/tracks'); $('trackCount').textContent = data.tracks.length; $('tracks').innerHTML = data.tracks.map((track) => `<div class="track-row"><div class="track-icon">⌖</div><div><strong>${escapeHtml(track.name)}</strong><small>${escapeHtml(track.surface)} · ${escapeHtml(track.state)}</small></div><span class="track-link">Météo →</span></div>`).join(''); } catch { $('tracks').innerHTML = '<div class="empty-state">Sources momentanément indisponibles.</div>'; } }

async function loadCapabilities() { $('capabilities').innerHTML = '<div class="empty-state">Diagnostic en cours…</div>'; try { const data = await api('/api/capabilities'); const sources = Object.entries(data.sources || {}); $('sourceCount').textContent = sources.length; $('capabilities').innerHTML = sources.map(([key, source]) => `<div class="capability-row"><span class="cap-dot ${source.status === 'available' ? 'ok' : 'warning'}"></span><div><strong>${escapeHtml(source.label)}</strong><small>${source.status === 'available' ? 'Disponible' : 'Connecteur requis'}</small></div><code>${escapeHtml(key)}</code></div>`).join(''); $('lastCollection').textContent = 'Maintenant'; } catch { $('capabilities').innerHTML = '<div class="empty-state">Diagnostic indisponible.</div>'; } }

$('horse').addEventListener('change', loadAnalysis);
$('refreshBtn').addEventListener('click', () => { loadAnalysis(); loadTracks(); loadCapabilities(); });
$('loadTracks').addEventListener('click', loadTracks);
$('loadCapabilities').addEventListener('click', loadCapabilities);
$('taskForm').addEventListener('submit', async (event) => { event.preventDefault(); const task = $('task').value.trim(); if (!task) return; const result = $('taskResult'); result.classList.remove('hidden'); result.innerHTML = '<div class="empty-state">Les agents travaillent sur votre mission…</div>'; const sources = [...document.querySelectorAll('.source-options input:checked')].map((input) => input.value); try { const data = await api('/api/multitask', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({task, sources}) }); result.innerHTML = `<div class="result-title">Mission terminée <span>${escapeHtml(data.horse || '')}</span></div><p>${escapeHtml(data.summary)}</p><div class="plan">${(data.plan || []).map((name) => `<span>${escapeHtml(name)}</span>`).join('')}</div>${Object.entries(data.collection?.results || {}).map(([name, value]) => `<div class="collection"><strong>${escapeHtml(name)}</strong><small>${value.status === 'ok' ? 'Données reçues' : 'Indisponible'}</small></div>`).join('')}<small class="disclaimer">${escapeHtml(data.disclaimer)}</small>`; } catch { result.innerHTML = '<div class="error-state">La mission n’a pas pu être exécutée.</div>'; } });
$('chatForm').addEventListener('submit', async (event) => { event.preventDefault(); const input = $('message'); const text = input.value.trim(); if (!text) return; $('messages').insertAdjacentHTML('beforeend', `<div class="bubble user">${escapeHtml(text)}</div>`); input.value = ''; const pending = document.createElement('div'); pending.className = 'bubble bot'; pending.textContent = 'Analyse en cours…'; $('messages').appendChild(pending); $('messages').scrollTop = $('messages').scrollHeight; try { const data = await api('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message:text})}); pending.innerHTML = `<strong>Assistant Hippique</strong><br>${escapeHtml(data.reply)}`; } catch { pending.textContent = 'Le service est momentanément indisponible.'; } });

$('today').textContent = new Intl.DateTimeFormat('fr-FR', {day:'numeric', month:'long', year:'numeric'}).format(new Date());
(async function init() { try { const data = await api('/api/agents'); $('agentCount').textContent = Object.keys(data.agents || {}).length; } catch { $('agentCount').textContent = '—'; } loadAnalysis(); loadTracks(); loadCapabilities(); })();
