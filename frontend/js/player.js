(() => {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const FH = String(window.FILMHUB_API || '').replace(/\/+$/, '');
  const abs = (u) => (u && String(u).startsWith('/') ? FH + u : u);

  const el = {
    video: $('#video'),
    title: $('#player-title'),
    subsBtn: $('#subs-btn'),
    hint: $('#player-hint'),
    toastContainer: $('#toast-container'),
    loading: $('#loading-overlay'),
    seekBack: $('#seek-back'),
    seekFwd: $('#seek-fwd'),
    speed: $('#speed-select'),
  };

  const params = new URLSearchParams(window.location.search);
  const id = params.get('id') || '';

  let currentItem = null;
  let subsBusy = false;
  let lastSave = 0;

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

  /* ------------------------- Tracks ------------------------- */

  function langLabel(lang) {
    const map = {
      fra: 'Français', fr: 'Français', 'fr-FR': 'Français',
      ara: 'Arabe', ar: 'Arabe',
      eng: 'Anglais', en: 'Anglais',
    };
    return map[String(lang).toLowerCase()] || lang || 'Sous-titres';
  }

  function buildTracks(defaultActiveFra) {
    el.video.querySelectorAll('track').forEach((t) => t.remove());
    if (!currentItem || !Array.isArray(currentItem.subtitles) || !currentItem.subtitles.length) return 0;
    const extended = currentItem.subtitles.map((s) => ({
      lang: s.lang || s.alpha3 || 'unk',
      alpha3: s.alpha3 || s.lang || 'unk',
      url: s.url,
    }));
    if (defaultActiveFra) {
      const fra = extended.find((s) => /fra|fr/i.test(s.lang));
      if (fra) fra.def = true;
    }
    extended.forEach((s, i) => {
      const t = document.createElement('track');
      t.kind = 'subtitles';
      t.label = langLabel(s.lang);
      t.srclang = s.alpha3;
      if (s.def) t.default = true;
      t.src = abs(s.url);
      el.video.appendChild(t);
    });
    return extended.length;
  }

  function activateDefaultTrack() {
    const activate = () => {
      const tracks = el.video.textTracks;
      for (let i = 0; i < tracks.length; i++) {
        if (/fra|fr/i.test(tracks[i].language || '')) tracks[i].mode = 'showing';
      }
    };
    activate();
    Array.from(el.video.querySelectorAll('track')).forEach((tr) => {
      tr.addEventListener('load', activate, { once: true });
    });
  }

  function reloadTracks() {
    const count = buildTracks(true);
    activateDefaultTrack();
    el.hint.textContent = count
      ? `${count} piste${count > 1 ? 's' : ''} de sous-titres disponibles. Utilisez « CC » dans le lecteur.`
      : 'Les sous-titres sont disponibles dès qu\'ils sont téléchargés. Cliquez sur « Sous-titres FR/AR » pour les récupérer.';
  }

  async function fetchLibraryItem() {
    const data = await api('/api/library');
    return (data.items || []).find((it) => String(it.id) === String(id)) || null;
  }

  /* ------------------------- Sous-titres FR/AR ------------------------- */

  function requestSubtitles() {
    if (subsBusy) return;
    subsBusy = true;
    el.subsBtn.disabled = true;
    toast('Recherche de sous-titres…', 'info');
    api('/api/library/' + encodeURIComponent(id) + '/subtitles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ languages: ['fra', 'ara'] }),
    })
      .then(() => {
        toast('Recherche de sous-titres lancée', 'success');
        return new Promise((resolve) => setTimeout(resolve, 5000));
      })
      .then(async () => {
        const keep = el.video.currentTime;
        currentItem = await fetchLibraryItem();
        reloadTracks();
        el.video.currentTime = keep;
      })
      .catch(() => toast('Erreur serveur, réessayez', 'error'))
      .finally(() => {
        subsBusy = false;
        el.subsBtn.disabled = false;
      });
  }

  el.subsBtn.addEventListener('click', requestSubtitles);

  /* ------------------------- Controles: ±10 s et vitesse ------------------------- */

  function seekBy(seconds) {
    const v = el.video;
    if (!v || isNaN(v.currentTime)) return;
    v.currentTime = Math.max(0, v.currentTime + seconds);
  }

  el.seekBack.addEventListener('click', () => seekBy(-10));
  el.seekFwd.addEventListener('click', () => seekBy(10));
  el.speed.addEventListener('change', () => {
    const val = parseFloat(el.speed.value);
    if (isFinite(val) && val > 0) el.video.playbackRate = val;
  });
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === 'ArrowLeft') { seekBy(-10); e.preventDefault(); }
    if (e.key === 'ArrowRight') { seekBy(10); e.preventDefault(); }
  });

  /* ------------------------- Historique ------------------------- */

  function loadHistory() {
    return api('/api/history').catch(() => ({ items: [] }));
  }

  function saveProgress() {
    const v = el.video;
    if (!currentItem || v.duration === Infinity || isNaN(v.duration) || v.duration <= 0) return;
    api('/api/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: currentItem.title,
        poster: currentItem.poster || '',
        position: Math.floor(v.currentTime),
        duration: Math.floor(v.duration),
      }),
    }).catch(() => {});
  }

  el.video.addEventListener('timeupdate', () => {
    const now = Date.now();
    if (now - lastSave >= 5000) {
      lastSave = now;
      saveProgress();
    }
  });

  /* ------------------------- Init ------------------------- */

  async function init() {
    showLoading();
    try {
      currentItem = await fetchLibraryItem();
    } catch (err) {
      hideLoading();
      el.title.textContent = 'Erreur serveur';
      toast('Erreur serveur, réessayez', 'error');
      return;
    }
    if (!currentItem || !currentItem.stream_url) {
      hideLoading();
      el.title.textContent = 'Film introuvable';
      toast('Film introuvable dans la bibliothèque', 'error');
      return;
    }
    el.title.textContent = currentItem.title || 'Film';
    document.title = (currentItem.title || 'Film') + ' — FilmHub';
    el.subsBtn.classList.remove('hidden');

    buildTracks(true);

    const history = await loadHistory();
    const entry = (history.items || []).find((h) => h.title === currentItem.title);
    const resumeAt = (entry && typeof entry.position === 'number' &&
      typeof entry.duration === 'number' && entry.position < entry.duration - 5)
      ? entry.position
      : 0;

    el.video.src = abs(currentItem.stream_url);

    const applyResume = () => {
      if (resumeAt > 0) { try { el.video.currentTime = resumeAt; } catch (e) {} }
    };
    if (el.video.readyState >= 1) applyResume();
    else el.video.addEventListener('loadedmetadata', applyResume, { once: true });

    activateDefaultTrack();
    el.video.play().catch(() => {});
    hideLoading();
  }

  init();
})();