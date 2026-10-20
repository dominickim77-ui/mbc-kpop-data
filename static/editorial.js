'use strict';
const $ = s => document.querySelector(s);
let me, selected = null;
async function api(path, method='GET', data) {
  const r = await fetch(path,{method,headers:{'Content-Type':'application/json'},...(data!==undefined?{body:JSON.stringify(data)}:{})});
  const result = await r.json();
  if(!r.ok) throw new Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
  return result;
}
async function run(fn){try{$('#message').textContent='';await fn();}catch(e){$('#message').textContent=e.message;}}
function evidenceText(evidence) {
  const f=evidence?.facts;
  if(!f)return '';
  const lines=[`지역: ${f.region}`,`전주: ${f.week_previous.start} ~ ${f.week_previous.end}`,`금주: ${f.week_current.start} ~ ${f.week_current.end}`,
    `차트 범위: Spotify ${f.chart_cutoffs.spotify_top_n}곡 / YouTube ${f.chart_cutoffs.youtube_top_n}곡`];
  for(const t of f.analysis_tracks){
    lines.push('',`${t.artist} — ${t.track_name}`,
      `Spotify 순위 ${t.spotify.previous_rank} → ${t.spotify.current_rank}`,
      `주간 스트리밍 ${t.spotify.previous_week_streams.toLocaleString()} → ${t.spotify.current_week_streams.toLocaleString()} (${t.spotify.streams_change_pct}%)`,
      `YouTube 순위 ${t.youtube.previous_rank} → ${t.youtube.current_rank}`,
      `주간 곡 조회수 ${t.youtube.previous_week_views.toLocaleString()} → ${t.youtube.current_week_views.toLocaleString()} (${t.youtube.views_change_pct}%)`);
  }
  lines.push('','출처',...Object.values(f.sources),'','주의사항',...f.cautions);
  return lines.join('\n');
}
function showArticle(row){
  selected=row; $('#title').value=row?.title||''; $('#body').value=row?.body||''; $('#week').value=row?.week_end||'2026-10-08';
  $('#status').textContent=row?`${row.status} · 기사 ${row.id} · 버전 ${row.version}`:'새 초안';
  $('#evidence').textContent=row?evidenceText(row.evidence):'';
  $('#fresh').textContent=row?(row.evidence_current?'현재 근거와 일치':'근거 변경 또는 검증 실패 — 다시 저장하고 검수 요청 필요'):'';
  $('#history').textContent=row?[
    ...(row.reviews||[]).map(r=>`검수 #${r.id} · 버전 ${r.version} · 검수자 ${r.reviewer_id} · ${r.created_at} UTC\n${r.decision} — ${r.comment}`),
    ...(row.revisions||[]).map(r=>{const s=JSON.parse(r.snapshot);return `수정 버전 ${r.version} · 작성자 ${r.actor_id} · ${r.created_at} UTC\n${s.title}\n${s.body}`;})
  ].join('\n\n'):'';
  const owner=!row||row.author_id===me.id;
  ['#title','#body','#week','#save','#preview'].forEach(s=>$(s).disabled=!owner);
  $('#submit').disabled=!row||!owner||!['DRAFT','REVISED'].includes(row.status);
  $('#withdraw').disabled=!row||row.status==='WITHDRAWN';
  $('#review-form').hidden=!row||!['EDITOR','ADMIN'].includes(me.role)||row.author_id===me.id||row.status!=='PENDING_REVIEW';
  ['numbers','period_units','no_unsupported_claims','sources'].forEach(k=>$('#'+k).checked=false); $('#comment').value='';
}
async function openArticle(id){showArticle(await api('/api/editorial/articles/'+id));}
async function refresh(){
  const published=await api('/api/editorial/published'); $('#published').replaceChildren();
  if(!published.length) $('#published').textContent='승인된 기사가 없습니다.';
  for(const row of published){const el=document.createElement('article'), h=document.createElement('h3'), p=document.createElement('pre');h.textContent=row.title;p.textContent=row.body;el.append(h,p);$('#published').append(el);}
  if(me.role==='READER') return;
  $('#workspace').hidden=false; $('#list').replaceChildren();
  for(const row of await api('/api/editorial/articles')){const b=document.createElement('button');b.textContent=`${row.status} · ${row.title} · v${row.version}`;b.onclick=()=>run(()=>openArticle(row.id));$('#list').append(b);}
}
$('#new').onclick=()=>showArticle(null);
$('#article-form').onsubmit=e=>{e.preventDefault();run(async()=>{
  const data={title:$('#title').value,body:$('#body').value,week_end:$('#week').value};
  if(selected)data.expected_version=selected.version;
  const row=await api('/api/editorial/articles'+(selected?'/'+selected.id:''),selected?'PUT':'POST',data);
  await refresh();await openArticle(row.id);
});};
$('#facts').onclick=()=>run(async()=>{const data=await api('/api/editorial/facts/'+$('#week').value);$('#evidence').textContent=evidenceText(data.evidence);});
$('#preview').onclick=()=>run(async()=>{const r=await api('/api/news/preview?week_end='+$('#week').value);$('#body').value=r.article;});
for(const action of ['submit','withdraw']) $('#'+action).onclick=()=>run(async()=>{if(!selected)return;await api(`/api/editorial/articles/${selected.id}/${action}`,'POST',{expected_version:selected.version});await refresh();await openArticle(selected.id);});
$('#review-form').onsubmit=e=>{e.preventDefault();run(async()=>{
  const checklist={};['numbers','period_units','no_unsupported_claims','sources'].forEach(k=>checklist[k]=$('#'+k).checked);
  const result=await api(`/api/editorial/articles/${selected.id}/review`,'POST',{expected_version:selected.version,evidence_hash:selected.evidence_hash,checklist,comment:$('#comment').value,decision:e.submitter.value});
  await refresh();await openArticle(selected.id);if(result.approval_blocked)$('#message').textContent='체크리스트가 모두 통과하지 않아 서버에서 승인을 차단하고 보류로 기록했습니다.';
});};
run(async()=>{
  me=await api('/api/auth/me');await refresh();showArticle(null);
  if(me.role==='ADMIN'){
    $('#admin').hidden=false;
    for(const user of await api('/api/auth/users')){
      const line=document.createElement('div'),label=document.createElement('span'),select=document.createElement('select'),button=document.createElement('button');
      label.textContent=user.username+' · '+user.role;
      for(const role of ['READER','JOURNALIST','EDITOR','ADMIN']){const opt=document.createElement('option');opt.value=role;opt.textContent=role;opt.selected=role===user.role;select.append(opt);}
      button.textContent='역할 변경';button.onclick=()=>run(async()=>{await api(`/api/auth/users/${user.id}/role`,'PUT',{role:select.value});location.reload();});
      line.append(label,select,button);$('#users').append(line);
    }
  }
});
