/**
 * Client-side Settings tab switching — avoids full page reloads and keeps
 * the same fade-up motion as other pages (.page-enter).
 */
(function () {
    'use strict';

    function getTabFromUrl() {
        return (new URLSearchParams(window.location.search).get('tab') || 'users').trim().toLowerCase();
    }

    function switchSettingsTab(tab, options) {
        options = options || {};
        tab = tab || 'users';

        document.querySelectorAll('.settings-tab-panel').forEach(function (panel) {
            panel.classList.add('d-none');
            panel.classList.remove('settings-tab-panel-enter');
        });

        document.querySelectorAll('.settings-tab-link[data-settings-tab]').forEach(function (link) {
            var isActive = link.getAttribute('data-settings-tab') === tab;
            link.classList.toggle('active', isActive);
            link.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        var panel = document.getElementById('settingsTabPanel-' + tab);
        if (panel) {
            panel.classList.remove('d-none');
            if (!options.skipAnimation) {
                void panel.offsetWidth;
                panel.classList.add('settings-tab-panel-enter');
            }
        }

        var subtitle = document.getElementById('settingsPageSubtitle');
        var activeLink = document.querySelector('.settings-tab-link[data-settings-tab="' + tab + '"]');
        if (subtitle && activeLink) {
            subtitle.textContent = activeLink.getAttribute('data-settings-subtitle') || '';
        }

        if (window.__settingsInitialData) {
            window.__settingsInitialData.active_tab = tab;
        }

        if (typeof window.activateSettingsTabUI === 'function') {
            window.activateSettingsTabUI(tab);
        }

        if (tab === 'assets' && typeof loadAssetTypes === 'function') {
            var needsAssets = !window.assetTypesData || !window.assetTypesData.length;
            if (needsAssets) {
                Promise.all([loadAssetTypes(), loadAssetNames()]).then(function () {
                    if (typeof updateAssetNameDropdowns === 'function') {
                        updateAssetNameDropdowns();
                    }
                }).catch(function () {});
            }
        }
    }

    window.switchSettingsTab = switchSettingsTab;

    document.addEventListener('DOMContentLoaded', function () {
        if (!document.querySelector('.settings-page')) return;

        document.querySelectorAll('.settings-tab-link[data-settings-tab]').forEach(function (link) {
            link.addEventListener('click', function (event) {
                event.preventDefault();
                var tab = link.getAttribute('data-settings-tab');
                switchSettingsTab(tab);
                history.pushState({ settingsTab: tab }, '', link.href);
            });
        });

        window.addEventListener('popstate', function (event) {
            var tab = (event.state && event.state.settingsTab) || getTabFromUrl();
            switchSettingsTab(tab);
        });
    });
})();
