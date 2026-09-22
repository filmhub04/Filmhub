(() => {
  'use strict';

  const FH = String(window.FILMHUB_API || '').replace(/\/+$/, '');

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const el = {
    navbar: $('#navbar'),
    searchForm: $('#search-form'),
    searchInput: $('#search-input'),
    searchYear: $('#search-year'),
    home: $('#view-home'),
    search: $('#view-search'),
    library: $('#view-library'),
    downloads: $('#view-downloads'),
    modal: $('#movie-modal'),
    modalClose: $('#modal-close'),
    modalContent: $('#modal-content'),
    overlay: $('#overlay'),
    heroBackdrop: $('#hero-backdrop'),
    toastContainer: $('#toast-container'),
    loading: $('#loading-overlay'),
    navTabs: $$('.nav-tab[data-nav]'),
  };

  const VIEWS = ['home', 'search', 'library', 'downloads'];

  const state = {
    view: 'home',
    library: [],
    watchlist: [],
    downloads: [],
    history: new Map(),
    modalData: null,
    downloadTimer: null,
    notifTimer: null,
    _notifStat: new Map(),
    searchAll: [],
    searchQuery: '',
    searchSource: 'all',
    searchQuality: 'all',
    searchById: {},
    libGenre: 'all',
    libSort: 'recent',
    libFavOnly: false,
  };

  const STATUS_FR = {
    downloading: 'Téléchargement',
    completed: 'Terminé',
    error: 'Erreur',
    cancelled: 'Annulé',
    pending: 'En attente',
    active: 'Actif',
    paused: 'En pause',
  };

  function api(path, options = {}) {
    const opts = Object.assign({ method: 'GET', headers: {} }, options);
    return fetch(FH + path, opts).then((res) => {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) return res.json();
      return res.text();
    });
  }

  let toastId = 0;
  function toast(message, type = 'info', ms = 3600) {
    const node = document.createElement('div');
    node.className = 'toast ' + (type || 'info');
    node.textContent = message;
    node.dataset.toast = ++toastId;
    el.toastContainer.appendChild(node);
    setTimeout(() => {
      node.classList.add('out');
      setTimeout(() => node.remove(), 320);
    }, ms);
  }

  function showLoading() { el.loading.classList.remove('hidden'); }
  function hideLoading() { el.loading.classList.add('hidden'); }

  function esc(str) {
    return String(str == null ? '' : str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function formatSize(size) {
    if (size == null || size === '') return '';
    const s = String(size).trim();
    if (!/^\d+(\.\d+)?$/.test(s)) return s;
    const mb = parseFloat(s);
    if (mb < 1024) return Math.round(mb) + ' Mo';
    return (mb / 1024).toFixed(1) + ' Go';
  }

  function initials(title) {
    const clean = String(title || '?').replace(/[^\p{L}\p{N} ]/gu, '').trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (!parts.length) return 'FH';
    if (parts.length === 1) return parts[0].slice(0, 3).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  function posterHtml(item, extra = {}) {
    const title = item.title || 'Film';
    const src = item.poster || extra.poster || '';
    const badge = extra.badge ? `<span class="card-badge">${esc(extra.badge)}</span>` : '';
    const remove = extra.remove
      ? `<button class="card-remove" data-action="remove-watch" data-id="${esc(item.id)}" aria-label="Retirer">×</button>`
      : '';
    const del = extra.delete
      ? `<button class="card-del" data-action="delete-lib" data-id="${esc(item.id)}" aria-label="Supprimer">🗑</button>`
      : '';
    const fav = extra.favorite !== undefined
      ? `<button class="card-fav${extra.favorite ? ' on' : ''}" data-action="fav" data-id="${esc(item.id)}" aria-label="Favori">${extra.favorite ? '♥' : '♡'}</button>`
      : '';
    let labels = extra.subLabels;
    if (typeof labels === 'function') labels = labels(extra.item || {});
    if (labels && !labels.length) labels = null;
    const body = extra.noBody ? '' : `
      <div class="card-body">
        <div class="card-title" title="${esc(title)}">${esc(title)}</div>
        ${labels && labels.length ? `<div class="card-sub">${labels.map((s) => `<span>${esc(s)}</span>`).join('<span>·</span>')}</div>` : ''}
      </div>`;
    const cover = src
      ? `<img class="poster" src="${esc(src)}" alt="${esc(title)}" loading="lazy" onerror="this.remove()">`
      : `<div class="poster-placeholder"><span class="poster-initials">${esc(initials(title))}</span></div>`;
    return `
      <div class="card" role="button" tabindex="0" data-action="${esc(extra.action || 'open')}" data-id="${esc(item.id || extra.fakeId || '')}"
              data-title="${esc(title)}" data-poster="${esc(src)}"
              data-note="${esc(item.note || '')}"
              data-link="${esc(item.link || '')}" data-size="${esc(item.size === undefined ? '' : item.size)}"
              data-seeders="${esc(item.seeders === undefined ? '' : item.seeders)}"
              data-source="${esc(item.source || '')}" data-year="${esc(item.year === undefined ? '' : item.year)}">
        <div class="poster-wrap">
          ${cover}
          ${badge}
          ${fav}
          ${remove}
          ${del}
        </div>
        ${body}
      </div>`;
  }

  function movieCardHtml(item, opts = {}) {
    return posterHtml({
      title: item.title,
      poster: item.poster,
      note: item.note,
      id: item.id || opts.fakeId || String(item.title).toLowerCase().replace(/[^a-z0-9]/g, '-'),
      link: item.link,
      size: item.size,
      seeders: item.seeders,
      source: item.source,
      year: item.year,
    }, {
      action: opts.action || 'open',
      badge: opts.badge,
      remove: opts.remove,
      delete: opts.delete,
      favorite: opts.favorite,
      subLabels: opts.subLabels,
      fakeId: opts.fakeId,
      noBody: opts.noBody,
      item: item,
    });
  }

  /* ------------------------------ Navigation ------------------------------ */

  function switchTab(name) {
    if (!VIEWS.includes(name)) name = 'home';
    if (name !== 'downloads' && state.downloadTimer) {
      clearInterval(state.downloadTimer);
      state.downloadTimer = null;
    }
    state.view = name;
    el.navTabs.forEach((b) => b.classList.toggle('active', b.dataset.nav === name));
    $$('.view').forEach((v) => v.classList.toggle('active', v.dataset.view === name));
    document.body.classList.toggle('has-hero', name === 'home' && state.library.length > 0);
    if (name === 'home') loadHome();
    if (name === 'library') loadLibrary();
    if (name === 'downloads') loadDownloads();
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  el.navTabs.forEach((b) => b.addEventListener('click', () => switchTab(b.dataset.nav)));

  const logoBtn = $('.logo[data-nav]');
  if (logoBtn) logoBtn.addEventListener('click', () => switchTab('home'));

  /* ------------------------------ Search ------------------------------ */

  el.searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    suggestBox.classList.add('hidden');
    const q = el.searchInput.value.trim();
    if (!q) { toast('Saisissez un titre de film.', 'error'); return; }
    doSearch(q, el.searchYear.value.trim());
  });

  /* ------------------------------ Suggestions live ------------------------------ */

  let suggestTimer = null;
  let suggestToken = 0;
  const suggestBox = document.createElement('div');
  suggestBox.className = 'suggest-box hidden';
  el.searchForm.appendChild(suggestBox);

  el.searchInput.addEventListener('input', () => {
    clearTimeout(suggestTimer);
    const q = el.searchInput.value.trim();
    if (q.length < 2) {
      suggestBox.classList.add('hidden');
      return;
    }
    suggestTimer = setTimeout(() => fetchSuggestions(q), 320);
  });

  function fetchSuggestions(q, target = suggestBox) {
    const token = ++suggestToken;
    api('/api/search?q=' + encodeURIComponent(q))
      .then((data) => {
        if (token !== suggestToken) return;
        if (el.searchInput.value.trim() !== q) return;
        const all = (data.results || []).slice().sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
        const seen = new Set();
        const rows = [];
        all.forEach((r) => {
          const t = String(r.title || '').trim().toLowerCase();
          if (seen.has(t)) return;
          seen.add(t);
          const year = r.year ? ` (${r.year})` : '';
          rows.push(`
            <button type="button" class="suggest-item" data-title="${esc(r.title)}" data-year="${esc(r.year || '')}">
              <span class="suggest-title">${esc(r.title)}${esc(year)}</span>
              <span class="suggest-meta">${esc(r.source || '')} · ${r.seeders || 0} seeders</span>
            </button>`);
        });
        target.innerHTML = rows.slice(0, 7).join('');
        target.classList.toggle('hidden', !rows.length);
      })
      .catch(() => {
        if (token === suggestToken) target.classList.add('hidden');
      });
  }

  suggestBox.addEventListener('click', (e) => {
    const row = e.target.closest('.suggest-item');
    if (!row) return;
    const title = row.dataset.title || '';
    const year = row.dataset.year || '';
    el.searchInput.value = title;
    if (year) el.searchYear.value = year;
    suggestBox.classList.add('hidden');
    if (title) doSearch(title, year);
  });

  el.searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') suggestBox.classList.add('hidden');
  });
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-form')) suggestBox.classList.add('hidden');
  });

  function doSearch(q, year) {
    switchTab('search');
    el.search.innerHTML = '<div class="welcome"><div><h2>Recherche en cours…</h2></div></div>';
    showLoading();
    state.searchQuery = q;
    state.searchSource = 'all';
    state.searchQuality = 'all';
    let url = FH + '/api/search?q=' + encodeURIComponent(q);
    if (year) url += '&year=' + encodeURIComponent(year);
    api(url)
      .then((data) => {
        const allResults = (data.results || []).slice().sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
        state.searchAll = allResults;
        renderSearchResults();
      })
      .catch(() => {
        errorState();
        toast('Erreur serveur, réessayez.', 'error');
      })
      .finally(hideLoading);
  }

  function errorState() {
    el.search.innerHTML = `
      <div class="empty-state">
        <h3>Erreur serveur</h3>
        <p>Impossible de joindre le serveur. Réessayez dans un instant.</p>
      </div>`;
  }

  function renderSearchResults() {
    const q = state.searchQuery || '';
    let list = state.searchAll || [];
    if (state.searchSource !== 'all') {
      const src = String(state.searchSource).toLowerCase();
      list = list.filter((r) => String(r.source || '').toLowerCase() === src);
    }
    if (state.searchQuality !== 'all') {
      const ql = String(state.searchQuality).toLowerCase();
      list = list.filter((r) => String(r.title || '').toLowerCase().indexOf(ql) !== -1);
    }
    const total = list.length;
    const shown = list.slice(0, 10);
    if (!shown.length) {
      el.search.innerHTML = `
        <div class="empty-state">
          <h3>Aucun résultat</h3>
          <p>Rien trouvé pour « ${esc(q)} ». Essayez un autre titre ou changez de filtre.</p>
        </div>`;
      return;
    }
    state.searchById = {};
    const keys = shown.map(() => 's-' + Math.random().toString(36).slice(2, 8));
    const cards = shown.map((r, i) => {
      const key = keys[i];
      state.searchById[key] = r;
      return movieCardHtml(r, {
        fakeId: key,
        badge: r.year ? String(r.year) : r.source ? r.source.toUpperCase() : 'Film',
        subLabels: [
          r.source,
          r.rating ? `★ ${r.rating}` : '',
          r.size ? formatSize(r.size) : '',
          ((r.seeders || 0) + ' seeders'),
        ].filter(Boolean),
      });
    });
    const sourceOpts = ['all', 'YTS', '1337x', 'PirateBay'].map((s) =>
      `<option value="${s}" ${state.searchSource === s ? 'selected' : ''}>${s === 'all' ? 'Toutes sources' : s}</option>`).join('');
    const qualityOpts = ['all', '720p', '1080p', '2160p'].map((q2) =>
      `<option value="${q2}" ${state.searchQuality === q2 ? 'selected' : ''}>${q2 === 'all' ? 'Toutes qualités' : q2}</option>`).join('');
    el.search.innerHTML = `
      <div class="result-head">
        <div class="page-head">
          <h2>Résultats pour « ${esc(q)} »</h2>
          <span class="py">${shown.length} meilleurs sur ${total} trouvés</span>
        </div>
        <div class="filter-bar">
          <label class="filter-item">
            <span>Source</span>
            <select id="filter-source">${sourceOpts}</select>
          </label>
          <label class="filter-item">
            <span>Qualité</span>
            <select id="filter-quality">${qualityOpts}</select>
          </label>
        </div>
      </div>
      <div class="grid">${cards.join('')}</div>`;
    el.search.querySelector('#filter-source').addEventListener('change', (e) => {
      state.searchSource = e.target.value;
      renderSearchResults();
    });
    el.search.querySelector('#filter-quality').addEventListener('change', (e) => {
      state.searchQuality = e.target.value;
      renderSearchResults();
    });
    wireCards();
    shown.forEach((r, i) => {
      if (r.poster) return;
      const key = keys[i];
      api('/api/poster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: r.title, year: r.year || null }),
      })
        .then((d) => {
          if (!d || !d.poster) return;
          const card = el.search.querySelector('.card[data-id="' + key + '"]');
          if (!card) return;
          const wrap = card.querySelector('.poster-wrap');
          if (!wrap) return;
          const ph = wrap.querySelector('.poster-placeholder');
          if (ph) ph.outerHTML = `<img class="poster" src="${esc(d.poster)}" alt="" loading="lazy">`;
          state.searchById[key].poster = d.poster;
        })
        .catch(() => {});
    });
  }

  /* ------------------------------ Home ------------------------------ */

  function loadHome() {
    el.home.innerHTML = '<div class="welcome"><div><div class="spinner"></div></div></div>';
    Promise.all([
      api('/api/library').catch(() => []),
      api('/api/watchlist').catch(() => []),
      api('/api/downloads').catch(() => []),
      api('/api/history').catch(() => []),
    ])
      .then(([library, watchlist, downloads, history]) => {
        state.library = library.items || [];
        state.watchlist = (watchlist.items || []).map((w) => ({
          id: w.id,
          title: w.title,
          poster: w.poster,
          note: w.note || '',
        }));
        state.downloads = downloads.downloads || [];
        (history.items || []).forEach((h) => {
          if (h.title) state.history.set(h.title, { position: h.position, duration: h.duration });
        });
        renderHome();
      })
      .catch(() => {
        el.home.innerHTML = `
          <div class="empty-state">
            <h3>Erreur serveur</h3>
            <p>Impossible de joindre le serveur. Réessayez dans un instant.</p>
          </div>`;
      });
  }

  function renderHome() {
    document.body.classList.toggle('has-hero', state.library.length > 0);

    if (!state.library.length) {
      el.heroBackdrop.style.backgroundImage = 'none';
      el.home.innerHTML = `
        <section class="welcome">
          <div>
            <div class="stage">
              <div class="stage-deco"></div>
              <div class="stage-deco"></div>
              <div class="stage-front">
                <span class="stage-initials">FH</span>
              </div>
            </div>
            <h2>Bienvenue sur FilmHub</h2>
            <p>Recherchez un film pour commencer : votre bibliothèque, vos téléchargements et votre watchlist seront rassemblés ici.</p>
            <p class="search-hint">Utilisez la barre de recherche en haut de la page et ajoutez l’année si nécessaire.</p>
          </div>
        </section>`;
      return;
    }

    const first = state.library[0];
    el.heroBackdrop.style.backgroundImage = first.poster ? `url("${first.poster.replace(/"/g, '\\"')}")` : 'none';

    const heroPoster = first.poster
      ? `<img class="hero-img" src="${esc(first.poster)}" alt="${esc(first.title)}" onerror="this.style.display='none'">`
      : '';
    const heroMeta = [
      first.size ? formatSize(first.size) : '',
      'HD',
      state.library.length + ' film' + (state.library.length > 1 ? 's' : ''),
    ].filter(Boolean)
      .map((m) => `<span class="hero-badge">${esc(m)}</span>`)
      .join('');

    const toContinue = state.library.filter((l) => state.history.has(l.title));
    const watchRows = state.watchlist.length
      ? state.watchlist.slice(0, 8)
      : [];

    const carousel = (title, items, opts) => `
      <section class="section">
        <div class="section-head">
          <h3 class="section-title">${title}</h3>
          <span class="section-count">${items.length} élément${items.length > 1 ? 's' : ''}</span>
        </div>
        <div class="carousel">
          <button class="carousel-arrow prev" aria-label="Précédent">‹</button>
          <div class="carousel-track" data-track>
            ${items.map((m) => movieCardHtml(m, opts)).join('')}
          </div>
          <button class="carousel-arrow next" aria-label="Suivant">›</button>
        </div>
      </section>`;

    const continueRows = carousel('Reprendre la lecture', toContinue.map((l) => ({
      title: l.title,
      poster: l.poster,
      id: l.id,
      subtitles: l.subtitles,
      stream_url: l.stream_url,
    })), {
      action: 'play',
      badge: 'Reprendre',
      subLabels: ['▶ Reprendre la lecture'],
    });

    const genreRows = (() => {
      const byGenre = {};
      state.library.forEach((l) => {
        const gs = Array.isArray(l.genres) ? l.genres : [];
        gs.forEach((g) => {
          if (!g) return;
          (byGenre[g] = byGenre[g] || []).push(l);
        });
      });
      return Object.keys(byGenre).map((g) =>
        carousel(g, byGenre[g].slice(0, 12).map((l) => ({
          title: l.title, poster: l.poster, id: l.id, _size: l.size,
        })), {
          action: 'play',
          badge: 'Lire',
          subLabels: (l) => (l._size ? [formatSize(l._size)] : []),
        })
      ).join('');
    })();

    el.home.innerHTML = `
      <section class="hero">
        ${heroPoster}
        <div class="hero-overlay">
          <div class="hero-content">
            <h1 class="hero-title">${esc(first.title)}</h1>
            <div class="hero-meta"><span class="hero-badge">À regarder</span>${heroMeta}</div>
            <div class="hero-actions">
              <a class="btn btn-play" href="player.html?id=${encodeURIComponent(first.id)}">▶ Lecture</a>
              <button class="btn btn-download" data-action="open" data-id="${esc(first.id)}"
                      data-title="${esc(first.title)}" data-poster="${esc(first.poster || '')}"
                      data-size="${esc(first.size === undefined ? '' : first.size)}">Télécharger</button>
            </div>
          </div>
        </div>
      </section>
      ${continueRows}
      ${carousel('À regarder', state.library.slice(0, 12).map((l) => ({
        title: l.title, poster: l.poster, id: l.id,
        _size: l.size,
      })), {
        action: 'play',
        badge: 'Lire',
        subLabels: l => (l._size ? [formatSize(l._size)] : []),
      })}
      ${genreRows}
${
          watchRows.length
            ? carousel('Votre watchlist', watchRows.map((w) => ({
                id: w.id, title: w.title, poster: w.poster, note: w.note,
              })), {
                action: 'open-watch',
                remove: true,
                badge: 'Watchlist',
                subLabels: w => (w.note ? [w.note] : ['Sur votre liste']),
              })
            : ''
        }`;

    wireCarousels();
    wireCards();
    autofillMissingPosters(el.home, state.library);
  }

  /* ------------------------------ Carousel wiring ------------------------------ */

  function wireCarousels() {
    $$('.carousel').forEach((car) => {
      const track = car.querySelector('[data-track]');
      if (!track) return;
      car.querySelector('.prev').addEventListener('click', () => {
        track.scrollBy({ left: -car.offsetWidth * 0.7, behavior: 'smooth' });
      });
      car.querySelector('.next').addEventListener('click', () => {
        track.scrollBy({ left: car.offsetWidth * 0.7, behavior: 'smooth' });
      });
    });
  }

  /* ------------------------------ Card actions ------------------------------ */

  function wireCards() {
    $$('.card').forEach((card) => card.addEventListener('click', (e) => {
      if (e.target.closest('.card-remove')) {
        e.stopPropagation();
        const id = e.target.closest('.card-remove').dataset.id;
        removeWatchlist(id);
        return;
      }
      if (e.target.closest('.card-fav')) {
        e.stopPropagation();
        const btn = e.target.closest('.card-fav');
        toggleFavorite(btn.dataset.id, btn);
        return;
      }
      if (e.target.closest('.card-del')) {
        e.stopPropagation();
        const id = e.target.closest('.card-del').dataset.id;
        deleteLibraryItem(id);
        return;
      }
      const action = card.dataset.action || 'open';
      const id = card.dataset.id;
      const title = card.dataset.title || '';
      const poster = card.dataset.poster || '';
      if (action === 'play') {
        window.location.href = 'player.html?id=' + encodeURIComponent(id);
      } else if (action === 'open') {
        const full = state.searchById[id] || {};
        const libItem = state.library.find((l) => String(l.id) === String(id));
        openModal(Object.assign({
          id: '',
          title: '',
          poster: '',
          note: '',
          link: '',
          size: '',
          seeders: '',
          source: '',
          year: '',
          genres: [],
        }, libItem || {}, full));
      } else if (action === 'open-watch') {
        openModal({
          id,
          title,
          poster,
          note: card.dataset.note || '',
          link: card.dataset.link || '',
          size: card.dataset.size || '',
          seeders: card.dataset.seeders || '',
          source: card.dataset.source || '',
          year: card.dataset.year || '',
          watch: true,
        });
      }
    }));
  }

  /* ------------------------------ Modal ------------------------------ */

  function relatedFilms(data) {
    const g = Array.isArray(data.genres) ? data.genres : [];
    if (!g.length || !Array.isArray(state.searchAll) || !state.searchAll.length) return [];
    const scored = [];
    state.searchAll.forEach((r) => {
      if (String(r.title || '') === String(data.title || '')) return;
      const rg = Array.isArray(r.genres) ? r.genres : [];
      const overlap = rg.filter((x) => g.indexOf(x) !== -1).length;
      if (overlap > 0) {
        const rating = Number(r.rating) || 0;
        scored.push({ item: r, score: overlap * 2 + (rating ? rating / 2 : 0) + (r.source === 'YTS' ? 0.5 : 0) });
      }
    });
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, 6).map((s) => s.item);
  }

  function openModal(data) {
    state.modalData = data;
    const src = data.poster || '';
    const cover = src
      ? `<img src="${esc(src)}" alt="${esc(data.title)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='grid'">`
      : '';
    const fallback = `<div class="poster-placeholder" style="${src ? 'display:none' : ''}">
        <span class="poster-initials" style="font-size:44px">${esc(initials(data.title))}</span>
      </div>`;

    const tags = [];
    if (data.year) tags.push(`<span class="tag">${esc(data.year)}</span>`);
    if (data.rating != null && data.rating !== '') tags.push(`<span class="tag tag-rating">★ ${esc(data.rating)}</span>`);
    if (data.runtime != null && data.runtime !== '') tags.push(`<span class="tag">${esc(data.runtime)} min</span>`);
    if (Array.isArray(data.genres) && data.genres.length) {
      data.genres.slice(0, 4).forEach((g) => tags.push(`<span class="tag">${esc(g)}</span>`));
    }
    if (data.source) tags.push(`<span class="tag">Source : ${esc(data.source)}</span>`);
    if (data.size != null && data.size !== '') tags.push(`<span class="tag">${esc(formatSize(data.size))}</span>`);
    if (data.seeders != null && data.seeders !== '') tags.push(`<span class="tag">${data.seeders} seeders</span>`);

    const summary = data.summary ? `<p class="detail-summary">${esc(data.summary)}</p>` : '';

    let actions = '';
    if (data.watch) {
      tags.unshift('<span class="tag">Dans votre watchlist</span>');
      actions = `
          <button class="btn btn-watch" data-action="watch-search">Rechercher ce titre</button>
          <button class="btn btn-ghost" data-action="watch-remove">Retirer de la watchlist</button>`;
    } else if (data.link) {
      const trailerBtn = data.trailer
        ? `<a class="btn btn-ghost" href="${esc(data.trailer)}" target="_blank" rel="noopener">▶ Bande-annonce</a>`
        : '';
      actions = `
          <button class="btn btn-download" data-action="dl">⬇ Télécharger</button>
          <button class="btn btn-ghost" data-action="watchlist">♥ Ajouter à la watchlist</button>
          ${trailerBtn}`;
    } else {
      tags.unshift('<span class="tag">En bibliothèque</span>');
      actions = `
          <a class="btn btn-play btn-watch" href="player.html?id=${encodeURIComponent(data.id || '')}">▶ Lire dans le lecteur</a>
          <button class="btn btn-ghost" data-action="watchlist">♥ Ajouter à la watchlist</button>`;
    }

    const related = relatedFilms(data);
    let relatedHtml = '';
    if (related.length) {
      const slug = String(data.title || 'film').replace(/[^a-z0-9]/gi, '').slice(0, 12);
      const cards = related.map((r, i) => {
        const key = 'r-' + slug + '-' + i;
        state.searchById[key] = r;
        return movieCardHtml(r, {
          fakeId: key,
          badge: r.year ? String(r.year) : r.source || 'Film',
          subLabels: [
            r.rating ? `★ ${r.rating}` : '',
            r.size ? formatSize(r.size) : '',
          ].filter(Boolean),
        });
      });
      relatedHtml = `
        <section class="detail-related">
          <div class="section-head">
            <h3 class="section-title">Films similaires</h3>
            <span class="section-count">${related.length}</span>
          </div>
          <div class="grid grid-tight">${cards.join('')}</div>
        </section>`;
    }

    el.modalContent.innerHTML = `
      <div class="detail">
        ${src ? `<div class="detail-backdrop" style="background-image:url('${src.replace(/"/g, '\\"')}')"></div>` : ''}
        <div class="detail-inner">
          <div class="detail-poster">${cover}${fallback}</div>
          <div class="detail-info">
            <div class="detail-title">${esc(data.title)}</div>
            <div class="modal-tags">${tags.join('')}</div>
            ${data.note ? `<p class="modal-note">${esc(data.note)}</p>` : ''}
            ${summary}
            <div class="modal-actions">${actions}</div>
          </div>
        </div>
        ${relatedHtml}
      </div>`;
    el.modal.classList.remove('hidden');
    el.overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    bindModalActions();
    el.modalContent.querySelectorAll('.card').forEach((card) =>
      card.addEventListener('click', (e) => {
        e.stopPropagation();
        const item = state.searchById[card.dataset.id];
        if (item) openModal(item);
      }));
  }

  function bindModalActions() {
    const dl = el.modalContent.querySelector('[data-action="dl"]');
    if (dl) dl.addEventListener('click', (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = 'Lancement…';
      downloadMovie(state.modalData);
    });
    const wl = el.modalContent.querySelector('[data-action="watchlist"]');
    if (wl) wl.addEventListener('click', (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      addWatchlist(state.modalData, btn);
    });
    const ws = el.modalContent.querySelector('[data-action="watch-search"]');
    if (ws) ws.addEventListener('click', () => {
      const title = state.modalData.title;
      closeModal();
      doSearch(title, '');
    });
    const wr = el.modalContent.querySelector('[data-action="watch-remove"]');
    if (wr) wr.addEventListener('click', () => {
      const id = state.modalData.id;
      closeModal();
      if (id != null && id !== '') removeWatchlist(id);
    });
  }

  function closeModal() {
    el.modal.classList.add('hidden');
    el.overlay.classList.add('hidden');
    document.body.style.overflow = '';
    state.modalData = null;
  }

  el.modalClose.addEventListener('click', closeModal);
  el.overlay.addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !el.modal.classList.contains('hidden')) closeModal();
  });

  /* ------------------------------ Download ------------------------------ */

  function downloadMovie(data) {
    api('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        link: data.link || '',
        title: data.title,
        poster: data.poster || '',
        genres: Array.isArray(data.genres) ? data.genres : [],
      }),
    })
      .then(() => {
        toast('Téléchargement lancé', 'success');
        closeModal();
        ensureDownloadNotifier();
        setTimeout(() => switchTab('downloads'), 1200);
      })
      .catch(() => {
        closeModal();
        toast('Erreur serveur, réessayez', 'error');
      });
  }

  /* ------------------------------ Watchlist ------------------------------ */

  function addWatchlist(data, btn) {
    const note = data.year ? ('Film de ' + data.year) : 'Film';
    api('/api/watchlist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: data.title, poster: data.poster || '', note }),
    })
      .then(() => {
        toast('Ajouté à la watchlist', 'success');
        closeModal();
        setTimeout(() => {
          if (state.view === 'home') loadHome();
        }, 300);
      })
      .catch(() => {
        if (btn) btn.disabled = false;
        toast('Erreur serveur, réessayez', 'error');
      });
  }

  function removeWatchlist(id) {
    api('/api/watchlist/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(() => {
        toast('Retiré de la watchlist', 'info');
        if (state.view === 'home') loadHome();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  /* ------------------------------ Library ------------------------------ */

  function loadLibrary() {
    el.library.innerHTML = '<div class="welcome"><div><div class="spinner"></div></div></div>';
    api('/api/library')
      .then((data) => {
        state.library = data.items || [];
        renderLibrary();
      })
      .catch(() => {
        el.library.innerHTML = `
          <div class="empty-state">
            <h3>Erreur serveur</h3>
            <p>Impossible de joindre le serveur. Réessayez dans un instant.</p>
          </div>`;
      });
  }

  function libFiltered() {
    let list = state.library.slice();
    if (state.libGenre !== 'all') {
      list = list.filter((l) => (Array.isArray(l.genres) ? l.genres : []).includes(state.libGenre));
    }
    if (state.libFavOnly) list = list.filter((l) => l.favorite);
    const byTitle = (a, b) => String(a.title).localeCompare(String(b.title), 'fr');
    const sorters = {
      recent: (a, b) => (b.added || 0) - (a.added || 0),
      title: byTitle,
      year: (a, b) => (b.year || 0) - (a.year || 0) || byTitle(a, b),
      size: (a, b) => (b.size || 0) - (a.size || 0),
    };
    list.sort(sorters[state.libSort] || sorters.recent);
    return list;
  }

  function renderLibrary() {
    if (!state.library.length) {
      el.library.innerHTML = `
        <div class="page-head"><h2>Bibliothèque</h2><span class="py">0 film</span></div>
        <div class="empty-state">
          <h3>Bibliothèque vide</h3>
          <p>Téléchargez un film depuis la recherche ou l’accueil pour l’ajouter ici.</p>
        </div>`;
      return;
    }

    const genres = Array.from(new Set(
      state.library.reduce((acc, l) => acc.concat(Array.isArray(l.genres) ? l.genres : []), [])
    )).filter(Boolean).sort((a, b) => a.localeCompare(b, 'fr'));

    const list = libFiltered();
    const recentlyDownloaded = state.downloads.some((d) => d.status === 'completed');
    const cards = list.map((l) => movieCardHtml({
      title: l.title, poster: l.poster, id: l.id,
    }, {
      action: 'play',
      badge: 'Lire',
      delete: true,
      favorite: !!l.favorite,
      subLabels: (l.year ? [String(l.year)] : []).concat(
        l.subtitles && l.subtitles.length
          ? [l.subtitles.length + ' sous-titre' + (l.subtitles.length > 1 ? 's' : '')]
          : recentlyDownloaded ? ['Sous-titres à récupérer'] : ['Prêt']
      ),
    }));

    const toolbar = `
      <div class="filter-bar">
        <label class="filter-item">Genre
          <select id="lib-genre">
            <option value="all">Tous</option>
            ${genres.map((g) => `<option value="${esc(g)}"${state.libGenre === g ? ' selected' : ''}>${esc(g)}</option>`).join('')}
          </select>
        </label>
        <label class="filter-item">Trier
          <select id="lib-sort">
            <option value="recent"${state.libSort === 'recent' ? ' selected' : ''}>Ajout récent</option>
            <option value="title"${state.libSort === 'title' ? ' selected' : ''}>Titre (A→Z)</option>
            <option value="year"${state.libSort === 'year' ? ' selected' : ''}>Année</option>
            <option value="size"${state.libSort === 'size' ? ' selected' : ''}>Taille</option>
          </select>
        </label>
        <div class="filter-item">
          <span>Favoris</span>
          <button id="lib-fav" class="chip${state.libFavOnly ? ' on' : ''}" type="button">♥ Favoris seulement</button>
        </div>
        <span class="lib-result">${list.length} / ${state.library.length}</span>
      </div>`;

    el.library.innerHTML = `
      <div class="page-head">
        <h2>Bibliothèque</h2>
        <span class="py">${state.library.length} film${state.library.length > 1 ? 's' : ''}</span>
      </div>
      ${toolbar}
      ${list.length
        ? `<div class="grid">${cards.join('')}</div>`
        : `<div class="empty-state"><h3>Aucun résultat</h3><p>Essayez un autre genre ou désactivez le filtre favoris.</p></div>`}`;

    const genreSel = $('#lib-genre');
    const sortSel = $('#lib-sort');
    const favBtn = $('#lib-fav');
    if (genreSel) genreSel.addEventListener('change', () => { state.libGenre = genreSel.value; renderLibrary(); });
    if (sortSel) sortSel.addEventListener('change', () => { state.libSort = sortSel.value; renderLibrary(); });
    if (favBtn) favBtn.addEventListener('click', () => { state.libFavOnly = !state.libFavOnly; renderLibrary(); });

    wireCards();
    autofillMissingPosters(el.library, list);
  }

  function cleanFilmTitle(raw) {
    return String(raw)
      .replace(/\[[^\]]*\]/gi, ' ')
      .replace(/[._-]+/g, ' ')
      .replace(/\b(19|20)\d{2}\b/gi, ' ')
      .replace(/\b(720p|1080p|2160p|4k|bluray|brrip|webrip|web-?dl|hdtv|hdr|hevc|x264|x265|aac|ac3|yify|yts|rarbg|torrent)\b/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function autofillMissingPosters(rootEl, items) {
    const busy = (state._libBusy = state._libBusy || []);
    items.forEach((item) => {
      if (item.poster || busy.indexOf(item.id) >= 0) return;
      busy.push(item.id);
      api('/api/poster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: cleanFilmTitle(item.title), year: null }),
      })
        .then((d) => {
          if (!d || !d.poster) return;
          item.poster = d.poster;
          api('/api/library/' + item.id + '/poster', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ poster: d.poster }),
          }).catch(() => {});
          const card = rootEl.querySelector('.card[data-id="' + item.id + '"]');
          if (card) {
            const wrap = card.querySelector('.poster-wrap');
            if (wrap) {
              const ph = wrap.querySelector('.poster-placeholder');
              if (ph) {
                ph.outerHTML = `<img class="poster" src="${esc(d.poster)}" alt="" loading="lazy">`;
              }
            }
          }
          if (state.library[0] && state.library[0].id === item.id) {
            el.heroBackdrop.style.backgroundImage = `url("${d.poster.replace(/"/g, '\\"')}")`;
          }
        })
        .catch(() => {});
    });
  }

  /* ------------------------------ Downloads ------------------------------ */

  function loadDownloads() {
    api('/api/downloads')
      .then((data) => {
        state.downloads = data.downloads || [];
        renderDownloads();
        scheduleDownloadRefresh();
      })
      .catch(() => {
        el.downloads.innerHTML = `
          <div class="page-head"><h2>Téléchargements</h2></div>
          <div class="empty-state"><h3>Erreur serveur</h3><p>Impossible de joindre le serveur.</p></div>`;
      });
  }

  function renderDownloads() {
    const list = state.downloads.slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    const rows = list.map((d) => {
      const pct = Math.max(0, Math.min(100, Math.round(Number(d.progress) || 0)));
      let status = STATUS_FR[d.status] || d.status;
      if ((d.status === 'downloading' || d.status === 'active' || d.status === 'pending') && pct === 0) {
        status = 'En attente de pairs…';
      }
      const thumb = d.poster
        ? `<img src="${esc(d.poster)}" alt="${esc(d.title)}" onerror="this.outerHTML=''">`
        : esc(initials(d.title));
      const canCancel = d.status === 'downloading' || d.status === 'active' || d.status === 'pending';
      const isActive = canCancel;
      const canResume = d.status === 'paused' || d.status === 'error';
      const finished = d.status === 'completed';
      const err = d.error ? `<span class="dl-error">${esc(d.error)}</span>` : '';
      const doneAt = d.completed_at ? new Date(d.completed_at).toLocaleString('fr-FR') : '';
      const dlMeta = [
        d.size ? formatSize(d.size) : '',
        d.speed ? `Vitesse : ${esc(d.speed)}` : '',
        d.eta ? `Reste : ${esc(d.eta)}` : '',
        doneAt ? `Terminé le ${doneAt}` : `Lancé le ${esc(new Date(d.created_at).toLocaleString('fr-FR'))}`,
      ].filter(Boolean);
      const dlActions = [];
      if (isActive) {
        dlActions.push(`<button class="btn btn-sm btn-ghost" data-action="pause" data-id="${esc(d.id)}">⏸ Pause</button>`);
        dlActions.push(`<button class="btn btn-sm btn-cancel" data-action="cancel" data-id="${esc(d.id)}">Annuler</button>`);
      }
      if (canResume) {
        dlActions.push(`<button class="btn btn-sm btn-cancel" data-action="resume" data-id="${esc(d.id)}">↻ Reprendre</button>`);
        dlActions.push(`<button class="btn btn-sm btn-danger" data-action="del" data-id="${esc(d.id)}">Supprimer</button>`);
      }
      if (finished || d.status === 'cancelled') {
        dlActions.push(`<button class="btn btn-sm btn-danger" data-action="del" data-id="${esc(d.id)}">Supprimer</button>`);
      }
      return `
        <div class="dl-row">
          <div class="dl-thumb">${thumb}</div>
          <div class="dl-main">
            <div class="dl-top">
              <span class="dl-title">${esc(d.title)}</span>
              <span class="dl-status ${esc(d.status || 'pending')}">${esc(status)}</span>
            </div>
            <div class="dl-progress-wrap">
              <div class="progress-track"><div class="progress-bar" style="width:${pct}%"></div></div>
              <span class="dl-pct">${pct}%</span>
            </div>
            <div class="dl-foot">
              <div class="dl-sub">
                <span class="dl-sub-line">${dlMeta.join(' · ')}</span>
                ${err}
              </div>
              <div class="dl-actions">
                ${dlActions.join('')}
              </div>
            </div>
          </div>
        </div>`;
    });

    el.downloads.innerHTML = `
      <div class="page-head">
        <h2>Téléchargements</h2>
        <span class="py">${list.length} téléchargement${list.length > 1 ? 's' : ''}</span>
        <button id="cleanup-btn" class="btn btn-sm btn-ghost" type="button">Nettoyer les résidus</button>
      </div>
      <div class="download-list">${rows.length ? rows.join('') :
        '<div class="empty-state"><h3>Aucun téléchargement</h3><p>Lancez un téléchargement depuis la recherche d’un film.</p></div>'}</div>`;

    el.downloads.querySelectorAll('[data-action="cancel"]').forEach((b) =>
      b.addEventListener('click', () => cancelDownload(b.dataset.id)));
    el.downloads.querySelectorAll('[data-action="pause"]').forEach((b) =>
      b.addEventListener('click', () => pauseDownload(b.dataset.id)));
    el.downloads.querySelectorAll('[data-action="resume"]').forEach((b) =>
      b.addEventListener('click', () => resumeDownload(b.dataset.id)));
    el.downloads.querySelectorAll('[data-action="del"]').forEach((b) =>
      b.addEventListener('click', () => deleteDownloadRow(b.dataset.id)));

    const cleanBtn = $('#cleanup-btn');
    if (cleanBtn) cleanBtn.addEventListener('click', runCleanup);
  }

  function runCleanup() {
    toast('Analyse des résidus…', 'info', 1400);
    api('/api/cleanup')
      .then((d) => {
        const aria = (d && d.aria2) || [];
        const dups = (d && d.duplicates) || [];
        if (!aria.length && !dups.length) {
          toast('Aucun résidu à nettoyer', 'success');
          return;
        }
        const lines = [];
        if (aria.length) lines.push(aria.length + ' fichier(s) .aria2 orphelin(s)');
        if (dups.length) lines.push(dups.length + ' téléchargement(s) en double');
        if (!confirm('Nettoyer :\n- ' + lines.join('\n- ') + '\n\nContinuer ?')) return;
        return api('/api/cleanup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            aria2: aria.map((a) => a.path),
            download_ids: dups.map((x) => x.id),
          }),
        }).then((r) => {
          toast(`Nettoyage : ${r.deleted_files || 0} fichier(s), ${r.deleted_downloads || 0} téléchargement(s)`, 'success');
          loadDownloads();
        });
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function ensureDownloadNotifier() {
    if (state.notifTimer) return;
    state.notifTimer = setInterval(() => {
      api('/api/downloads')
        .then((data) => {
          const list = data.downloads || [];
          list.forEach((d) => {
            const idKey = String(d.id);
            const prev = state._notifStat.get(idKey);
            if (prev && prev !== d.status && d.status === 'completed') {
              toast(d.title + ' est terminé et disponible dans la bibliothèque.', 'success', 7000);
            } else if (prev && prev !== d.status && d.status === 'error') {
              toast(d.title + ' a rencontré une erreur.', 'error', 7000);
            } else if (prev && prev !== d.status && d.status === 'cancelled') {
              toast(d.title + ' a été annulé.', 'info', 5000);
            } else if (prev && prev !== d.status && d.status === 'paused') {
              toast(d.title + ' mis en pause.', 'info', 4000);
            }
            state._notifStat.set(idKey, d.status);
          });
          state.downloads = list;
          if (state.view === 'downloads') renderDownloads();
          const stillActive = list.some((d) =>
            d.status === 'downloading' || d.status === 'active' || d.status === 'pending');
          if (!list.length || !stillActive) {
            clearInterval(state.notifTimer);
            state.notifTimer = null;
          }
        })
        .catch(() => {});
    }, 4000);
  }

  function cancelDownload(id) {
    api('/api/downloads/' + encodeURIComponent(id) + '/cancel', { method: 'POST' })
      .then(() => {
        toast('Téléchargement annulé', 'info');
        return api('/api/downloads');
      })
      .then((data) => {
        state.downloads = data.downloads || [];
        renderDownloads();
        scheduleDownloadRefresh();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function pauseDownload(id) {
    api('/api/downloads/' + encodeURIComponent(id) + '/pause', { method: 'POST' })
      .then(() => {
        toast('Téléchargement en pause', 'info');
        return api('/api/downloads');
      })
      .then((data) => {
        state.downloads = data.downloads || [];
        renderDownloads();
        scheduleDownloadRefresh();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function resumeDownload(id) {
    api('/api/downloads/' + encodeURIComponent(id) + '/resume', { method: 'POST' })
      .then(() => {
        toast('Réactivation du téléchargement', 'success');
        ensureDownloadNotifier();
        return api('/api/downloads');
      })
      .then((data) => {
        state.downloads = data.downloads || [];
        renderDownloads();
        scheduleDownloadRefresh();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function deleteDownloadRow(id) {
    if (!confirm('Retirer ce téléchargement de la liste ?')) return;
    api('/api/downloads/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(() => {
        state.downloads = state.downloads.filter((d) => String(d.id) !== String(id));
        toast('Téléchargement retiré', 'success');
        renderDownloads();
        scheduleDownloadRefresh();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function toggleFavorite(id, btn) {
    api('/api/library/' + encodeURIComponent(id) + '/favorite', { method: 'POST' })
      .then((d) => {
        if (!d || d.status !== 'ok') throw new Error('bad');
        const item = state.library.find((l) => String(l.id) === String(id));
        if (item) item.favorite = d.favorite;
        if (btn) {
          btn.classList.toggle('on', !!d.favorite);
          btn.textContent = d.favorite ? '♥' : '♡';
        }
        toast(d.favorite ? 'Ajouté aux favoris' : 'Retiré des favoris', 'success', 1600);
        if (state.view === 'library' && state.libFavOnly) renderLibrary();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function deleteLibraryItem(id) {
    if (!confirm('Supprimer ce fichier de la bibliothèque ?\nLe fichier vidéo et ses sous-titres seront effacés du disque.')) return;
    api('/api/library/' + encodeURIComponent(id), { method: 'DELETE' })
      .then(() => {
        toast('Fichier supprimé du disque', 'success');
        state.library = state.library.filter((l) => String(l.id) !== String(id));
        renderLibrary();
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'));
  }

  function scheduleDownloadRefresh() {
    const hasActive = state.downloads.some((d) =>
      d.status === 'downloading' || d.status === 'active' || d.status === 'pending');
    if (state.downloadTimer) {
      clearInterval(state.downloadTimer);
      state.downloadTimer = null;
    }
    if (hasActive && state.view === 'downloads') {
      state.downloadTimer = setInterval(() => {
        api('/api/downloads')
          .then((data) => {
            state.downloads = data.downloads || [];
            renderDownloads();
            const stillActive = state.downloads.some((d) =>
              d.status === 'downloading' || d.status === 'active' || d.status === 'pending');
            if (!stillActive) {
              clearInterval(state.downloadTimer);
              state.downloadTimer = null;
            }
          })
          .catch(() => {
            clearInterval(state.downloadTimer);
            state.downloadTimer = null;
            toast('Erreur serveur, réessayez', 'error');
          });
      }, 2000);
    }
  }

  /* ------------------------------ Init ------------------------------ */

  ensureDownloadNotifier();
  if (window.location.hash === '#downloads') switchTab('downloads');
  else if (window.location.hash === '#library') switchTab('library');
  else switchTab('home');
})();