/* ORA scores table: adds a paged scores table below the native list in the Open
 * Responses tab of the legacy instructor dashboard. Copy of the Auto Assessments
 * tab script in tutor-contrib-edl with a different CSS prefix and global name. Keep in sync.
 * Server data is only ever written with textContent (or setAttribute for title), never innerHTML. */
(function () {
  'use strict';

  var PAGE_SIZES = [10, 25, 50];
  var NO_ATTEMPT = 'No attempt yet';
  var BASE_TITLE = 'Open response scores';
  var AWAITING = 'Awaiting grade';
  var FONT_LINK_ID = 'edl-inter-font';
  var FONT_URL = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
  // Column widths in px, used for the table's minimum width so many assessments scroll sideways.
  var LEARNER_WIDTH = 200;
  var DATE_WIDTH = 96;
  var CRITERION_MIN_WIDTH = 136;

  var state = {page: 1, pageSize: 10, q: '', assessment: '', loaded: false, requestId: 0, timer: null, courseName: ''};
  var els = {};

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function root() { return document.querySelector('#open_response_assessment .edl-ora'); }

  // Inter comes from Google Fonts. If it is blocked the CSS falls back to the system font.
  function loadFont() {
    if (document.getElementById(FONT_LINK_ID)) { return; }
    var connect = el('link');
    connect.rel = 'preconnect';
    connect.href = 'https://fonts.googleapis.com';
    var connectStatic = el('link');
    connectStatic.rel = 'preconnect';
    connectStatic.href = 'https://fonts.gstatic.com';
    connectStatic.crossOrigin = 'anonymous';
    var sheet = el('link');
    sheet.id = FONT_LINK_ID;
    sheet.rel = 'stylesheet';
    sheet.href = FONT_URL;
    document.head.appendChild(connect);
    document.head.appendChild(connectStatic);
    document.head.appendChild(sheet);
  }

  function srLabel(text, forId) {
    var label = el('label', 'sr-only', text);
    label.setAttribute('for', forId);
    return label;
  }

  // The CSV always holds every learner and every assessment. Only the browser time zone is added.
  function updateCsvLink() {
    var host = root();
    var base = host && host.getAttribute('data-csv-url');
    if (base && els.download) { els.download.href = withZone(base); }
  }

  function buildControls(host) {
    var tableRoot = host.querySelector('.edl-ora-table-root');
    els.title = host.querySelector('.edl-ora-title');
    els.intro = host.querySelector('.edl-ora-intro');
    var bar = el('div', 'edl-ora-bar');

    els.search = el('input', 'edl-ora-search');
    els.search.id = 'edl-ora-search';
    els.search.type = 'search';
    els.search.placeholder = 'Name, username or email';
    els.search.addEventListener('input', function () {
      window.clearTimeout(state.timer);
      state.timer = window.setTimeout(function () {
        state.q = els.search.value.trim();
        state.page = 1;
        fetchPage();
      }, 300);
    });

    els.clear = el('button', 'edl-ora-clear', 'Clear filters');
    els.clear.type = 'button';
    els.clear.hidden = true;
    els.clear.addEventListener('click', function () {
      window.clearTimeout(state.timer);
      els.search.value = '';
      state.q = '';
      state.page = 1;
      fetchPage();
      els.search.focus();
    });

    els.select = el('select', 'edl-ora-assessment');
    els.select.id = 'edl-ora-assessment';
    els.select.appendChild(new Option('All assessments', ''));
    els.select.addEventListener('change', function () {
      state.assessment = els.select.value;
      state.page = 1;
      fetchPage();
    });

    bar.appendChild(srLabel('Search learners', els.search.id));
    bar.appendChild(els.search);
    bar.appendChild(els.clear);
    bar.appendChild(srLabel('Assessment', els.select.id));
    bar.appendChild(els.select);
    els.download = el('a', 'edl-ora-download', 'Download CSV');
    els.download.href = '#';
    bar.appendChild(els.download);

    tableRoot.appendChild(bar);

    els.status = el('div', 'edl-ora-status');
    els.status.setAttribute('role', 'status');
    els.scroll = el('div', 'edl-ora-scroll');
    els.scroll.tabIndex = 0;
    els.scroll.setAttribute('role', 'region');
    els.scroll.setAttribute('aria-label', 'Learner scores table, scrolls sideways');
    els.footer = el('div', 'edl-ora-footer');
    tableRoot.appendChild(els.status);
    tableRoot.appendChild(els.scroll);
    tableRoot.appendChild(els.footer);
    updateCsvLink();
  }

  // The course name is the competency of every column (see get_columns), so no extra field is needed.
  function setHeading(payload) {
    if (payload.columns.length) { state.courseName = payload.columns[0].competency || ''; }
    els.title.textContent = state.courseName ? BASE_TITLE + ' for ' + state.courseName : BASE_TITLE;
    els.intro.textContent = 'Scores for each rubric criterion in every open response assessment. ' +
      'Demonstrated means ' + payload.threshold + '% or more.';
  }

  // Rebuilt on every response so the counts stay current. The selected option is kept.
  function setAssessments(assessments) {
    var selected = state.assessment;
    els.select.textContent = '';
    els.select.appendChild(new Option('All assessments (' + assessments.length + ' assessments)', ''));
    assessments.forEach(function (a) {
      els.select.appendChild(new Option(a.name + ' (' + a.attempted + ' of ' + a.total + ' attempted)', a.id));
    });
    els.select.value = selected;
  }

  function setClear() { els.clear.hidden = !state.q; }

  function noMatch() {
    var box = el('div', 'edl-ora-nomatch');
    box.appendChild(el('strong', null, 'No learners match'));
    box.appendChild(document.createTextNode('Try a different search.'));
    return box;
  }

  function dateCell(info) {
    var td = el('td', 'edl-ora-date edl-ora-group-start');
    td.appendChild(el('div', 'edl-ora-date-text', info.date));
    if (info.note) { td.appendChild(el('div', 'edl-ora-date-note', info.note)); }
    return td;
  }

  function scoreCell(cell) {
    var td = el('td');
    if (cell === null) {
      td.className = 'edl-ora-none';
      td.textContent = NO_ATTEMPT;
      return td;
    }
    var demonstrated = cell.status === 'demonstrated';
    td.className = demonstrated ? 'edl-ora-demonstrated' : 'edl-ora-not-demonstrated';
    td.appendChild(el('div', 'edl-ora-pct', cell.percent + '%'));
    td.appendChild(el('div', 'edl-ora-label', demonstrated ? 'Demonstrated' : 'Not demonstrated'));
    return td;
  }

  function learnerCell(learner) {
    var th = el('th', 'edl-ora-sticky edl-ora-learner');
    th.scope = 'row';
    th.appendChild(el('strong', null, learner.name));
    th.appendChild(el('div', 'edl-ora-sub', learner.username));
    var email = el('div', 'edl-ora-email', learner.email);
    email.setAttribute('title', learner.email);
    th.appendChild(email);
    return th;
  }

  // Splits the flat column list into one block per assessment: {id, name, start, count}.
  function groupColumns(columns) {
    var blocks = [];
    columns.forEach(function (c, idx) {
      var last = blocks[blocks.length - 1];
      if (last && last.id === c.block_id) {
        last.count += 1;
      } else {
        blocks.push({id: c.block_id, name: c.assessment, start: idx, count: 1});
      }
    });
    return blocks;
  }

  function buildColgroup(blocks) {
    var colgroup = el('colgroup');
    colgroup.appendChild(el('col', 'edl-ora-col-learner'));
    blocks.forEach(function (block) {
      colgroup.appendChild(el('col', 'edl-ora-col-date'));
      for (var n = 0; n < block.count; n += 1) { colgroup.appendChild(el('col')); }
    });
    return colgroup;
  }

  function buildHead(columns, blocks) {
    var head = el('thead');
    var row1 = el('tr');
    var row2 = el('tr');

    var learnerHead = el('th', 'edl-ora-sticky edl-ora-learner-head', 'Learner');
    learnerHead.rowSpan = 2;
    learnerHead.scope = 'col';
    row1.appendChild(learnerHead);

    blocks.forEach(function (block) {
      var group = el('th', 'edl-ora-group', block.name);
      group.colSpan = block.count + 1;  // plus the "Attempt date" column
      group.scope = 'colgroup';
      row1.appendChild(group);

      var dateHead = el('th', 'edl-ora-date-head edl-ora-group-start', 'Attempt date');
      dateHead.scope = 'col';
      row2.appendChild(dateHead);
      for (var n = block.start; n < block.start + block.count; n += 1) {
        var th = el('th', 'edl-ora-criterion', columns[n].criterion);
        th.scope = 'col';
        row2.appendChild(th);
      }
    });
    head.appendChild(row1);
    head.appendChild(row2);
    return head;
  }

  function buildRow(learner, blocks) {
    var tr = el('tr');
    tr.appendChild(learnerCell(learner));
    blocks.forEach(function (block) {
      var info = (learner.dates || {})[block.id];
      if (!info || !info.date) {
        // One merged cell per assessment, never per row.
        var none = el('td', 'edl-ora-none edl-ora-group-start', NO_ATTEMPT);
        none.colSpan = block.count + 1;
        tr.appendChild(none);
        return;
      }
      tr.appendChild(dateCell(info));
      var cells = learner.cells.slice(block.start, block.start + block.count);
      if (cells.every(function (cell) { return cell === null; })) {
        // Submitted but not graded yet: one merged cell, the date note says the same.
        var awaiting = el('td', 'edl-ora-none', AWAITING);
        awaiting.colSpan = block.count;
        tr.appendChild(awaiting);
        return;
      }
      cells.forEach(function (cell) { tr.appendChild(scoreCell(cell)); });
    });
    return tr;
  }

  function renderTable(payload) {
    els.scroll.textContent = '';
    if (!payload.columns.length) {
      els.status.textContent = 'No open response assessments with rubric criteria in this course.';
      return;
    }
    if (!payload.learners.length) {
      els.status.textContent = '';
      els.scroll.appendChild(state.q ? noMatch() : el('div', 'edl-ora-nomatch', 'No learners found.'));
      return;
    }
    els.status.textContent = '';

    var blocks = groupColumns(payload.columns);
    var table = el('table', 'edl-ora-table');
    table.style.minWidth = (LEARNER_WIDTH + blocks.length * DATE_WIDTH +
      payload.columns.length * CRITERION_MIN_WIDTH) + 'px';
    table.appendChild(buildColgroup(blocks));
    table.appendChild(buildHead(payload.columns, blocks));

    var body = el('tbody');
    payload.learners.forEach(function (learner) { body.appendChild(buildRow(learner, blocks)); });
    table.appendChild(body);
    els.scroll.appendChild(table);
  }

  function pageButton(label, page, disabled, current) {
    var button = el('button', 'edl-ora-page' + (current ? ' edl-ora-current' : ''), label);
    button.type = 'button';
    button.disabled = !!disabled;
    if (current) { button.setAttribute('aria-current', 'page'); }
    button.addEventListener('click', function () {
      state.page = page;
      fetchPage();
    });
    return button;
  }

  function renderFooter(payload) {
    els.footer.textContent = '';
    var info = el('span', 'edl-ora-info', 'Showing ' + payload.learners.length + ' of ' + payload.total + ' learners');
    info.setAttribute('role', 'status');
    els.footer.appendChild(info);

    var size = el('select', 'edl-ora-size');
    size.setAttribute('aria-label', 'Rows per page');
    PAGE_SIZES.forEach(function (n) {
      var option = new Option(n + ' per page', n);
      option.selected = n === payload.page_size;
      size.appendChild(option);
    });
    size.addEventListener('change', function () {
      state.pageSize = parseInt(size.value, 10);
      state.page = 1;
      fetchPage();
    });
    els.footer.appendChild(size);

    var pager = el('span', 'edl-ora-pager');
    pager.appendChild(pageButton('Previous', payload.page - 1, payload.page <= 1));
    for (var p = Math.max(1, payload.page - 2); p <= Math.min(payload.num_pages, payload.page + 2); p += 1) {
      pager.appendChild(pageButton(String(p), p, false, p === payload.page));
    }
    pager.appendChild(pageButton('Next', payload.page + 1, payload.page >= payload.num_pages));
    els.footer.appendChild(pager);
  }

  // The viewer's IANA time zone (for example "America/Chicago"). The server writes every date in it.
  function browserZone() {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { return ''; }
  }

  function withZone(url) {
    var zone = browserZone();
    if (!url || !zone) { return url; }
    return url + (url.indexOf('?') === -1 ? '?' : '&') + 'tz=' + encodeURIComponent(zone);
  }

  function fetchPage() {
    var host = root();
    if (!host) { return; }
    var url = host.getAttribute('data-data-url');
    if (!url) { return; }

    state.requestId += 1;
    var requestId = state.requestId;
    var params = new URLSearchParams({
      page: state.page, page_size: state.pageSize, q: state.q, assessment: state.assessment, tz: browserZone()
    });
    els.status.textContent = 'Loading...';
    setClear();

    fetch(url + '?' + params.toString(), {credentials: 'same-origin'})
      .then(function (response) {
        if (!response.ok) { throw new Error('HTTP ' + response.status); }
        return response.json();
      })
      .then(function (payload) {
        if (requestId !== state.requestId) { return; }  // a newer request replaced this one
        state.page = payload.page;
        setHeading(payload);
        setAssessments(payload.assessments);
        renderTable(payload);
        renderFooter(payload);
      })
      .catch(function () {
        if (requestId !== state.requestId) { return; }
        els.scroll.textContent = '';
        els.footer.textContent = '';
        els.status.textContent = 'Could not load scores. Try again.';
      });
  }

  window.EdlOraScores = {
    load: function () {
      var host = root();
      if (!host || state.loaded || !host.getAttribute('data-data-url')) { return; }
      state.loaded = true;
      loadFont();
      buildControls(host);
      fetchPage();
    }
  };

  // The native Open Responses section already has its own dashboard wrapper
  // (onClickTitle), so this script never touches $section.data('wrapper').
  function buildHost(section) {
    var config = window.EdlOraScoresConfig || {};
    var host = el('div', 'edl-ora');
    host.setAttribute('data-data-url', config.dataUrl || '');
    host.setAttribute('data-csv-url', config.csvUrl || '');
    host.appendChild(el('h2', 'edl-ora-title', BASE_TITLE));
    host.appendChild(el('p', 'edl-ora-intro',
      'Scores for each rubric criterion in every open response assessment. Demonstrated means ' +
      config.threshold + '% or more.'));
    host.appendChild(el('div', 'edl-ora-table-root'));
    section.appendChild(host);  // below the native ORA list
  }

  function init() {
    var section = document.getElementById('open_response_assessment');
    if (!section || section.querySelector('.edl-ora')) { return; }
    buildHost(section);

    // Load once, the first time the section is the visible one.
    if (section.classList.contains('active-section')) {
      window.EdlOraScores.load();
      return;
    }
    var observer = new MutationObserver(function () {
      if (section.classList.contains('active-section')) {
        observer.disconnect();
        window.EdlOraScores.load();
      }
    });
    observer.observe(section, {attributes: true, attributeFilter: ['class']});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
