/* ORA scores table: adds a paged scores table below the native list in the Open
 * Responses tab of the legacy instructor dashboard. Copy of the Auto Assessments
 * tab script in tutor-contrib-edl with a different CSS prefix and global name. Keep in sync.
 * Server data is only ever written with textContent, never innerHTML. */
(function () {
  'use strict';

  var PAGE_SIZES = [10, 25, 50];
  var state = {page: 1, pageSize: 10, q: '', assessment: '', loaded: false, requestId: 0, timer: null};
  var els = {};

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function root() { return document.querySelector('#open_response_assessment .edl-ora'); }

  function buildControls(host) {
    var bar = el('div', 'edl-ora-bar');

    els.search = el('input', 'edl-ora-search');
    els.search.type = 'search';
    els.search.placeholder = 'Search name, username or email';
    els.search.setAttribute('aria-label', 'Search learners');
    els.search.addEventListener('input', function () {
      window.clearTimeout(state.timer);
      state.timer = window.setTimeout(function () {
        state.q = els.search.value.trim();
        state.page = 1;
        fetchPage();
      }, 300);
    });

    els.select = el('select', 'edl-ora-assessment');
    els.select.setAttribute('aria-label', 'Filter by assessment');
    els.select.appendChild(new Option('All assessments', ''));
    els.select.addEventListener('change', function () {
      state.assessment = els.select.value;
      state.page = 1;
      fetchPage();
    });

    els.legend = el('span', 'edl-ora-legend');
    bar.appendChild(els.search);
    bar.appendChild(els.select);
    bar.appendChild(els.legend);

    var download = host.querySelector('.edl-ora-download');
    if (download) { bar.appendChild(download); }
    host.querySelector('.edl-ora-table-root').appendChild(bar);

    els.status = el('div', 'edl-ora-status');
    els.status.setAttribute('role', 'status');
    els.scroll = el('div', 'edl-ora-scroll');
    els.scroll.tabIndex = 0;
    els.scroll.setAttribute('role', 'region');
    els.scroll.setAttribute('aria-label', 'Open response assessment scores');
    els.footer = el('div', 'edl-ora-footer');
    var tableRoot = host.querySelector('.edl-ora-table-root');
    tableRoot.appendChild(els.status);
    tableRoot.appendChild(els.scroll);
    tableRoot.appendChild(els.footer);
  }

  function setLegend(threshold) {
    els.legend.textContent = '';
    els.legend.appendChild(el('span', 'edl-ora-chip edl-ora-demonstrated', 'Demonstrated ' + threshold + '% or more'));
    els.legend.appendChild(el('span', 'edl-ora-chip edl-ora-not-demonstrated', 'Not Demonstrated below ' + threshold + '%'));
  }

  function setAssessments(assessments) {
    if (els.select.options.length > 1) { return; }  // keep the full list across filtered responses
    assessments.forEach(function (a) { els.select.appendChild(new Option(a.name, a.id)); });
  }

  function renderTable(payload) {
    els.scroll.textContent = '';
    if (!payload.columns.length) {
      els.status.textContent = 'No open response assessments with rubric criteria in this course.';
      return;
    }
    if (!payload.learners.length) {
      els.status.textContent = 'No learners found.';
      return;
    }
    els.status.textContent = '';

    var table = el('table', 'edl-ora-table');
    var head = el('thead');
    var rowC = el('tr');
    var row1 = el('tr');
    var row2 = el('tr');

    var learnerHead = el('th', 'edl-ora-sticky edl-ora-learner-head', 'Learner');
    learnerHead.rowSpan = 3;
    learnerHead.scope = 'col';
    rowC.appendChild(learnerHead);

    var starts = payload.columns.map(function (c, k) { return k === 0 || payload.columns[k - 1].block_id !== c.block_id; });

    var j = 0;
    while (j < payload.columns.length) {
      var competency = payload.columns[j].competency;
      var cStart = j;
      while (j < payload.columns.length && payload.columns[j].competency === competency) { j += 1; }
      var comp = el('th', 'edl-ora-competency');
      comp.appendChild(el('span', 'edl-ora-group-label', competency));
      // One extra "Date taken" column per assessment inside this competency.
      var assessmentCount = starts.slice(cStart, j).filter(Boolean).length;
      comp.colSpan = (j - cStart) + assessmentCount;
      comp.scope = 'colgroup';
      rowC.appendChild(comp);
    }

    var i = 0;
    while (i < payload.columns.length) {
      var blockId = payload.columns[i].block_id;
      var start = i;
      while (i < payload.columns.length && payload.columns[i].block_id === blockId) { i += 1; }
      var group = el('th', 'edl-ora-group');
      group.appendChild(el('span', 'edl-ora-group-label', payload.columns[start].assessment));
      group.colSpan = (i - start) + 1;  // plus the "Date taken" column
      group.scope = 'colgroup';
      row1.appendChild(group);
    }
    payload.columns.forEach(function (c, idx) {
      if (starts[idx]) {
        var dateHead = el('th', 'edl-ora-date-head edl-ora-group-start', 'Date taken');
        dateHead.scope = 'col';
        row2.appendChild(dateHead);
      }
      var th = el('th', 'edl-ora-criterion', c.criterion);
      th.scope = 'col';
      row2.appendChild(th);
    });
    head.appendChild(rowC);
    head.appendChild(row1);
    head.appendChild(row2);
    table.appendChild(head);

    var body = el('tbody');
    payload.learners.forEach(function (learner) {
      var tr = el('tr');
      var th = el('th', 'edl-ora-sticky edl-ora-learner');
      th.scope = 'row';
      th.appendChild(el('strong', null, learner.name));
      th.appendChild(el('div', 'edl-ora-sub', learner.username));
      th.appendChild(el('div', 'edl-ora-sub', learner.email));
      tr.appendChild(th);
      learner.cells.forEach(function (cell, idx) {
        if (starts[idx]) {
          var dateTd = el('td', 'edl-ora-date edl-ora-group-start');
          var info = (learner.dates || {})[payload.columns[idx].block_id];
          if (info && info.date) {
            dateTd.appendChild(el('div', 'edl-ora-date-text', info.date));
            if (info.note) { dateTd.appendChild(el('div', 'edl-ora-date-note', info.note)); }
          } else {
            dateTd.classList.add('edl-ora-date-none');
            dateTd.textContent = '-';
          }
          tr.appendChild(dateTd);
        }
        var td = el('td');
        if (cell === null) {
          td.className = 'edl-ora-empty';
        } else {
          var demonstrated = cell.status === 'demonstrated';
          td.className = demonstrated ? 'edl-ora-demonstrated' : 'edl-ora-not-demonstrated';
          td.appendChild(el('div', 'edl-ora-pct', cell.percent + '%'));
          td.appendChild(el('div', 'edl-ora-label', demonstrated ? 'Demonstrated' : 'Not Demonstrated'));
        }
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
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
    var first = payload.total ? (payload.page - 1) * payload.page_size + 1 : 0;
    var last = Math.min(payload.page * payload.page_size, payload.total);
    els.footer.appendChild(el('span', 'edl-ora-info', 'Showing learners ' + first + ' to ' + last + ' of ' + payload.total));

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

  function fetchPage() {
    var host = root();
    if (!host) { return; }
    var url = host.getAttribute('data-data-url');
    if (!url) { return; }

    state.requestId += 1;
    var requestId = state.requestId;
    var params = new URLSearchParams({
      page: state.page, page_size: state.pageSize, q: state.q, assessment: state.assessment
    });
    els.status.textContent = 'Loading...';

    fetch(url + '?' + params.toString(), {credentials: 'same-origin'})
      .then(function (response) {
        if (!response.ok) { throw new Error('HTTP ' + response.status); }
        return response.json();
      })
      .then(function (payload) {
        if (requestId !== state.requestId) { return; }  // a newer request replaced this one
        state.page = payload.page;
        setLegend(payload.threshold);
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
    host.appendChild(el('h3', null, 'Assessment scores'));
    host.appendChild(el('p', 'edl-ora-intro',
      'Scores for each rubric criterion in every open response assessment. Demonstrated means ' +
      config.threshold + '% or more.'));
    var download = el('a', 'btn btn-primary edl-ora-download', 'Download All Scores (CSV)');
    download.href = config.csvUrl || '#';
    host.appendChild(download);
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
