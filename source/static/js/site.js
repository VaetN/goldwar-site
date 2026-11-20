(function(){
  // Поиск по базе: индекс грузится при первом фокусе
  var q=document.getElementById('q'),box=document.getElementById('qres'),idx=null,sel=-1;
  function load(){if(idx)return Promise.resolve(idx);return fetch(q.getAttribute('data-index')||'/static/search.json').then(function(r){return r.json()}).then(function(d){idx=d.map(function(x){x.k=(x[0]+' '+(x[4]||'')).toLowerCase();return x});return idx})}
  function render(list){
    if(!list.length){box.innerHTML='<a>Ничего не найдено</a>';box.style.display='block';return}
    box.innerHTML=list.map(function(x){return '<a href="'+x[1]+'">'+(x[2]?'<img src="/static/i/'+x[2]+'" alt="" width="28" height="28" loading="lazy">':'')+'<span>'+x[0]+'</span><small>'+x[3]+'</small></a>'}).join('');
    box.style.display='block';sel=-1;
  }
  if(q){
    q.addEventListener('focus',load);
    q.addEventListener('input',function(){
      var v=q.value.trim().toLowerCase();if(v.length<2){box.style.display='none';return}
      load().then(function(d){var a=[],b=[];for(var i=0;i<d.length&&a.length<40;i++){var p=d[i].k.indexOf(v);if(p===0)a.push(d[i]);else if(p>0&&b.length<40)b.push(d[i])}render(a.concat(b).slice(0,14))});
    });
    q.addEventListener('keydown',function(e){
      var l=box.querySelectorAll('a[href]');if(!l.length)return;
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();sel=(sel+(e.key==='ArrowDown'?1:-1)+l.length)%l.length;l.forEach(function(x,i){x.classList.toggle('on',i===sel)})}
      if(e.key==='Enter'){location.href=(l[sel>=0?sel:0]).getAttribute('href')}
      if(e.key==='Escape'){box.style.display='none'}
    });
    document.addEventListener('click',function(e){if(!e.target.closest('.search'))box.style.display='none'});
  }
  // Фильтр таблиц
  document.querySelectorAll('input[data-filter]').forEach(function(inp){
    inp.addEventListener('input',function(){
      var v=inp.value.trim().toLowerCase();
      document.querySelectorAll('.tbl tbody tr').forEach(function(tr){tr.style.display=!v||tr.textContent.toLowerCase().indexOf(v)>-1?'':'none'});
    });
  });
})();
(function(){
  // Шапка и мобильная панель меняются после прокрутки
  var b=document.body,t=false;
  function on(){b.classList.toggle('scrolled',scrollY>40);t=false}
  addEventListener('scroll',function(){if(!t){t=true;requestAnimationFrame(on)}},{passive:true});on();
  // «/» и Ctrl+K – к поиску
  addEventListener('keydown',function(e){
    var q=document.getElementById('q');if(!q)return;
    var typing=/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName);
    if((e.key==='/'&&!typing)||(e.key.toLowerCase()==='k'&&(e.ctrlKey||e.metaKey))){e.preventDefault();q.focus();q.select()}
  });
  // Подсказка предмета при наведении, как в игре
  if(!matchMedia('(hover:hover)').matches)return;
  var tip=document.createElement('div');tip.className='tip';tip.setAttribute('role','tooltip');document.body.appendChild(tip);
  var cache={},cur=null,G={d:'D',c:'C',b:'B',a:'A',s:'S'};
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function draw(d){
    tip.innerHTML='<div class="tip-h">'+(d.i?'<img src="/static/i/'+d.i+'" alt="">':'')+'<div><b>'+esc(d.n)+(G[d.g]?' <span class="grade g-'+d.g+'">'+G[d.g]+'</span>':'')+'</b>'+esc(d.k)+'</div></div>'+
      (d.s.length?'<dl>'+d.s.map(function(x){return '<dt>'+esc(x[0])+'</dt><dd>'+esc(x[1])+'</dd>'}).join('')+'</dl>':'')+(d.src?'<p>Где взять: '+esc(d.src)+'</p>':'');
  }
  function place(e){var x=e.clientX+18,y=e.clientY+18,w=tip.offsetWidth,h=tip.offsetHeight;if(x+w>innerWidth-8)x=e.clientX-w-18;if(y+h>innerHeight-8)y=innerHeight-h-8;tip.style.left=x+'px';tip.style.top=y+'px'}
  document.addEventListener('mouseover',function(e){
    var a=e.target.closest&&e.target.closest('a[data-i]');if(!a||a===cur)return;cur=a;var id=a.getAttribute('data-i');
    var p=cache[id]||(cache[id]=fetch('/static/tip/'+id+'.json').then(function(r){return r.json()}));
    p.then(function(d){if(cur!==a)return;draw(d);tip.classList.add('on')}).catch(function(){});
  });
  document.addEventListener('mousemove',function(e){if(cur)place(e)});
  document.addEventListener('mouseout',function(e){if(cur&&!cur.contains(e.relatedTarget)){cur=null;tip.classList.remove('on')}});
})();
