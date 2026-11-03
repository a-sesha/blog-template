/* Crossword player. build.py turns {{crossword file.ipuz}} into <div class="crossword"> holding the puzzle as JSON; this script builds
   the board, the clue lists and the toolbar from it. No dependencies. Keyboard: letters type, arrows move, Space or Enter turns the
   direction, Tab and Shift+Tab change clue (Tab on the last clue, or Shift+Tab on the first, leaves the board), Backspace deletes, Escape leaves the board. Progress and the timer are kept in this
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
    if (!words.length) return;

    /* ---- state ---- */
    var letters = [], flags = [];                               // flags: '' | 'bad' (failed a check) | 'rev' (revealed)
    for (k = 0; k < W * H; k++) { letters.push(''); flags.push(''); }
    var cur = { r: 0, c: 0, dir: 'across' }, elapsed = 0, running = false, paused = false, done = false, ticker = null, started = false;
    var wasRunning = false, revealed = 0;
    var key = 'blog-crossword:' + data.id;

    function load() {
      var s = store(key);
      if (!s || typeof s.l !== 'string' || s.l.length !== W * H || !/^[A-Z0-9 ]*$/.test(s.l)) return;
      var marks = typeof s.f === 'string' ? s.f : '';
      for (var i = 0; i < W * H; i++) {
        var ch = s.l.charAt(i);
        letters[i] = ch === ' ' || isBlock(Math.floor(i / W), i % W) ? '' : ch;
        flags[i] = marks.charAt(i) === 'r' ? 'rev' : '';
      }
      elapsed = typeof s.t === 'number' && isFinite(s.t) ? Math.max(0, Math.floor(s.t)) : 0;
      revealed = typeof s.h === 'number' && isFinite(s.h) ? Math.max(0, Math.floor(s.h)) : 0;
      done = s.d === true;
      started = elapsed > 0 || letters.some(Boolean);
    }
    function save() {
      store(key, { l: letters.map(function (x) { return x || ' '; }).join(''), f: flags.map(function (x) { return x === 'rev' ? 'r' : '.'; }).join(''), t: elapsed, h: revealed, d: done });
    }

    /* ---- the page ---- */
    var bar = el('div', 'cw-bar'), timerBtn = el('button', 'btn cw-timer'), timeText = el('span', 'cw-time', '00:00');
    timerBtn.type = 'button';
    var playIcon = el('span', 'cw-icon');
    timerBtn.appendChild(playIcon); timerBtn.appendChild(timeText);
    bar.appendChild(timerBtn);

    var menus = [];
    function closeMenus(except) { menus.forEach(function (m) { if (m !== except && m.open) m.open = false; }); }
    function menu(label, actions) {
      var d = el('details', 'cw-menu'), s = el('summary', 'btn', label), box = el('div', 'cw-menu-items');
      actions.forEach(function (a) {
        var b = el('button', 'btn', a[0]);
        b.type = 'button';
        b.addEventListener('click', function () { a[1](); d.open = false; focusBoard(); });
        box.appendChild(b);
      });
      d.appendChild(s); d.appendChild(box);
      d.addEventListener('toggle', function () { if (d.open) closeMenus(d); });      // opening one closes the other
      menus.push(d);
      return d;
    }
    bar.appendChild(menu('Check', [['Square', function () { check('square'); }], ['Word', function () { check('word'); }], ['Puzzle', function () { check('puzzle'); }]]));
    bar.appendChild(menu('Reveal', [['Square', function () { reveal('square'); }], ['Word', function () { reveal('word'); }], ['Puzzle', function () { reveal('puzzle'); }]]));
    document.addEventListener('click', function (e) {                           // a click anywhere else, or on the board, closes an open menu
      menus.forEach(function (m) { if (m.open && !m.contains(e.target)) m.open = false; });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      menus.forEach(function (m) {
        if (!m.open) return;
        var inside = m.contains(document.activeElement);
        m.open = false;
        if (inside) m.querySelector('summary').focus();
      });
    });
    bar.addEventListener('focusout', function (e) {                             // tabbing out of a menu closes it
      menus.forEach(function (m) { if (m.open && e.relatedTarget && !m.contains(e.relatedTarget)) m.open = false; });
    });
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
    var cellEls = [], letEls = [], shown = [], cursorBox = svg('rect', { width: CELL - 3, height: CELL - 3, 'class': 'cw-curbox' });
    for (r = 0; r < H; r++) {
      for (c = 0; c < W; c++) {
        var g = svg('g', { 'class': 'cw-c' });
        var x = c * CELL, y = r * CELL;
        g.style.setProperty('--d', Math.round((r + c) * 900 / Math.max(1, W + H - 2)) + 'ms');       // the wave always takes about a second
        g.appendChild(svg('rect', { x: x, y: y, width: CELL, height: CELL, 'class': 'cw-sq' }));
        if (isBlock(r, c)) { g.setAttribute('class', 'cw-c cw-block'); grid.appendChild(g); cellEls.push(g); continue; }
        if ((data.circles || []).some(function (p) { return p[0] === r && p[1] === c; })) g.appendChild(svg('circle', { cx: x + CELL / 2, cy: y + CELL / 2, r: CELL / 2 - 1.5, 'class': 'cw-circle' }));
        if (numberAt[r * W + c]) { var nt = svg('text', { x: x + 3, y: y + 11, 'class': 'cw-num' }); nt.textContent = numberAt[r * W + c]; g.appendChild(nt); }
        var lt = svg('text', { x: x + CELL / 2, y: y + CELL - 9, 'class': 'cw-let', 'text-anchor': 'middle' });
        g.appendChild(lt);
        letEls[r * W + c] = lt;
        g.appendChild(svg('line', { x1: x + 2, y1: y + CELL - 2, x2: x + CELL - 2, y2: y + 2, 'class': 'cw-slash' }));
        g.appendChild(svg('path', { d: 'M' + (x + CELL - 11) + ' ' + y + 'h11v11z', 'class': 'cw-revmark' }));
        (function (rr, cc) { g.addEventListener('mousedown', function (e) { if (e.button !== 0) return; e.preventDefault(); clickCell(rr, cc); }); })(r, c);
        grid.appendChild(g);
        cellEls.push(g);
      }
    }
    grid.appendChild(cursorBox);                                   // drawn last so the cursor square's outline is never covered by a neighbour
    var input = el('input', 'cw-input');
    input.type = 'text'; input.autocomplete = 'off'; input.spellcheck = false;
    input.setAttribute('autocapitalize', 'characters'); input.setAttribute('autocorrect', 'off');
    input.setAttribute('aria-label', 'Crossword: type your answer. Arrow keys move, Tab changes clue, Space turns the direction, Escape leaves the board.');
    frame.appendChild(grid); frame.appendChild(input);
    var pausedNote = el('div', 'cw-pausednote', 'Paused. Press the timer to continue.');
    frame.appendChild(pausedNote);
    board.appendChild(banner); board.appendChild(frame);

    var clues = el('div', 'cw-clues'), clueEls = [];
    ['across', 'down'].forEach(function (dir) {
      var mine = words.filter(function (w) { return w.dir === dir; });
      if (!mine.length) return;
      var sec = el('section', 'cw-list'), h = el('h3', null, dir === 'across' ? 'Across' : 'Down'), ol = el('ol');
      mine.forEach(function (w) {
        var li = el('li'), b = el('button', 'cw-clue'), nn = el('span', 'cw-cn', String(w.n)), tx = el('span', null, w.clue || '');
        b.type = 'button'; b.appendChild(nn); b.appendChild(tx);
        b.addEventListener('click', function () { if (paused) return; selectWord(w); focusBoard(); });
        li.appendChild(b); ol.appendChild(li);
        clueEls[w.idx] = b;
      });
      sec.appendChild(h); sec.appendChild(ol); clues.appendChild(sec);
    });
    main.appendChild(board); main.appendChild(clues);
    var status = el('p', 'cw-status');
    status.setAttribute('role', 'status');
    var where = el('p', 'cw-sr');                                  // the board itself is a picture; this says which square you are on
    where.setAttribute('aria-live', 'polite');
    root.appendChild(bar); root.appendChild(main); root.appendChild(status); root.appendChild(where);

    /* ---- helpers ---- */
    function idx(rr, cc) { return rr * W + cc; }
    function curWord() { return wordAt[cur.dir][idx(cur.r, cur.c)] || wordAt[cur.dir === 'across' ? 'down' : 'across'][idx(cur.r, cur.c)]; }
    function fixDir() { if (!wordAt[cur.dir][idx(cur.r, cur.c)]) cur.dir = cur.dir === 'across' ? 'down' : 'across'; }
    function other() { return cur.dir === 'across' ? 'down' : 'across'; }
    function focusBoard() { if (!paused) input.focus({ preventScroll: true }); }
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
      for (var q = 0; q < w.cells.length; q++) if (w.cells[q][0] === cur.r && w.cells[q][1] === cur.c) i = q;
      var j = i + delta;
      return j >= 0 && j < w.cells.length ? w.cells[j] : null;
    }
    var every = [];                                                // every playable square, listed once
    for (r = 0; r < H; r++) for (c = 0; c < W; c++) if (!isBlock(r, c)) every.push([r, c]);
    function allCells() { return every; }
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
    function syncTimer() {
      playIcon.className = 'cw-icon ' + (running ? 'cw-pause' : 'cw-play');
      timerBtn.setAttribute('aria-label', done ? 'Timer stopped' : running ? 'Pause the timer' : !started ? 'Start the timer' : 'Resume the timer');
    }
    function setRunning(on) {
      if (on === running) return;
      running = on;
      if (on) ticker = setInterval(tick, 1000); else { clearInterval(ticker); ticker = null; }
      syncTimer();
    }
    function begin() { started = true; if (!done && !paused) setRunning(true); else syncTimer(); }
    function setPaused(pause) {
      paused = pause; root.classList.toggle('cw-paused', pause);
      setRunning(!pause && started && !done);
      if (pause) { input.blur(); announce('Paused.'); } else focusBoard();
      syncTimer(); save();
    }
    timerBtn.addEventListener('click', function () {
      if (done) return;
      if (!running && !paused) { begin(); focusBoard(); return; }    // not started yet, or stopped because the tab was hidden: just go
      setPaused(!paused);
    });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) { wasRunning = running; setRunning(false); save(); }                    // iOS may never fire pagehide for a hidden tab
      else if (wasRunning && !paused && !done) { wasRunning = false; setRunning(true); }           // resume only what was running
    });
    window.addEventListener('pagehide', save);

    /* ---- actions ---- */
    function setLetter(rr, cc, ch, flag) {
      letters[idx(rr, cc)] = ch;
      flags[idx(rr, cc)] = flag || '';
    }
    function type(ch) {
      if (paused || done) return;
      begin();
      setLetter(cur.r, cur.c, ch, flags[idx(cur.r, cur.c)] === 'rev' ? 'rev' : '');      // retyping a revealed square keeps its mark
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
      var w = curWord(), j = (w.idx + delta + words.length) % words.length;
      selectWord(words[j]);
    }
    function check(scope) {
      if (paused) return;
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
      var added = 0;
      scopeCells(scope).forEach(function (p) {
        if (flags[idx(p[0], p[1])] !== 'rev') added++;
        setLetter(p[0], p[1], sol[p[0]].charAt(p[1]), 'rev');
      });
      revealed += added;
      announce(added ? 'Revealed ' + added + (added === 1 ? ' square.' : ' squares.') : 'Nothing new to reveal.');
      afterEdit();
    }
    var clearTimer = null;
    function resetClear() { clearTimeout(clearTimer); clearTimer = null; clear.textContent = 'Clear'; }
    clear.addEventListener('click', function () {
      if (!clearTimer && (started || letters.some(Boolean))) {      // two steps instead of a pop-up: press again within a few seconds to confirm (6 s)
        clear.textContent = 'Sure? Clear';
        clearTimer = setTimeout(resetClear, 6000);
        announce('Press Clear again to empty the grid.');
        return;
      }
      resetClear();
      for (var i = 0; i < W * H; i++) { letters[i] = ''; flags[i] = ''; }
      elapsed = 0; revealed = 0; done = false; started = false; paused = false; wasRunning = false;
      setRunning(false); root.classList.remove('cw-paused', 'cw-solved', 'cw-wave');
      timerBtn.disabled = false; syncTimer(); showTime(); announce('Grid cleared.');
      selectWord(words[0]); save();                                 // back to 1 Across; focus stays on the Clear button
    });
    function announce(msg) { status.textContent = msg; }
    function helpedCount() { return revealed; }
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
        done = true; setRunning(false); syncTimer();
        announce(solvedMessage());
        finish(true);
      }
      paint(); save();
    }

    /* ---- drawing ---- */
    function ensureVisible(box, item) {                            // `box` is the scrolling <ol>; offsetTop is already measured from it
      var top = item.offsetTop, bottom = top + item.offsetHeight;
      if (top < box.scrollTop) box.scrollTop = top - 4;
      else if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 4;
    }
    var lastActive = -1, lastCross = -1, lastSquare = '';
    function paint() {
      fixDir();
      var w = curWord(), inWord = {};
      w.cells.forEach(function (p) { inWord[idx(p[0], p[1])] = true; });
      for (var q = 0; q < every.length; q++) {
        var rr = every[q][0], cc = every[q][1], i = idx(rr, cc), cls = 'cw-c';
        if (!done) { if (rr === cur.r && cc === cur.c) cls += ' cw-cur'; else if (inWord[i]) cls += ' cw-word'; }
        if (flags[i] === 'bad') cls += ' cw-bad';
        if (flags[i] === 'rev') cls += ' cw-rev';
        var state = cls + '|' + letters[i];
        if (shown[i] === state) continue;                          // unchanged since the last paint
        shown[i] = state;
        cellEls[i].setAttribute('class', cls);
        letEls[i].textContent = letters[i];
      }
      cursorBox.setAttribute('x', cur.c * CELL + 1.5); cursorBox.setAttribute('y', cur.r * CELL + 1.5);
      cursorBox.style.display = done ? 'none' : '';
      var label = w.n + (w.dir === 'across' ? 'A' : 'D'), text = ' ' + (w.clue || '');
      if (done) { label = helpedCount() ? 'Filled in' : 'Solved'; text = (helpedCount() ? ' ' : ' in ') + clock(elapsed); }
      if (bannerNum.textContent !== label) bannerNum.textContent = label;         // only when the clue changes, so screen readers hear it once
      if (bannerText.textContent !== text) bannerText.textContent = text;
      var crossWord = wordAt[w.dir === 'across' ? 'down' : 'across'][idx(cur.r, cur.c)], crossIdx = crossWord ? crossWord.idx : -1;
      if (w.idx !== lastActive) {                                  // only the clue buttons that changed
        if (lastActive >= 0) clueEls[lastActive].classList.remove('cw-active');
        clueEls[w.idx].classList.add('cw-active');
        lastActive = w.idx;
        ensureVisible(clueEls[w.idx].parentNode.parentNode, clueEls[w.idx].parentNode);
      }
      if (crossIdx !== lastCross) {
        if (lastCross >= 0) clueEls[lastCross].classList.remove('cw-cross');
        if (crossIdx >= 0) { clueEls[crossIdx].classList.add('cw-cross'); ensureVisible(clueEls[crossIdx].parentNode.parentNode, clueEls[crossIdx].parentNode); }
        lastCross = crossIdx;
      }
      banner.setAttribute('aria-live', done ? 'off' : 'polite');   // the status line says it once when the puzzle is solved
      var pos = 1 + w.cells.map(function (p) { return idx(p[0], p[1]); }).indexOf(idx(cur.r, cur.c));
      var square = (letters[idx(cur.r, cur.c)] || 'blank') + ', square ' + pos + ' of ' + w.cells.length + ', ' + label;
      if (square !== lastSquare) { lastSquare = square; where.textContent = square; }
      showTime();
    }

    /* ---- keyboard (physical keys) and the input event (phone keyboards) ---- */
    input.addEventListener('keydown', function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var kk = e.key, handled = true;
      if (kk.length === 1 && /[A-Za-z0-9]/.test(kk)) type(kk.toUpperCase());
      else if (kk === 'Backspace') backspace();
      else if (kk === 'Delete') { if (!paused && !done) { setLetter(cur.r, cur.c, ''); afterEdit(); } }       // clears this square and stays
      else if (kk === 'ArrowLeft') arrow('across', 0, -1);
      else if (kk === 'ArrowRight') arrow('across', 0, 1);
      else if (kk === 'ArrowUp') arrow('down', -1, 0);
      else if (kk === 'ArrowDown') arrow('down', 1, 0);
      else if (kk === 'Tab') {
        var here = curWord().idx;
        if (paused || (e.shiftKey ? here === 0 : here === words.length - 1)) handled = false;   // the first and last clue let Tab carry on to the page
        else nextClue(e.shiftKey ? -1 : 1);
      }
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
    syncTimer();
    if (done) { announce(solvedMessage()); finish(false); }
    paint();
  }

  document.querySelectorAll('.crossword').forEach(init);
})();
