// 説明映像エンジン: window.VIDEO(場面データ)と window.CHARACTER(キャラ。無くてもよい)から映像を組み立てる。
// render(t) が「t 秒目の 1 コマ」を決定論で描く。再生は毎フレーム呼ぶだけ、書き出しは render-video.mjs が 1 コマずつ撮る。
// 時刻はすべて「場面の頭からの秒」で書く。場面の長さ(dur)を変えれば後ろが自動でずれる(音を足す時はナレーションの長さを dur に入れる)。
(() => {
  const V = window.VIDEO, C = window.CHARACTER || null;
  const FPS = V.fps || 30, MW = (V.map && V.map.w) || 1920, MH = (V.map && V.map.h) || 920;
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const lerp = (a, b, p) => a + (b - a) * p;
  const eOut = p => 1 - Math.pow(1 - p, 3);
  const eInOut = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
  const back = p => { const c = 1.7, c3 = c + 1; return 1 + c3 * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
  const COLOR = { g: 'var(--frame)', o: 'var(--accent)', s: 'var(--ink-soft)' };
  const NS = 'http://www.w3.org/2000/svg';
  const $ = s => document.querySelector(s);
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

  if (V.theme) for (const [k, v] of Object.entries(V.theme)) document.documentElement.style.setProperty('--' + k, v);

  // ---- 絵: 名前 → SVG。scene.js の art(その映像だけの絵)を先に、無ければ engine/icons.js の同梱アイコンを引く ----
  const ICONS = window.EXPLAINER_ICONS || {}, ART = V.art || {};
  const iconSvg = (name, where) => {
    const src = name in ART ? ART[name] : ICONS[name] && ICONS[name][1];
    if (src === undefined) {
      console.error(`${where}: 絵「${name}」がありません(engine/icons.js の名前か、scene.js の art に描く)` +
        (window.EXPLAINER_ICONS ? '' : '。index.html に engine/icons.js の行がありません'));
      return '';
    }
    return /^\s*<svg/.test(src) ? src.replace(/^\s*<svg/, '<svg class="art-svg"') : `<svg class="art-svg" viewBox="0 0 64 64">${src}</svg>`;
  };

  // ---- 時刻表(場面の頭からの秒 → 全体の秒) ----
  const T0 = V.title ? V.title.dur : 0;
  let acc = T0;
  const scenes = V.scenes.map(s => { const o = { ...s, start: acc }; acc += s.dur; return o; });
  const DUR = acc;
  const ev = { show: {}, draw: {}, packet: [], tag: {}, pulse: {}, legend: null };
  scenes.forEach(s => (s.at || []).forEach(([dt, kind, id, text, icon]) => {
    const t = s.start + dt;
    if (kind === 'packet') ev.packet.push({ t, id, text, icon });
    else if (kind === 'legend') ev.legend = t;
    else if (kind === 'pulse') (ev.pulse[id] = ev.pulse[id] || []).push(t);
    else if (ev[kind]) ev[kind][id] = t;
  }));

  // ---- 画面を組み立てる ----
  const markers = ['g', 'o', 's'].map(c => `<marker id="h${c}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill:${COLOR[c]}"/></marker>`).join('');
  document.body.insertAdjacentHTML('afterbegin', `
    <div id="stage">
      <div id="map" style="width:${MW}px;height:${MH}px">
        <svg id="svg" width="${MW}" height="${MH}" viewBox="0 0 ${MW} ${MH}"><defs>${markers}</defs></svg>
        <div id="items"></div><div id="labels"></div><div id="packets"></div>
      </div>
      <div id="legend"></div>
      <div id="cap"><span class="step"></span><span class="tx"></span></div>
      <div id="title" class="${C ? '' : 'nocat'}"><div class="t1"></div><div class="t2"></div><div class="t3"></div></div>
      <div id="cats"></div>
      <div id="frame"></div>
    </div>
    <div id="hint">クリック: 一時停止 / 再開 ・ R: 最初から</div>`);
  if (V.title) { $('#title .t1').textContent = V.title.eyebrow || ''; $('#title .t2').textContent = V.title.title || ''; $('#title .t3').innerHTML = V.title.sub || ''; }
  else $('#title').style.display = 'none';

  const items = (V.items || []).map(it => {
    const el = document.createElement('div');
    el.className = 'it ' + (it.cls || 'box'); el.id = it.id;
    Object.assign(el.style, { left: it.x + 'px', top: it.y + 'px' });
    if (it.w) el.style.width = it.w + 'px';
    if (it.h) el.style.height = it.h + 'px';
    if (el.classList.contains('art')) {
      // 絵だけの部品: w × h いっぱいに描き、html は絵の下の見出しにする
      if (!it.icon) console.error(`絵「${it.id}」: cls 'art' には icon(絵の名前)が要ります`);
      el.innerHTML = (it.icon ? iconSvg(it.icon, `絵「${it.id}」`) : '') + (it.html ? `<div class="cap">${it.html}</div>` : '');
    } else if (it.icon) {
      // 箱に絵を添える: 左(既定)か上。大きさは箱の高さから決める(iconSize で上書き)
      const top = it.iconAt === 'top', chip = el.classList.contains('chip');
      const size = it.iconSize || (chip ? 34 : top ? 72 : it.h ? Math.max(40, Math.min(it.h - 28, 120)) : 76);
      const pad = chip ? 0 : Math.round(size * .08);
      el.classList.add('has-ic', top ? 'ic-top' : 'ic-left');
      el.innerHTML = `<div class="ic" style="width:${size}px;height:${size}px;padding:${pad}px;border-radius:${Math.round(size * .22)}px">${iconSvg(it.icon, `箱「${it.id}」`)}</div>` +
        (chip ? `<span>${it.html || ''}</span>` : `<div class="tx">${it.html || ''}</div>`);
    } else el.innerHTML = it.html || '';
    $('#items').appendChild(el);
    return { el, it };
  });

  const svg = $('#svg');
  const arrows = {};
  (V.arrows || []).forEach(a => {
    const c = a.c || 'g';
    const m = document.createElementNS(NS, 'mask'); m.id = 'm-' + a.id;
    Object.entries({ maskUnits: 'userSpaceOnUse', x: -400, y: -400, width: MW + 800, height: MH + 800 }).forEach(([k, v]) => m.setAttribute(k, v));
    const mp = document.createElementNS(NS, 'path');
    Object.entries({ d: a.d, stroke: '#fff', 'stroke-width': 44, fill: 'none', pathLength: 1, 'stroke-dasharray': '1 1', 'stroke-dashoffset': 1 }).forEach(([k, v]) => mp.setAttribute(k, v));
    m.appendChild(mp); svg.querySelector('defs').appendChild(m);
    const p = document.createElementNS(NS, 'path');
    Object.entries({ d: a.d, fill: 'none', mask: `url(#m-${a.id})`, 'stroke-linecap': 'round', 'stroke-width': c === 's' ? 5 : 7 }).forEach(([k, v]) => p.setAttribute(k, v));
    p.style.stroke = COLOR[c];
    if (a.head !== false) p.setAttribute('marker-end', `url(#h${c})`);
    if (a.dash) p.setAttribute('stroke-dasharray', '12 10');
    svg.appendChild(p);
    let le = null;
    if (a.label) { le = document.createElement('div'); le.className = 'lbl ' + c; le.textContent = a.label; le.style.left = a.labelAt[0] + 'px'; le.style.top = a.labelAt[1] + 'px'; $('#labels').appendChild(le); }
    let pp = p;   // 動くラベルの通り道(短い矢印は箱の上を通す別経路を指定できる)
    if (a.packetPath) { pp = document.createElementNS(NS, 'path'); pp.setAttribute('d', a.packetPath); pp.setAttribute('fill', 'none'); svg.appendChild(pp); }
    arrows[a.id] = { a, c, mp, p, le, pp, len: pp.getTotalLength() };
  });
  const packets = ev.packet.filter(e => arrows[e.id]).map(e => {
    const A = arrows[e.id];
    const text = e.text || A.a.packet || '', icon = e.icon || A.a.packetIcon;
    const el = document.createElement('div'); el.className = 'pk ' + A.c + (icon && !text ? ' ico' : '');
    el.innerHTML = (icon ? `<span class="pi">${iconSvg(icon, `矢印「${e.id}」の動くラベル`)}</span>` : '') + esc(text);
    $('#packets').appendChild(el);
    return { ...e, A, el };
  });
  const tags = (V.tags || []).map(g => {
    const el = document.createElement('div'); el.className = 'tag ' + (g.c || 'o');
    el.innerHTML = (g.icon ? `<span class="pi">${iconSvg(g.icon, `札「${g.id}」`)}</span>` : '') + esc(g.text || '');
    el.style.left = g.x + 'px'; el.style.top = g.y + 'px'; $('#labels').appendChild(el);
    return { el, g };
  });
  if (V.legend) {
    const lg = $('#legend');
    Object.entries(V.legend.pos || { left: 60, top: 44 }).forEach(([k, v]) => { lg.style[k] = v + 'px'; });
    lg.innerHTML = V.legend.items.map(([c, label, dash]) =>
      `<div><svg width="60" height="14"><line x1="0" y1="7" x2="60" y2="7" style="stroke:${COLOR[c]}" stroke-width="${c === 's' ? 5 : 6}" ${dash ? 'stroke-dasharray="10 8"' : ''}/></svg>${label}</div>`).join('');
  } else $('#legend').style.display = 'none';
  // 文中の絵: html の中の <i data-icon="名前"></i> を、文字の大きさに合わせた絵にする
  document.querySelectorAll('#stage i[data-icon]').forEach(el => {
    const holder = el.closest('[id]');
    el.outerHTML = `<span class="ii">${iconSvg(el.dataset.icon, `「${holder ? holder.id : '?'}」の中の絵`)}</span>`;
  });

  const cats = {};
  if (C) for (const [name, file] of Object.entries(C.poses)) {
    const img = document.createElement('img'); img.className = 'cat'; img.src = C.base + file; img.alt = '';
    $('#cats').appendChild(img); cats[name] = img;
  }

  // 書き間違いの検出: 場面データが存在しない id やポーズを指すと、その部品は黙って出ないままになる。
  // console.error に出すと render-video.mjs が拾って失敗扱いにする(見落としたまま書き出さない)
  const arrowIds = new Set((V.arrows || []).map(a => a.id)), tagIds = new Set((V.tags || []).map(g => g.id));
  V.scenes.forEach((s, k) => {
    if (C && s.pose && !C.poses[s.pose]) console.error(`場面 ${k + 1}: ポーズ「${s.pose}」が character.js にありません`);
    if (!(s.dur > 0)) console.error(`場面 ${k + 1}: dur(秒)がありません`);
    (s.at || []).forEach(([dt, kind, id]) => {
      if (!['show', 'draw', 'packet', 'tag', 'legend', 'pulse'].includes(kind)) console.error(`場面 ${k + 1}: 種類「${kind}」は使えません`);
      else if ((kind === 'draw' || kind === 'packet') && !arrowIds.has(id)) console.error(`場面 ${k + 1}: 矢印「${id}」がありません`);
      else if (kind === 'tag' && !tagIds.has(id)) console.error(`場面 ${k + 1}: 札「${id}」がありません`);
      else if (kind === 'pulse' && !document.getElementById(id) && !tagIds.has(id)) console.error(`場面 ${k + 1}: 跳ねさせる「${id}」(箱・行・札)がありません`);
      else if (dt > s.dur) console.error(`場面 ${k + 1}: ${dt} 秒目の「${id || kind}」が場面の長さ ${s.dur} 秒を超えています`);
    });
  });
  if (C && V.title && V.title.pose && !C.poses[V.title.pose]) console.error(`タイトル: ポーズ「${V.title.pose}」が character.js にありません`);

  // 出し方: 箱は「ぽんと出る」、.row は「横から滑り込む」、それ以外はフェード
  const showEls = Object.entries(ev.show).map(([id, t]) => {
    const el = document.getElementById(id);
    if (!el) { console.error(`show: 箱・行「${id}」がありません`); return null; }
    return { el, t, kind: el.classList.contains('row') ? 'slide' : el.classList.contains('it') ? 'pop' : 'fade' };
  }).filter(Boolean);
  items.forEach(({ el, it }) => { if (!(it.id in ev.show) && !it.visible) el.style.opacity = 0; });
  // 跳ねる(pulse): 字幕が話している部品を、0.6 秒だけ少し大きくして目を引く。出し方の動きに掛け合わせる
  const pulseK = (id, t) => (ev.pulse[id] || []).reduce((k, at) => {
    const p = prog(t, at, at + .6);
    return p > 0 && p < 1 ? k * (1 + .14 * Math.sin(Math.PI * p)) : k;
  }, 1);
  const pulseOnly = Object.keys(ev.pulse).filter(id => !(id in ev.show) && !(V.tags || []).some(g => g.id === id))
    .map(id => document.getElementById(id)).filter(Boolean);

  function camAt(t) {
    let i = 0; scenes.forEach((s, k) => { if (t >= s.start) i = k; });
    const cur = scenes[i].cam, prev = (scenes[i - 1] || scenes[i]).cam;
    if (t < T0) return scenes[0].cam;
    const p = eInOut(prog(t, scenes[i].start, scenes[i].start + (scenes[i].camMove || 1.0)));
    return cur.map((v, k) => lerp(prev[k], v, p));
  }

  function render(t) {
    // タイトル
    const tOut = V.title ? prog(t, T0 - .5, T0 + .1) : 1;
    $('#title').style.opacity = 1 - tOut;
    $('#title').style.visibility = tOut >= 1 ? 'hidden' : 'visible';
    ['.t1', '.t2', '.t3'].forEach((s, i) => { const p = eOut(prog(t, .3 + i * .25, .8 + i * .25)); const el = $('#title ' + s); el.style.opacity = p; el.style.transform = `translateX(${(1 - p) * 60}px)`; });

    const [cx, cy, s] = camAt(t);
    $('#map').style.transform = `translate(${960 - cx * s}px,${450 - cy * s}px) scale(${s})`;

    showEls.forEach(({ el, t: at, kind }) => {
      const p = prog(t, at, at + .4), k = pulseK(el.id, t);
      el.style.opacity = p;
      el.style.transform = (kind === 'pop' ? `scale(${lerp(.8, 1, back(p))})` : kind === 'slide' ? `translateX(${(1 - eOut(p)) * 30}px)` : '') +
        (k !== 1 ? ` scale(${k})` : '');
    });
    pulseOnly.forEach(el => { const k = pulseK(el.id, t); el.style.transform = k !== 1 ? `scale(${k})` : ''; });
    Object.values(arrows).forEach(A => {
      const at = ev.draw[A.a.id];
      const p = at === undefined ? (A.a.visible ? 1 : 0) : eInOut(prog(t, at, at + .6));
      A.mp.setAttribute('stroke-dashoffset', 1 - p);
      A.p.style.visibility = p > 0 ? 'visible' : 'hidden';
      if (A.le) A.le.style.opacity = at === undefined ? p : prog(t, at + .4, at + .7);
    });
    packets.forEach(P => {
      const q = prog(t, P.t, P.t + 1.2), on = t >= P.t && t < P.t + 1.5;
      const pt = P.A.pp.getPointAtLength(P.A.len * eInOut(q));
      P.el.style.opacity = on ? Math.min(prog(t, P.t, P.t + .15), 1 - prog(t, P.t + 1.25, P.t + 1.5)) : 0;
      P.el.style.transform = `translate(${pt.x}px,${pt.y}px) translate(-50%,-50%)`;
    });
    tags.forEach(({ el, g }) => {
      const at = ev.tag[g.id], p = at === undefined ? 0 : prog(t, at, at + .35);
      el.style.opacity = p; el.style.transform = `translate(-50%,-50%) scale(${lerp(.7, 1, back(p)) * pulseK(g.id, t)})`;
    });
    $('#legend').style.opacity = ev.legend === null ? 0 : prog(t, ev.legend, ev.legend + .5);

    // 字幕とキャラ
    const inTitle = t < T0;
    let si = 0; scenes.forEach((sc, k) => { if (t >= sc.start) si = k; });
    const sc = scenes[si], next = scenes[si + 1];
    const right = sc.side === 'R';
    const capO = inTitle ? 0 : Math.min(prog(t, sc.start + .1, sc.start + .35), next ? 1 - prog(t, next.start - .15, next.start) : 1);
    const cap = $('#cap');
    cap.style.opacity = inTitle ? 0 : 1;
    const side = C ? 250 : 60;
    cap.style.left = (right ? 60 : side) + 'px'; cap.style.right = (right ? side : 60) + 'px';
    cap.querySelector('.step').textContent = sc.step || ''; cap.querySelector('.step').style.display = sc.step ? '' : 'none';
    cap.querySelector('.tx').textContent = sc.caption || '';
    cap.querySelector('.step').style.opacity = cap.querySelector('.tx').style.opacity = capO;
    cap.querySelector('.tx').style.transform = `translateY(${(1 - eOut(prog(t, sc.start + .1, sc.start + .4))) * 14}px)`;

    if (C) {
      const pose = inTitle ? (V.title.pose || Object.keys(cats)[0]) : sc.pose;
      const a = inTitle ? 0 : sc.start, lt = t - a;
      Object.entries(cats).forEach(([name, el]) => {
        if (name !== pose || !el.naturalHeight) { el.style.opacity = 0; return; }
        const H = el.naturalHeight * (inTitle ? (C.titleScale || 1.3) : (C.scale || .56));
        el.style.height = H + 'px';
        const w = H * el.naturalWidth / el.naturalHeight;
        const pop = lerp(.6, 1, back(prog(t, a, a + .35))) * (1 + Math.sin(t * 3) * .012);
        const bob = (C.bounce || []).includes(name) ? -Math.abs(Math.sin(lt * 5)) * 16 : 0;
        const x = inTitle ? 400 - w / 2 : (right ? 1780 : 140) - w / 2, y = (inTitle ? 980 : 1070) - H + bob;
        el.style.transform = `translate(${x}px,${y}px) scale(${pop})`;
        el.style.opacity = inTitle ? 1 - tOut : 1;
      });
    }
  }

  function fit() {
    const s = Math.min(innerWidth / 1920, innerHeight / 1080);
    $('#stage').style.transform = `translate(${(innerWidth - 1920 * s) / 2}px,${(innerHeight - 1080 * s) / 2}px) scale(${s})`;
  }
  addEventListener('resize', fit); fit();

  window.VIDEO_META = { fps: FPS, dur: DUR, width: 1920, height: 1080 };
  window.seek = render;
  // はみ出しの検出: 箱の文字は折り返さないので、長いと箱から出る(絵を添えると幅が減る)。
  // console.warn は render-video.mjs が「注意」として出す(フォントの違いで端末ごとに数 px 変わるため、止めはしない)
  // 縦は「中身が箱の線から 4px 以内に迫っていないか」も測る(上下中央そろえだと、上へのはみ出しは scrollHeight に出ない)
  const checkOverflow = () => items.forEach(({ el, it }) => {
    if (el.classList.contains('zone') || el.classList.contains('art')) return;
    let top = Infinity, bottom = -Infinity;
    el.querySelectorAll('*').forEach(k => { if (k.offsetParent === el && k.offsetHeight > 0) { top = Math.min(top, k.offsetTop); bottom = Math.max(bottom, k.offsetTop + k.offsetHeight); } });
    const dx = el.scrollWidth - el.clientWidth;
    const dy = Math.round(Math.max(el.scrollHeight - el.clientHeight, top === Infinity ? 0 : Math.max(4 - top, bottom - (el.clientHeight - 4))));
    if (dx > 1 || dy > 1) console.warn(`はみ出し: 箱「${it.id}」の中身が${dx > 1 ? ` 横に ${dx}px` : ''}${dy > 1 ? ` 縦に ${dy}px` : ''} はみ出しています(w / h を広げるか、言葉を短くする)`);
  });
  window.ready = Promise.all([document.fonts.ready, ...Object.values(cats).map(c => c.decode().catch(() => {}))]).then(checkOverflow);
  if (location.search.includes('render')) {
    document.body.classList.add('render'); window.ready.then(() => render(0));
  } else {
    let t0 = performance.now(), paused = false, pt = 0;
    const loop = now => { if (!paused) render(((now - t0) / 1000) % DUR); requestAnimationFrame(loop); };
    window.ready.then(() => { t0 = performance.now(); requestAnimationFrame(loop); });
    addEventListener('click', () => {
      if (paused) t0 = performance.now() - pt * 1000; else pt = ((performance.now() - t0) / 1000) % DUR;
      paused = !paused;
    });
    addEventListener('keydown', e => { if (e.key === 'r' || e.key === 'R') { t0 = performance.now(); paused = false; } });
    setTimeout(() => { $('#hint').style.opacity = 0; }, 3500);
  }
})();
