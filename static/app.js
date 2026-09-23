const $ = (id) => document.getElementById(id);

function renderAnalysis(data) {
  $('analysis').innerHTML = `<strong>${data.horse.name}</strong><br>${data.summary}<br><span class="muted">Dernières performances : ${(data.horse.last_runs || []).join(' · ')}</span>`;
  $('agents').innerHTML = data.agents.map(a => `<div class="agent"><div><strong>${a.name}</strong><small>${a.specialty}</small></div><b>${a.score}/100</b><p>${a.insight}</p></div>`).join('');
}
async function loadAnalysis() { const res = await fetch(`/api/analysis?horse=${encodeURIComponent($('horse').value)}`); renderAnalysis(await res.json()); }
$('horse').addEventListener('change', loadAnalysis);
$('taskForm').addEventListener('submit', async (e) => { e.preventDefault(); const task = $('task').value.trim(); if (!task) return; $('taskResult').textContent = 'Orchestration en cours…'; const res = await fetch('/api/multitask', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({task})}); const data = await res.json(); $('taskResult').innerHTML = `<strong>Plan :</strong> ${data.plan.join(' → ')}<br><strong>Sources :</strong> ${data.source_report.map(s => `${s.label} (${s.status})`).join(' · ')}<hr>${data.results.map(r => `<p><b>${r.agent}</b> — ${r.finding}</p>`).join('')}`; });
$('chatForm').addEventListener('submit', async (e) => { e.preventDefault(); const input=$('message'); const text=input.value.trim(); if(!text)return; $('messages').insertAdjacentHTML('beforeend', `<div class="bubble user">${text.replaceAll('<','&lt;')}</div>`); input.value=''; const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})}); const data=await res.json(); $('messages').insertAdjacentHTML('beforeend', `<div class="bubble bot">${data.reply}</div>`); $('messages').scrollTop=$('messages').scrollHeight; });
loadAnalysis();
