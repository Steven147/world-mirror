const rootPath = './stories.json';
fetch(rootPath, { cache: 'no-store' }).then(r=>r.json()).then(({stories})=>{
  document.querySelector('#story-count').textContent=stories.length;
  document.querySelector('#world-count').textContent=new Set(stories.map(x=>x.world_id)).size;
  document.querySelector('#thread-count').textContent=stories.filter(x=>x.kind==='community-thread').length;
  if(!stories.length)return;
  document.querySelector('#stories').innerHTML=stories.slice().reverse().map(s=>`<article class="card"><span class="kind">${s.kind}</span><h3>${escapeHtml(s.title)}</h3><p>${escapeHtml(s.summary)}</p><footer>${escapeHtml(s.author.display_name)} · ${escapeHtml(s.completed_at)}</footer></article>`).join('');
}).catch(()=>{});
function escapeHtml(value){const e=document.createElement('span');e.textContent=String(value);return e.innerHTML}
