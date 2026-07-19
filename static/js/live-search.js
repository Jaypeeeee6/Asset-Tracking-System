/**
 * Live search: update results table/list via AJAX (no full page reload).
 * Debounces input; Enter refreshes immediately; pagination/sort links inside
 * the results container are intercepted and fetched the same way.
 */
(function (global) {
    'use strict';

    function resolveEl(ref) {
        if (!ref) return null;
        if (typeof ref === 'string') return document.getElementById(ref);
        return ref;
    }

    function syncFormFromUrl(form, url) {
        if (!form || !url) return;
        url.searchParams.forEach(function (value, key) {
            if (key === 'partial') return;
            var el = form.elements.namedItem(key);
            if (!el) return;
            if (el instanceof RadioNodeList) {
                Array.prototype.forEach.call(el, function (node) {
                    if ('value' in node) node.value = value;
                });
                return;
            }
            if ('value' in el) el.value = value;
        });
    }

    function bindLiveSearchForm(options) {
        var form = resolveEl(options.form);
        var input = resolveEl(options.input);
        var results = resolveEl(options.results);
        if (!form || !input || !results) return;

        var delay = options.delay != null ? options.delay : 280;
        var selectIds = options.selectIds || [];
        var onUpdated = typeof options.onUpdated === 'function' ? options.onUpdated : function () {};
        var timeout = null;
        var abortController = null;
        var requestId = 0;
        var basePath = form.getAttribute('action') || window.location.pathname;

        function buildUrlFromForm(resetPage) {
            var params = new URLSearchParams(new FormData(form));
            if (resetPage) params.set('page', '1');
            var perPageEl = document.getElementById('itemsPerPage');
            if (perPageEl && perPageEl.value && !params.has('per_page')) {
                params.set('per_page', perPageEl.value);
            }
            params.delete('partial');
            var url = new URL(basePath, window.location.origin);
            url.search = params.toString();
            return url;
        }

        function fetchResults(urlLike, opts) {
            opts = opts || {};
            var url = new URL(urlLike, window.location.origin);
            url.searchParams.set('partial', '1');

            var id = ++requestId;
            if (abortController) abortController.abort();
            abortController = new AbortController();

            results.classList.add('is-loading');

            return fetch(url.toString(), {
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/html' },
                signal: abortController.signal,
                credentials: 'same-origin'
            })
                .then(function (response) {
                    if (!response.ok) throw new Error('Search request failed');
                    return response.text();
                })
                .then(function (html) {
                    if (id !== requestId) return;
                    results.innerHTML = html;

                    var hist = new URL(url.toString());
                    hist.searchParams.delete('partial');
                    history.replaceState({}, '', hist.pathname + (hist.search ? hist.search : ''));

                    if (opts.syncForm !== false) {
                        syncFormFromUrl(form, hist);
                    }
                    onUpdated();
                })
                .catch(function (err) {
                    if (err && err.name === 'AbortError') return;
                    console.error(err);
                })
                .finally(function () {
                    if (id === requestId) {
                        results.classList.remove('is-loading');
                    }
                });
        }

        function refreshFromForm(resetPage) {
            fetchResults(buildUrlFromForm(resetPage), { syncForm: false });
        }

        function scheduleRefresh() {
            clearTimeout(timeout);
            timeout = setTimeout(function () {
                refreshFromForm(true);
            }, delay);
        }

        if (input.dataset.liveSearchBound === '1') return;
        input.dataset.liveSearchBound = '1';

        input.addEventListener('input', scheduleRefresh);
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                clearTimeout(timeout);
                refreshFromForm(true);
            }
        });

        selectIds.forEach(function (sid) {
            var sel = document.getElementById(sid);
            if (!sel || sel.dataset.liveSearchBound === '1') return;
            sel.dataset.liveSearchBound = '1';
            sel.addEventListener('change', function () {
                clearTimeout(timeout);
                refreshFromForm(true);
            });
        });

        // Pagination / sort links inside results — fetch partial, don't navigate away
        results.addEventListener('click', function (e) {
            var link = e.target.closest('a[href]');
            if (!link || !results.contains(link)) return;
            if (link.target === '_blank' || link.hasAttribute('download')) return;
            if (link.classList.contains('asset-register-doc-link')) return;

            var href = link.getAttribute('href');
            if (!href || href.charAt(0) === '#') return;

            var abs = new URL(href, window.location.origin);
            if (abs.origin !== window.location.origin) return;
            // Same list page (dashboard / archive / department)
            if (abs.pathname !== window.location.pathname && abs.pathname !== basePath) return;

            e.preventDefault();
            clearTimeout(timeout);
            fetchResults(abs);
        });

        // Rows-per-page control rendered inside results (dashboard)
        results.addEventListener('change', function (e) {
            if (e.target && e.target.id === 'itemsPerPage') {
                clearTimeout(timeout);
                var url = buildUrlFromForm(true);
                url.searchParams.set('per_page', e.target.value);
                url.searchParams.set('page', '1');
                fetchResults(url, { syncForm: false });
            }
        });

        // Expose for jump-to-page helpers
        global.liveSearchFetch = function (urlLike) {
            return fetchResults(urlLike);
        };
        global.liveSearchRefresh = function (resetPage) {
            refreshFromForm(resetPage !== false);
        };
    }

    global.bindLiveSearchForm = bindLiveSearchForm;
})(window);
