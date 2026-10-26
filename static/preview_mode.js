'use strict';
(async()=>{
  const status=await fetch('/api/preview/status').then(r=>r.json()).catch(()=>null);
  if(!status?.synthetic)return;
  const main=document.querySelector('main')||document.body;
  const banner=document.createElement('p');banner.className='preview-banner';banner.setAttribute('role','status');
  banner.textContent='MBC AI 수업용 데모 · 합성 데이터 · 실제 아티스트·차트 관측이 아닙니다 · 유료 AI·외부 수집 꺼짐';
  main.prepend(banner);
  const notice=document.createElement('p');notice.className='preview-banner';notice.textContent='기사 작성·검수·승인은 개발 중입니다. 미승인 기사는 공개되지 않습니다.';banner.after(notice);
  const note=document.querySelector('.sidebar-note');if(note)note.textContent='합성 데이터만 표시합니다. 기사 편집·검수 기능은 개발 중입니다.';
  document.querySelectorAll('[data-collect-confirm]').forEach(b=>{b.disabled=true;b.title='Preview에서는 준비된 합성 예제곡을 선택해 주세요.';});
  const paid=document.querySelector('#news-generate-btn');if(paid)paid.hidden=true;
  const legacyExamples=document.querySelector('#news-advanced-tools');if(legacyExamples)legacyExamples.hidden=true;
  const week=document.querySelector('#week');if(week&&week.value==='2026-10-08')week.value=status.default_week;
  if(!document.body.classList.contains('page-editorial'))return;
  const me=await fetch('/api/auth/me').then(r=>r.ok?r.json():null);if(!me||!['EDITOR','ADMIN'].includes(me.role))return;
  const panel=document.createElement('section');panel.className='preview-facts-panel';
  const heading=document.createElement('h2');heading.textContent='합성 Fact Sheet 검수';
  const help=document.createElement('p');help.textContent='검수할 예제곡의 두 주간 수치를 확인하세요. 이 작업은 기사 승인과 별개입니다.';
  const load=document.createElement('button');load.type='button';load.textContent='합성 근거 3곡 확인';
  const form=document.createElement('form'),choices=document.createElement('div'),raw=document.createElement('pre'),message=document.createElement('p');
  const period=document.createElement('input');period.type='checkbox';period.required=true;
  const label=document.createElement('label');label.append(period,' 표시된 합성 두 주의 기간·단위와 비교 조건을 확인했습니다.');
  const save=document.createElement('button');save.type='submit';save.textContent='선택한 합성 곡의 검수 기록 저장';save.disabled=true;
  form.append(choices,label,save);panel.append(heading,help,load,raw,form,message);banner.after(panel);
  let draft;
  load.onclick=async()=>{try{
    const r=await fetch('/api/editorial/fact-drafts/'+status.default_week);draft=await r.json();if(!r.ok)throw Error(draft.detail);
    choices.replaceChildren();for(const t of draft.candidates.slice(0,3)){
      const row=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.value=t.candidate_id;
      row.append(check,` ${t.artist} · ${t.track_name} — 동일 예제곡·버전임을 확인`);choices.append(row);
    }
    raw.textContent=JSON.stringify({dataset_kind:draft.dataset_kind,week_previous:draft.week_previous,week_current:draft.week_current,
      source_refs:draft.source_refs,candidates:draft.candidates.slice(0,3)},null,2);save.disabled=false;
  }catch(e){message.textContent=e.message;}};
  form.onsubmit=async e=>{e.preventDefault();try{
    const ids=[...choices.querySelectorAll('input:checked')].map(x=>x.value);if(!ids.length)throw Error('검수한 예제곡을 선택해 주세요.');
    const body={draft_sha256:draft.draft_sha256,period_review:'CONFIRMED_COMPARABLE_PERIODS',
      period_evidence:'화면의 합성 CSV 기간·단위·수치와 지문을 사용자가 대조해 확인함. 실제 공식 차트의 출처 검수가 아님.',
      tracks:ids.map(candidate_id=>({candidate_id,identity_review:'CONFIRMED_SAME_SONG',version_review:'CONFIRMED_SAME_VERSION',
        editorial_category:'KPOP_RELATED_GLOBAL',evidence:'사용자가 합성 예제의 동일 곡·버전을 대조해 확인함. 실제 아티스트 분류가 아님.'}))};
    const r=await fetch('/api/editorial/fact-drafts/'+status.default_week+'/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await r.json();if(!r.ok)throw Error(result.detail);message.textContent='합성 Fact Sheet 검수 기록을 저장했습니다. 기사에는 별도 작성 출처·편집자 검수가 필요합니다.';
  }catch(e){message.textContent=e.message;}};
})();
