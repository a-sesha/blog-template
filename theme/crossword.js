/* Crossword player. build.py turns {{crossword file.ipuz}} into <div class="crossword"> holding the puzzle as JSON; this script builds
   the board, the clue lists and the toolbar from it. No dependencies. Keyboard: letters type, arrows move, Space or Enter turns the
   direction, Tab and Shift+Tab change clue, Backspace deletes, Escape leaves the board. Progress and the timer are kept in this
   browser's localStorage only (nothing is sent anywhere). */
(function () {
  'use strict';
  if (window.blogCrosswordLoaded) return;
  window.blogCrosswordLoaded = true;

  var SVGNS = 'http://www.w3.org/2000/svg', CELL = 40;

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function svg(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function clock(s) {
    var m = Math.floor(s / 60), r = s % 60;
    return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r;
  }
  function store(key, value) {                                  // localStorage can be missing or full; the puzzle works without it
    try {
      if (value === undefined) return JSON.parse(localStorage.getItem(key));
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { /* ignore */ }
    return null;
  }

  function init(root) {
    var data;
    try { data = JSON.parse(root.querySelector('script.crossword-data').textContent); } catch (e) { return; }
    var W = data.w, H = data.h, sol = data.grid;                // sol[r].charAt(c): a letter, or '#' for a block
    var isBlock = function (r, c) { return sol[r].charAt(c) === '#'; };

    /* ---- words and numbers: the same counting build.py checks the clues against ---- */
    var numberAt = {}, words = [], wordAt = { across: {}, down: {} }, n = 0, r, c, k, end;
    function addWord(dir, num, cells, clue) {
      var word = { n: num, dir: dir, cells: cells, clue: clue, idx: words.length };
      words.push(word);
      cells.forEach(function (p) { wordAt[dir][p[0] * W + p[1]] = word; });
    }
    var clueText = { across: {}, down: {} };
    data.across.forEach(function (x) { clueText.across[x[0]] = x[1]; });
    data.down.forEach(function (x) { clueText.down[x[0]] = x[1]; });
    var down = [];
    for (r = 0; r < H; r++) {
      for (c = 0; c < W; c++) {
        if (isBlock(r, c)) continue;
        var sa = (c === 0 || isBlock(r, c - 1)) && c + 1 < W && !isBlock(r, c + 1);
        var sd = (r === 0 || isBlock(r - 1, c)) && r + 1 < H && !isBlock(r + 1, c);
        if (sa || sd) numberAt[r * W + c] = ++n;
        if (sa) {
          for (end = c; end < W && !isBlock(r, end); end++) { /* find the end */ }
          var cells = [];
          for (k = c; k < end; k++) cells.push([r, k]);
          addWord('across', n, cells, clueText.across[n]);
        }
        if (sd) {
          for (end = r; end < H && !isBlock(end, c); end++) { /* find the end */ }
          var dcells = [];
          for (k = r; k < end; k++) dcells.push([k, c]);
          down.push(['down', n, dcells, clueText.down[n]]);
        }
      }
    }
    down.forEach(function (d) { addWord(d[0], d[1], d[2], d[3]); });   // all Across words first, then all Down, like the clue lists

    /* ---- state ---- */
    var letters = [], flags = [];                               // flags: '' | 'bad' (failed a check) | 'rev' (revealed)
    for (k = 0; k < W * H; k++) { letters.push(''); flags.push(''); }
    var cur = { r: 0, c: 0, dir: 'across' }, elapsed = 0, running = false, paused = false, done = false, ticker = null, started = false;
    var key = 'blog-crossword:' + data.id;

    function load() {
      var s = store(key);
      if (!s || typeof s.l !== 'string' || s.l.length !== W * H) return;
      for (var i = 0; i < W * H; i++) {
        var ch = s.l.charAt(i);
        letters[i] = ch === ' ' ? '' : ch;
        flags[i] = s.f && s.f.charAt(i) === 'r' ? 'rev' : '';
      }
      elapsed = typeof s.t === 'number' ? s.t : 0;
      done = !!s.d;
      started = elapsed > 0 || letters.some(Boolean);
    }
    function save() {
      store(key, { l: letters.map(function (x) { return x || ' '; }).join(''), f: flags.map(function (x) { return x === 'rev' ? 'r' : '.'; }).join(''), t: elapsed, d: done });
    }

    /* ---- the page ---- */
    var bar = el('div', 'cw-bar'), timerBtn = el('button', 'btn cw-timer'), timeText = el('span', 'cw-time', '00:00');
    timerBtn.type = 'button';
    var playIcon = el('span', 'cw-icon');
    timerBtn.appendChild(playIcon); timerBtn.appendChild(timeText);
    bar.appendChild(timerBtn);

    function menu(label, actions) {
      var d = el('details', 'cw-menu'), s = el('summary', 'btn', label), box = el('div', 'cw-menu-items');
      actions.forEach(function (a) {
        var b = el('button', 'btn', a[0]);
        b.type = 'button';
        b.addEventListener('click', function () { a[1](); d.open = false; focusBoard(); });
        box.appendChild(b);
      });
      d.appendChild(s); d.appendChild(box);
      return d;
    }
    bar.appendChild(menu('Check', [['Square', function () { check('square'); }], ['Word', function () { check('word'); }], ['Puzzle', function () { check('puzzle'); }]]));
    bar.appendChild(menu('Reveal', [['Square', function () { reveal('square'); }], ['Word', function () { reveal('word'); }], ['Puzzle', function () { reveal('puzzle'); }]]));
    var clear = el('button', 'btn', 'Clear');
    clear.type = 'button';
    bar.appendChild(clear);
    var stamp = el('span', 'cw-stamp', 'Solved');
    stamp.setAttribute('aria-hidden', 'true');
    bar.appendChild(stamp);

    var main = el('div', 'cw-main'), board = el('div', 'cw-board');
    var banner = el('div', 'cw-banner'), bannerNum = el('b'), bannerText = el('span');
    banner.setAttribute('role', 'status');
    banner.appendChild(bannerNum); banner.appendChild(bannerText);
    var frame = el('div', 'cw-frame');
    var grid = svg('svg', { viewBox: '0 0 ' + W * CELL + ' ' + H * CELL, 'class': 'cw-grid', 'aria-hidden': 'true', focusable: 'false' });
    var cellEls = [];
    for (r = 0; r < H; r++) {
      for (c = 0; c < W; c++) {
        var g = svg('g', { 'class': 'cw-c' });
        var x = c * CELL, y = r * CELL;
        g.style.setProperty('--d', (r + c) * 60 + 'ms');
        g.appendChild(svg('rect', { x: x, y: y, width: CELL, height: CELL, 'class': 'cw-sq' }));
        if (isBlock(r, c)) { g.setAttribute('class', 'cw-c cw-block'); grid.appendChild(g); cellEls.push(g); continue; }
        if ((data.circles || []).some(function (p) { return p[0] === r && p[1] === c; })) g.appendChild(svg('circle', { cx: x + CELL / 2, cy: y + CELL / 2, r: CELL / 2 - 1.5, 'class': 'cw-circle' }));
        if (numberAt[r * W + c]) { var nt = svg('text', { x: x + 3, y: y + 11, 'class': 'cw-num' }); nt.textContent = numberAt[r * W + c]; g.appendChild(nt); }
        var lt = svg('text', { x: x + CELL / 2, y: y + CELL - 9, 'class': 'cw-let', 'text-anchor': 'middle' });
        g.appendChild(lt);
        g.appendChild(svg('line', { x1: x + 2, y1: y + CELL - 2, x2: x + CELL - 2, y2: y + 2, 'class': 'cw-slash' }));
        g.appendChild(svg('path', { d: 'M' + (x + CELL - 11) + ' ' + y + 'h11v11z', 'class': 'cw-revmark' }));
        (function (rr, cc) { g.addEventListener('mousedown', function (e) { e.preventDefault(); clickCell(rr, cc); }); })(r, c);
        grid.appendChild(g);
        cellEls.push(g);
      }
    }
    var input = el('input', 'cw-input');
    input.type = 'text'; input.autocomplete = 'off'; input.spellcheck = false;
    input.setAttribute('autocapitalize', 'characters'); input.setAttribute('autocorrect', 'off');
    input.setAttribute('aria-label', 'Crossword: type your answer. Arrow keys move, Tab changes clue, Space turns the direction.');
    frame.appendChild(grid); frame.appendChild(input);
    var pausedNote = el('div', 'cw-pausednote', 'Paused. Press the timer to continue.');
    frame.appendChild(pausedNote);
    board.appendChild(banner); board.appendChild(frame);

    var clues = el('div', 'cw-clues'), clueEls = [];
    ['across', 'down'].forEach(function (dir) {
      var sec = el('section', 'cw-list'), h = el('h3', null, dir === 'across' ? 'Across' : 'Down'), ol = el('ol');
      words.filter(function (w) { return w.dir === dir; }).forEach(function (w) {
        var li = el('li'), b = el('button', 'cw-clue'), nn = el('span', 'cw-cn', String(w.n)), tx = el('span', null, w.clue || '');
        b.type = 'button'; b.appendChild(nn); b.appendChild(tx);
        b.addEventListener('click', function () { selectWord(w); focusBoard(); });
        li.appendChild(b); ol.appendChild(li);
        clueEls[w.idx] = b;
      });
      sec.appendChild(h); sec.appendChild(ol); clues.appendChild(sec);
    });
    main.appendChild(board); main.appendChild(clues);
    var status = el('p', 'cw-status');
    status.setAttribute('role', 'status');
    root.appendChild(bar); root.appendChild(main); root.appendChild(status);

    /* ---- helpers ---- */
    function idx(rr, cc) { return rr * W + cc; }
    function curWord() { return wordAt[cur.dir][idx(cur.r, cur.c)] || wordAt[cur.dir === 'across' ? 'down' : 'across'][idx(cur.r, cur.c)]; }
    function fixDir() { if (!wordAt[cur.dir][idx(cur.r, cur.c)]) cur.dir = cur.dir === 'across' ? 'down' : 'across'; }
    function other() { return cur.dir === 'across' ? 'down' : 'across'; }
    function focusBoard() { input.focus({ preventScroll: true }); }
    function firstEmpty(w) {
      for (var i = 0; i < w.cells.length; i++) if (!letters[idx(w.cells[i][0], w.cells[i][1])]) return w.cells[i];
      return w.cells[0];
    }
    function selectWord(w) {
      var p = firstEmpty(w);
      cur.r = p[0]; cur.c = p[1]; cur.dir = w.dir;
      paint();
    }
    function clickCell(rr, cc) {
      if (paused) return;
      begin();
      if (cur.r === rr && cur.c === cc) { if (wordAt[other()][idx(rr, cc)]) cur.dir = other(); }
      else { cur.r = rr; cur.c = cc; fixDir(); }
      focusBoard(); paint();
    }
    function step(dr, dc, from) {
      var rr = from.r + dr, cc = from.c + dc;
      while (rr >= 0 && rr < H && cc >= 0 && cc < W) {
        if (!isBlock(rr, cc)) return { r: rr, c: cc };
        rr += dr; cc += dc;
      }
      return null;
    }
    function nextInWord(delta) {
      var w = curWord(), i = -1;
      for (k = 0; k < w.cells.length; k++) if (w.cells[k][0] === cur.r && w.cells[k][1] === cur.c) i = k;
      var j = i + delta;
      return j >= 0 && j < w.cells.length ? w.cells[j] : null;
    }
    function allCells() {
      var out = [];
      for (var rr = 0; rr < H; rr++) for (var cc = 0; cc < W; cc++) if (!isBlock(rr, cc)) out.push([rr, cc]);
      return out;
    }
    function scopeCells(scope) {
      if (scope === 'square') return [[cur.r, cur.c]];
      if (scope === 'word') return curWord().cells;
      return allCells();
    }
    function solved() {
      return allCells().every(function (p) { return letters[idx(p[0], p[1])] === sol[p[0]].charAt(p[1]); });
    }

    /* ---- timer ---- */
    function showTime() { timeText.textContent = clock(elapsed); }
    function tick() { elapsed++; showTime(); if (elapsed % 5 === 0) save(); }
    function setRunning(on) {
      if (on === running) return;
      running = on;
      if (on) ticker = setInterval(tick, 1000); else { clearInterval(ticker); ticker = null; }
      playIcon.className = 'cw-icon ' + (on ? 'cw-pause' : 'cw-play');
      timerBtn.setAttribute('aria-label', (on ? 'Pause the timer, ' : 'Resume the timer, ') + clock(elapsed));
    }
    function begin() { started = true; if (!done && !paused) setRunning(true); }
    function setPaused(p) {
      paused = p; root.classList.toggle('cw-paused', p);
      setRunning(!p && started && !done);
      if (p) input.blur(); else focusBoard();
      save();
    }
    timerBtn.addEventListener('click', function () {
      if (done) return;
      if (!started) { begin(); focusBoard(); return; }
      setPaused(!paused);
    });
    document.addEventListener('visibilitychange', function () { if (document.hidden && running) { setRunning(false); } else if (!document.hidden && started && !paused && !done) setRunning(true); });
    window.addEventListener('pagehide', save);

    /* ---- actions ---- */
    function setLetter(rr, cc, ch, flag) {
      letters[idx(rr, cc)] = ch;
      flags[idx(rr, cc)] = flag || '';
    }
    function type(ch) {
      if (paused || done) return;
      begin();
      if (!wordAt[cur.dir][idx(cur.r, cur.c)]) fixDir();
      setLetter(cur.r, cur.c, ch);
      var nx = nextInWord(1);
      if (nx) { cur.r = nx[0]; cur.c = nx[1]; }
      afterEdit();
    }
    function backspace() {
      if (paused || done) return;
      if (letters[idx(cur.r, cur.c)]) setLetter(cur.r, cur.c, '');
      else {
        var pv = nextInWord(-1);
        if (pv) { cur.r = pv[0]; cur.c = pv[1]; setLetter(cur.r, cur.c, ''); }
      }
      afterEdit();
    }
    function arrow(dir, dr, dc) {
      if (paused) return;
      if (cur.dir !== dir && wordAt[dir][idx(cur.r, cur.c)]) { cur.dir = dir; paint(); return; }
      var to = step(dr, dc, cur);
      if (to) { cur.r = to.r; cur.c = to.c; fixDir(); }
      paint();
    }
    function nextClue(delta) {
      if (paused) return;
      var w = curWord(), j = (w.idx + delta + words.length) % words.length;
      selectWord(words[j]);
    }
    function check(scope) {
      scopeCells(scope).forEach(function (p) {
        var i = idx(p[0], p[1]);
        if (letters[i] && letters[i] !== sol[p[0]].charAt(p[1]) && flags[i] !== 'rev') flags[i] = 'bad';
      });
      var bad = scopeCells(scope).filter(function (p) { return flags[idx(p[0], p[1])] === 'bad'; }).length;
      announce(bad ? bad + (bad === 1 ? ' square is' : ' squares are') + ' wrong.' : 'No mistakes found.');
      paint(); save();
    }
    function reveal(scope) {
      if (paused || done) return;
      begin();
      scopeCells(scope).forEach(function (p) { setLetter(p[0], p[1], sol[p[0]].charAt(p[1]), 'rev'); });
      afterEdit();
    }
    clear.addEventListener('click', function () {
      if (!window.confirm('Clear the whole grid and reset the timer?')) return;
      for (var i = 0; i < W * H; i++) { letters[i] = ''; flags[i] = ''; }
      elapsed = 0; done = false; started = false; setRunning(false); setPaused(false); showTime(); announce('Grid cleared.');
      timerBtn.disabled = false; root.classList.remove('cw-solved', 'cw-wave');
      selectWord(words[0]); save();                                 // back to 1 Across
    });
    function announce(msg) { status.textContent = msg; }
    function helpedCount() { return flags.filter(function (f) { return f === 'rev'; }).length; }
    function solvedMessage() {
      var helped = helpedCount();
      return 'Solved in ' + clock(elapsed) + (helped ? ', with ' + helped + (helped === 1 ? ' square' : ' squares') + ' revealed.' : '.');
    }
    var waveTimer = null;
    function finish(celebrate) {                                   // a small flourish for a clean solve: a wave across the grid and a stamp
      timerBtn.disabled = true;
      root.classList.toggle('cw-solved', helpedCount() === 0);
      if (celebrate && helpedCount() === 0) {
        root.classList.remove('cw-wave');
        void root.offsetWidth;                                     // restart the animation if it ran before
        root.classList.add('cw-wave');
        clearTimeout(waveTimer);
        waveTimer = setTimeout(function () { root.classList.remove('cw-wave'); }, 1800);
      }
    }
    function afterEdit() {
      if (!done && solved()) {
        done = true; setRunning(false);
        announce(solvedMessage());
        finish(true);
      }
      paint(); save();
    }

    /* ---- drawing ---- */
    function ensureVisible(box, item) {
      var top = item.offsetTop - box.offsetTop, bottom = top + item.offsetHeight;
      if (top < box.scrollTop) box.scrollTop = top - 4;
      else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 4;
    }
    function paint() {
      fixDir();
      var w = curWord(), inWord = {};
      w.cells.forEach(function (p) { inWord[idx(p[0], p[1])] = true; });
      for (var rr = 0; rr < H; rr++) {
        for (var cc = 0; cc < W; cc++) {
          var i = idx(rr, cc), g = cellEls[i];
          if (isBlock(rr, cc)) continue;
          var cls = 'cw-c';
          if (!done) { if (rr === cur.r && cc === cur.c) cls += ' cw-cur'; else if (inWord[i]) cls += ' cw-word'; }
          if (flags[i] === 'bad') cls += ' cw-bad';
          if (flags[i] === 'rev') cls += ' cw-rev';
          g.setAttribute('class', cls);
          g.querySelector('.cw-let').textContent = letters[i];
        }
      }
      var label = w.n + (w.dir === 'across' ? 'A' : 'D'), text = ' ' + (w.clue || '');
      if (done) { label = helpedCount() ? 'Filled in' : 'Solved'; text = ' in ' + clock(elapsed); }
      if (bannerNum.textContent !== label) bannerNum.textContent = label;         // only when the clue changes, so screen readers hear it once
      if (bannerText.textContent !== text) bannerText.textContent = text;
      var crossWord = wordAt[w.dir === 'across' ? 'down' : 'across'][idx(cur.r, cur.c)];
      clueEls.forEach(function (b, j) {
        b.classList.toggle('cw-active', j === w.idx);
        b.classList.toggle('cw-cross', !!crossWord && j === crossWord.idx);
      });
      [w, crossWord].forEach(function (x) { if (x && clueEls[x.idx]) ensureVisible(clueEls[x.idx].closest('.cw-list'), clueEls[x.idx].parentNode); });
      showTime();
    }

    /* ---- keyboard (physical keys) and the input event (phone keyboards) ---- */
    input.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var kk = e.key, handled = true;
      if (kk.length === 1 && /[A-Za-z0-9]/.test(kk)) type(kk.toUpperCase());
      else if (kk === 'Backspace' || kk === 'Delete') backspace();
      else if (kk === 'ArrowLeft') arrow('across', 0, -1);
      else if (kk === 'ArrowRight') arrow('across', 0, 1);
      else if (kk === 'ArrowUp') arrow('down', -1, 0);
      else if (kk === 'ArrowDown') arrow('down', 1, 0);
      else if (kk === 'Tab') nextClue(e.shiftKey ? -1 : 1);
      else if (kk === ' ' || kk === 'Enter') { if (!paused) { cur.dir = other(); fixDir(); paint(); } }
      else if (kk === 'Escape') { input.blur(); }
      else handled = false;
      if (handled) e.preventDefault();
    });
    input.addEventListener('input', function () {
      var ch = input.value.slice(-1);
      input.value = '';
      if (/[A-Za-z0-9]/.test(ch)) type(ch.toUpperCase());
    });
    input.addEventListener('focus', function () { board.classList.add('cw-focus'); });
    input.addEventListener('blur', function () { board.classList.remove('cw-focus'); });

    /* ---- go ---- */
    load();
    var first = words.filter(function (x) { return x.dir === 'across'; })[0] || words[0];
    cur.r = first.cells[0][0]; cur.c = first.cells[0][1]; cur.dir = first.dir;
    playIcon.className = 'cw-icon cw-play';
    timerBtn.setAttribute('aria-label', started && !done ? 'Resume the timer, ' + clock(elapsed) : 'Start the timer');
    if (done) { announce(solvedMessage()); finish(false); }
    paint();
  }

  document.querySelectorAll('.crossword').forEach(init);
})();
