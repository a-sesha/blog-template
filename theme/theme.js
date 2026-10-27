/* Hover / focus / tap definitions. Mark a word in a post as
     <span class="term" tabindex="0" data-title="FiLM" data-tip="Feature-wise linear modulation: ...">FiLM</span>
   and this script shows the definition in a small card. Works with the mouse, the keyboard (focus) and touch (tap); Escape closes it. */
(function () {
  const terms = document.querySelectorAll('.term[data-tip]');
  if (!terms.length) return;
  const tip = document.createElement('div');
  tip.id = 'tip'; tip.setAttribute('role', 'tooltip'); tip.style.display = 'none';
  document.body.appendChild(tip);
  let timer = null, cur = null;

  function show(el) {
    clearTimeout(timer); cur = el;
    tip.textContent = '';
    if (el.dataset.title) { const b = document.createElement('b'); b.textContent = el.dataset.title; tip.appendChild(b); }
    tip.appendChild(document.createTextNode(el.dataset.tip));          // text, never HTML: a definition cannot inject markup
    if (el.dataset.more) {
      const a = document.createElement('a'); a.href = el.dataset.more; a.textContent = ' more';
      tip.appendChild(a);
    }
    tip.style.display = 'block'; el.setAttribute('aria-describedby', 'tip');
    const r = el.getBoundingClientRect(), w = tip.offsetWidth;
    tip.style.left = Math.max(8, Math.min(r.left + scrollX, scrollX + innerWidth - w - 8)) + 'px';
    tip.style.top = (r.bottom + scrollY + 6) + 'px';
  }
  function close() { tip.style.display = 'none'; if (cur) cur.removeAttribute('aria-describedby'); cur = null; }
  function hideSoon() { timer = setTimeout(close, 160); }

  terms.forEach(el => {
    if (!el.hasAttribute('tabindex')) el.tabIndex = 0;
    el.addEventListener('mouseenter', () => show(el));
    el.addEventListener('mouseleave', hideSoon);
    el.addEventListener('focus', () => show(el));
    el.addEventListener('blur', hideSoon);
    el.addEventListener('click', e => { e.stopPropagation(); cur === el && tip.style.display === 'block' ? close() : show(el); });
  });
  tip.addEventListener('mouseenter', () => clearTimeout(timer));
  tip.addEventListener('mouseleave', hideSoon);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  document.addEventListener('click', close);
})();
