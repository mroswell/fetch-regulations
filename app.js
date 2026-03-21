// === Constants ===
const PAGE_SIZE = 50;
const DATA_URL = 'data/json/comments_CDC-2026-0199.json';
const PERSPECTIVE_ORDER = [
  'supportive',
  'mostly-supportive',
  'uncertain',
  'vaccine-hesitant',
  'mRNA-opposed',
  'broadly-opposed'
];
const PERSPECTIVE_LABELS = {
  'supportive': 'Supportive',
  'mostly-supportive': 'Mostly supportive',
  'uncertain': 'Uncertain',
  'vaccine-hesitant': 'Vaccine-hesitant',
  'mRNA-opposed': 'mRNA-opposed',
  'broadly-opposed': 'Broadly opposed'
};

// === State ===
let allComments = [];
let fuseIndex = null;
let searchResults = null;
let allTags = [];      // [{name, count}]
let allVaccines = [];  // [{name, count}]
let highlightedId = null; // single comment view via ?id=

const state = {
  perspective: '',
  vaccineInjured: false,
  hasAttachment: false,
  isOrganization: false,
  tags: [],       // array for multi-select
  vaccine: '',
  search: '',
  name: '',
  sort: 'date',
  page: 1
};

// === DOM refs ===
const $loading = document.getElementById('loading-overlay');
const $loadingText = document.getElementById('loading-text');
const $searchInput = document.getElementById('search-input');
const $nameInput = document.getElementById('name-input');
const $perspectiveSelect = document.getElementById('perspective-select');
const $injuredCheck = document.getElementById('vaccine-injured-check');
const $attachmentCheck = document.getElementById('attachment-check');
const $orgCheck = document.getElementById('organization-check');
const $tagSearch = document.getElementById('tag-search');
const $tagList = document.getElementById('tag-list');
const $tagDropdown = document.getElementById('tag-dropdown');
const $selectedTags = document.getElementById('selected-tags');
const $vaccineSelect = document.getElementById('vaccine-select');
const $clearFilters = document.getElementById('clear-filters');
const $sortSelect = document.getElementById('sort-select');
const $resultsCount = document.getElementById('results-count');
const $cards = document.getElementById('comment-cards');
const $pagination = document.getElementById('pagination');
const $filterToggle = document.getElementById('filter-toggle');
const $filterPanel = document.getElementById('filter-panel');
const $activeFilterCount = document.getElementById('active-filter-count');

// === Data Loading ===
async function loadData() {
  try {
    const resp = await fetch(DATA_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const contentLength = resp.headers.get('content-length');
    if (contentLength && resp.body) {
      const total = parseInt(contentLength, 10);
      const reader = resp.body.getReader();
      let received = 0;
      const chunks = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        received += value.length;
        const mb = (received / 1024 / 1024).toFixed(1);
        const totalMb = (total / 1024 / 1024).toFixed(1);
        $loadingText.textContent = `Downloading… ${mb} / ${totalMb} MB`;
      }

      const blob = new Blob(chunks);
      const text = await blob.text();
      allComments = JSON.parse(text);
    } else {
      allComments = await resp.json();
    }

    // Strip HTML for search
    $loadingText.textContent = 'Preparing search index…';
    for (const r of allComments) {
      r._searchComment = r.comment ? r.comment.replace(/<[^>]*>/g, '') : '';
    }

    // Build Fuse index
    fuseIndex = new Fuse(allComments, {
      keys: [
        { name: '_searchComment', weight: 0.4 },
        { name: 'title', weight: 0.2 },
        { name: 'first_name', weight: 0.15 },
        { name: 'last_name', weight: 0.15 },
        { name: 'organization', weight: 0.1 }
      ],
      threshold: 0.3,
      ignoreLocation: true,
      includeScore: true
    });

    computeAllTags();
    computeAllVaccines();
    populateVaccineSelect();

    // Read state from URL
    readStateFromURL();

    // Initial render
    render();

    // Hide loader
    $loading.classList.add('hidden');
    setTimeout(() => { $loading.style.display = 'none'; }, 300);

  } catch (err) {
    $loadingText.textContent = `Error loading data: ${err.message}`;
  }
}

function computeAllTags() {
  const counts = {};
  for (const r of allComments) {
    if (r.tags) {
      for (const t of String(r.tags).split(',')) {
        const tag = t.trim();
        if (tag) counts[tag] = (counts[tag] || 0) + 1;
      }
    }
  }
  allTags = Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

function computeAllVaccines() {
  const counts = {};
  for (const r of allComments) {
    if (r.vaccines_mentioned) {
      for (const v of String(r.vaccines_mentioned).split(',')) {
        const vac = v.trim();
        if (vac) counts[vac] = (counts[vac] || 0) + 1;
      }
    }
  }
  allVaccines = Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

function populateVaccineSelect() {
  $vaccineSelect.innerHTML = '<option value="">All vaccines</option>';
  for (const v of allVaccines) {
    const opt = document.createElement('option');
    opt.value = v.name;
    opt.textContent = `${v.name} (${v.count})`;
    $vaccineSelect.appendChild(opt);
  }
}

// === URL State ===
function stateToURL() {
  const params = new URLSearchParams();
  if (highlightedId) {
    params.set('id', highlightedId);
    const url = `${location.pathname}?${params.toString()}`;
    history.replaceState(null, '', url);
    return;
  }
  if (state.perspective) params.set('perspective', state.perspective);
  if (state.vaccineInjured) params.set('injured', '1');
  if (state.hasAttachment) params.set('attachment', '1');
  if (state.isOrganization) params.set('org', '1');
  if (state.tags.length) params.set('tags', state.tags.join(','));
  if (state.vaccine) params.set('vaccine', state.vaccine);
  if (state.search) params.set('q', state.search);
  if (state.name) params.set('name', state.name);
  if (state.sort !== 'date') params.set('sort', state.sort);
  if (state.page > 1) params.set('page', state.page);

  const qs = params.toString();
  const url = qs ? `${location.pathname}?${qs}` : location.pathname;
  history.replaceState(null, '', url);
}

function readStateFromURL() {
  const params = new URLSearchParams(location.search);

  highlightedId = params.get('id') || null;

  state.perspective = params.get('perspective') || '';
  state.vaccineInjured = params.get('injured') === '1';
  state.hasAttachment = params.get('attachment') === '1';
  state.isOrganization = params.get('org') === '1';
  state.tags = params.get('tags') ? params.get('tags').split(',') : [];
  state.vaccine = params.get('vaccine') || '';
  state.search = params.get('q') || '';
  state.name = params.get('name') || '';
  state.sort = params.get('sort') || 'date';
  state.page = parseInt(params.get('page'), 10) || 1;

  // Sync UI
  $perspectiveSelect.value = state.perspective;
  $injuredCheck.checked = state.vaccineInjured;
  $attachmentCheck.checked = state.hasAttachment;
  $orgCheck.checked = state.isOrganization;
  $vaccineSelect.value = state.vaccine;
  $searchInput.value = state.search;
  $nameInput.value = state.name;
  $sortSelect.value = state.sort;
  if (state.search) searchResults = null;

  renderSelectedTags();
}

// === Filter Engine ===
function getSearchResults() {
  if (!state.search) return allComments;
  if (searchResults && searchResults._query === state.search) {
    return searchResults._results;
  }
  const results = fuseIndex.search(state.search).map(r => {
    r.item._fuseScore = r.score;
    return r.item;
  });
  searchResults = { _query: state.search, _results: results };
  return results;
}

function applyFilters(records, exclude) {
  return records.filter(r => {
    if (exclude !== 'name' && state.name) {
      const q = state.name.toLowerCase();
      const first = (r.first_name || '').toLowerCase();
      const last = (r.last_name || '').toLowerCase();
      if (!first.includes(q) && !last.includes(q)) return false;
    }
    if (exclude !== 'perspective' && state.perspective && r.perspective !== state.perspective) return false;
    if (exclude !== 'vaccineInjured' && state.vaccineInjured && !r.vaccine_injured) return false;
    if (exclude !== 'hasAttachment' && state.hasAttachment && !r.attachment_urls) return false;
    if (exclude !== 'isOrganization' && state.isOrganization && !r.organization) return false;
    if (exclude !== 'tags' && state.tags.length) {
      const rTags = r.tags ? String(r.tags).split(',').map(t => t.trim()) : [];
      if (!state.tags.every(t => rTags.includes(t))) return false;
    }
    if (exclude !== 'vaccine' && state.vaccine) {
      const vacs = r.vaccines_mentioned ? String(r.vaccines_mentioned).split(',').map(v => v.trim()) : [];
      if (!vacs.includes(state.vaccine)) return false;
    }
    return true;
  });
}

function computeCounts(records) {
  const persp = {};
  let injured = 0, attachment = 0, org = 0;
  const tags = {};
  const vaccines = {};
  for (const r of records) {
    if (r.perspective) persp[r.perspective] = (persp[r.perspective] || 0) + 1;
    if (r.vaccine_injured) injured++;
    if (r.attachment_urls) attachment++;
    if (r.organization) org++;
    if (r.tags) {
      for (const t of String(r.tags).split(',')) {
        const tag = t.trim();
        if (tag) tags[tag] = (tags[tag] || 0) + 1;
      }
    }
    if (r.vaccines_mentioned) {
      for (const v of String(r.vaccines_mentioned).split(',')) {
        const vac = v.trim();
        if (vac) vaccines[vac] = (vaccines[vac] || 0) + 1;
      }
    }
  }
  return { persp, injured, attachment, org, tags, vaccines };
}

// === Rendering ===
function onFilterChange() {
  state.page = 1;
  render();
}

function render() {
  // Single comment view
  if (highlightedId) {
    const comment = allComments.find(r => r.comment_id === highlightedId);
    stateToURL();
    if (comment) {
      $resultsCount.textContent = '';
      $cards.innerHTML = '';
      const backBtn = document.createElement('button');
      backBtn.className = 'back-to-all';
      backBtn.textContent = 'Show all comments';
      backBtn.addEventListener('click', () => {
        highlightedId = null;
        onFilterChange();
      });
      $cards.appendChild(backBtn);
      const card = renderCard(comment);
      card.classList.add('highlighted');
      $cards.appendChild(card);
      $pagination.innerHTML = '';
    } else {
      $resultsCount.textContent = 'Comment not found';
      $cards.innerHTML = '<p style="color:#888;padding:2rem;text-align:center;">Comment not found.</p>';
      $pagination.innerHTML = '';
    }
    return;
  }

  const base = getSearchResults();
  const filtered = applyFilters(base);
  const sorted = sortRecords(filtered);

  updateFilterCounts(base);
  stateToURL();

  $resultsCount.textContent = `${filtered.length.toLocaleString()} comment${filtered.length !== 1 ? 's' : ''}`;

  const start = (state.page - 1) * PAGE_SIZE;
  const pageRecords = sorted.slice(start, start + PAGE_SIZE);
  renderCards(pageRecords);
  renderPagination(filtered.length);
  updateActiveFilterCount();

  const relOpt = $sortSelect.querySelector('option[value="relevance"]');
  relOpt.disabled = !state.search;
  if (!state.search && state.sort === 'relevance') {
    state.sort = 'date';
    $sortSelect.value = 'date';
  }
}

function sortRecords(records) {
  const sorted = [...records];
  switch (state.sort) {
    case 'date':
      sorted.sort((a, b) => (b.posted_date || '').localeCompare(a.posted_date || ''));
      break;
    case 'date-asc':
      sorted.sort((a, b) => (a.posted_date || '').localeCompare(b.posted_date || ''));
      break;
    case 'relevance':
      sorted.sort((a, b) => (a._fuseScore || 1) - (b._fuseScore || 1));
      break;
  }
  return sorted;
}

function updateFilterCounts(base) {
  // Perspective counts
  const perspBase = applyFilters(base, 'perspective');
  const perspCounts = computeCounts(perspBase);
  const currentPersp = $perspectiveSelect.value;
  $perspectiveSelect.innerHTML = '<option value="">All perspectives (' + perspBase.length + ')</option>';
  for (const p of PERSPECTIVE_ORDER) {
    const count = perspCounts.persp[p] || 0;
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = `${PERSPECTIVE_LABELS[p]} (${count})`;
    $perspectiveSelect.appendChild(opt);
  }
  $perspectiveSelect.value = currentPersp;

  // Checkbox counts
  const injuredBase = applyFilters(base, 'vaccineInjured');
  document.getElementById('injured-count').textContent = `(${computeCounts(injuredBase).injured})`;

  const attachBase = applyFilters(base, 'hasAttachment');
  document.getElementById('attachment-count').textContent = `(${computeCounts(attachBase).attachment})`;

  const orgBase = applyFilters(base, 'isOrganization');
  document.getElementById('organization-count').textContent = `(${computeCounts(orgBase).org})`;

  // Tag counts
  const tagBase = applyFilters(base, 'tags');
  const tagCounts = computeCounts(tagBase);
  updateTagList(tagCounts.tags);

  // Vaccine counts
  const vacBase = applyFilters(base, 'vaccine');
  const vacCounts = computeCounts(vacBase);
  updateVaccineSelect(vacCounts.vaccines);
}

function updateVaccineSelect(vacCounts) {
  const currentVal = $vaccineSelect.value;
  $vaccineSelect.innerHTML = '<option value="">All vaccines</option>';
  for (const v of allVaccines) {
    const count = vacCounts[v.name] || 0;
    if (count === 0) continue;
    const opt = document.createElement('option');
    opt.value = v.name;
    opt.textContent = `${v.name} (${count})`;
    $vaccineSelect.appendChild(opt);
  }
  $vaccineSelect.value = currentVal;
}

function updateTagList(tagCounts) {
  $tagList.innerHTML = '';
  const searchVal = $tagSearch.value.toLowerCase();

  for (const t of allTags) {
    const count = tagCounts[t.name] || 0;
    if (searchVal && !t.name.toLowerCase().includes(searchVal)) continue;
    if (state.tags.includes(t.name)) continue; // already selected

    const div = document.createElement('div');
    div.className = 'tag-item' + (count === 0 ? ' disabled' : '');
    div.innerHTML = `<span>${t.name}</span><span class="tag-count">${count}</span>`;
    if (count > 0) {
      div.addEventListener('click', () => addTag(t.name));
    }
    $tagList.appendChild(div);
  }
}

function addTag(name) {
  if (!state.tags.includes(name)) {
    state.tags.push(name);
  }
  $tagSearch.value = '';
  $tagList.hidden = true;
  renderSelectedTags();
  onFilterChange();
}

function removeTag(name) {
  state.tags = state.tags.filter(t => t !== name);
  renderSelectedTags();
  onFilterChange();
}

function clearAllTags() {
  state.tags = [];
  renderSelectedTags();
  onFilterChange();
}

function renderSelectedTags() {
  $selectedTags.innerHTML = '';
  for (const t of state.tags) {
    const chip = document.createElement('span');
    chip.className = 'selected-tag';
    chip.innerHTML = `<span>${escHtml(t)}</span><button aria-label="Remove tag ${t}">&times;</button>`;
    chip.querySelector('button').addEventListener('click', (e) => {
      e.stopPropagation();
      removeTag(t);
    });
    $selectedTags.appendChild(chip);
  }
  $selectedTags.hidden = state.tags.length === 0;
}

function renderCards(records) {
  $cards.innerHTML = '';
  if (records.length === 0) {
    $cards.innerHTML = '<p style="color:#888;padding:2rem;text-align:center;">No comments match your filters.</p>';
    return;
  }
  const frag = document.createDocumentFragment();
  for (const r of records) {
    frag.appendChild(renderCard(r));
  }
  $cards.appendChild(frag);
}

function renderCard(r) {
  const card = document.createElement('article');
  card.className = 'comment-card';

  const perspClass = r.perspective ? `perspective-${r.perspective}` : '';
  const perspLabel = PERSPECTIVE_LABELS[r.perspective] || r.perspective || '';
  const perspBadge = perspLabel ? `<span class="perspective-badge ${perspClass}">${perspLabel}</span>` : '';

  const injuredBadge = r.vaccine_injured ? '<span class="injured-badge">Vaccine Injured</span>' : '';
  const dupBadge = r.duplicate === 'duplicate' ? '<span class="duplicate-badge">Duplicate</span>' : '';

  const name = [r.first_name, r.last_name].filter(Boolean).join(' ');
  const orgHtml = r.organization ? `<span class="org">${escHtml(r.organization)}</span>` : '';
  const dateStr = formatDate(r.posted_date);

  const comment = r.comment || '<em>No comment text</em>';

  const tags = r.tags
    ? String(r.tags).split(',').map(t => `<span class="tag">${escHtml(t.trim())}</span>`).join('')
    : '';

  const attachments = r.attachment_urls
    ? String(r.attachment_urls).split(',').map((url, i) =>
        `<a href="${escAttr(url.trim())}" target="_blank" rel="noopener">Attachment ${i + 1}</a>`
      ).join(' ')
    : '';

  const regLink = r.url
    ? `<a href="${escAttr(r.url)}" target="_blank" rel="noopener" class="reg-link">View on regulations.gov</a>`
    : '';

  card.innerHTML = `
    <div class="card-header">${perspBadge} ${injuredBadge} ${dupBadge} <button class="share-btn" data-id="${escAttr(r.comment_id)}">Share this Comment</button></div>
    <div class="card-meta">
      ${name ? `<strong>${escHtml(name)}</strong>` : ''}
      ${orgHtml}
      <time datetime="${r.posted_date || ''}">${dateStr}</time>
    </div>
    <div class="card-comment">${comment}</div>
    ${tags ? `<div class="card-tags">${tags}</div>` : ''}
    <div class="card-footer">${attachments} ${regLink}</div>
  `;

  card.querySelector('.share-btn').addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const id = btn.dataset.id;
    const url = `${location.origin}${location.pathname}?id=${encodeURIComponent(id)}`;
    navigator.clipboard.writeText(url).then(() => {
      btn.textContent = 'Copied to clipboard!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Share this Comment';
        btn.classList.remove('copied');
      }, 2500);
    });
  });

  return card;
}

function renderPagination(total) {
  $pagination.innerHTML = '';
  const totalPages = Math.ceil(total / PAGE_SIZE);
  if (totalPages <= 1) return;

  const current = state.page;

  function btn(label, page, disabled, active) {
    const b = document.createElement('button');
    b.className = 'page-btn' + (active ? ' active' : '');
    b.textContent = label;
    b.disabled = disabled;
    if (!disabled && !active) {
      b.addEventListener('click', () => {
        state.page = page;
        render();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
    return b;
  }

  $pagination.appendChild(btn('First', 1, current === 1));
  $pagination.appendChild(btn('Prev', current - 1, current === 1));

  const pages = getPageNumbers(current, totalPages);
  for (const p of pages) {
    if (p === '…') {
      const span = document.createElement('span');
      span.className = 'page-ellipsis';
      span.textContent = '…';
      $pagination.appendChild(span);
    } else {
      $pagination.appendChild(btn(String(p), p, false, p === current));
    }
  }

  $pagination.appendChild(btn('Next', current + 1, current === totalPages));
  $pagination.appendChild(btn('Last', totalPages, current === totalPages));
}

function getPageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [];
  if (current <= 4) {
    for (let i = 1; i <= 5; i++) pages.push(i);
    pages.push('…', total);
  } else if (current >= total - 3) {
    pages.push(1, '…');
    for (let i = total - 4; i <= total; i++) pages.push(i);
  } else {
    pages.push(1, '…', current - 1, current, current + 1, '…', total);
  }
  return pages;
}

function updateActiveFilterCount() {
  let count = 0;
  if (state.perspective) count++;
  if (state.vaccineInjured) count++;
  if (state.hasAttachment) count++;
  if (state.isOrganization) count++;
  if (state.tags.length) count++;
  if (state.vaccine) count++;
  if (state.search) count++;
  if (state.name) count++;

  if (count > 0) {
    $activeFilterCount.textContent = count;
    $activeFilterCount.hidden = false;
  } else {
    $activeFilterCount.hidden = true;
  }
}

// === Utilities ===
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function formatDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric', month: 'short', day: 'numeric'
    });
  } catch { return iso; }
}

function escHtml(str) {
  const el = document.createElement('span');
  el.textContent = str;
  return el.innerHTML;
}

function escAttr(str) {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// === Event Handlers ===
$searchInput.addEventListener('input', debounce(() => {
  state.search = $searchInput.value.trim();
  searchResults = null;
  if (state.search) {
    state.sort = 'relevance';
    $sortSelect.value = 'relevance';
  }
  onFilterChange();
}, 300));

$nameInput.addEventListener('input', debounce(() => {
  state.name = $nameInput.value.trim();
  onFilterChange();
}, 300));

$perspectiveSelect.addEventListener('change', () => {
  state.perspective = $perspectiveSelect.value;
  onFilterChange();
});

$injuredCheck.addEventListener('change', () => {
  state.vaccineInjured = $injuredCheck.checked;
  onFilterChange();
});

$attachmentCheck.addEventListener('change', () => {
  state.hasAttachment = $attachmentCheck.checked;
  onFilterChange();
});

$orgCheck.addEventListener('change', () => {
  state.isOrganization = $orgCheck.checked;
  onFilterChange();
});

$vaccineSelect.addEventListener('change', () => {
  state.vaccine = $vaccineSelect.value;
  onFilterChange();
});

$sortSelect.addEventListener('change', () => {
  state.sort = $sortSelect.value;
  state.page = 1;
  render();
});

$clearFilters.addEventListener('click', () => {
  state.perspective = '';
  state.vaccineInjured = false;
  state.hasAttachment = false;
  state.isOrganization = false;
  state.tags = [];
  state.vaccine = '';
  state.search = '';
  state.name = '';
  state.sort = 'date';
  state.page = 1;

  $searchInput.value = '';
  $nameInput.value = '';
  $perspectiveSelect.value = '';
  $injuredCheck.checked = false;
  $attachmentCheck.checked = false;
  $orgCheck.checked = false;
  $vaccineSelect.value = '';
  $sortSelect.value = 'date';
  renderSelectedTags();
  searchResults = null;
  render();
});

// Tag dropdown
$tagSearch.addEventListener('focus', () => { $tagList.hidden = false; });
$tagSearch.addEventListener('input', () => {
  $tagList.hidden = false;
  render();
});

// Close tag dropdown on outside click
document.addEventListener('click', (e) => {
  if (!$tagDropdown.contains(e.target)) {
    $tagList.hidden = true;
  }
});

// Mobile filter toggle
$filterToggle.addEventListener('click', () => {
  const panel = $filterPanel;
  const isOpen = panel.classList.toggle('open');
  $filterToggle.setAttribute('aria-expanded', isOpen);
});

// Browser back/forward
window.addEventListener('popstate', () => {
  readStateFromURL();
  render();
});

// === Init ===
document.addEventListener('DOMContentLoaded', loadData);
