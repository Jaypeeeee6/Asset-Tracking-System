/**
 * Searchable combobox: type in the field to filter, pick from the dropdown list.
 * Panel is fixed to the viewport so it is not clipped by modal overflow.
 */
(function (global) {
    'use strict';

    var VIEWPORT_MARGIN = 8;
    var GAP = 4;
    var PREFERRED_MAX = 220;
    var MIN_PANEL_HEIGHT = 72;

    function create(config) {
        var wrap = document.getElementById(config.wrapId);
        var input = document.getElementById(config.inputId);
        var panel = document.getElementById(config.panelId);
        var hidden = config.hiddenId ? document.getElementById(config.hiddenId) : null;
        if (!wrap || !input || !panel) {
            return null;
        }

        var getOptions = typeof config.getOptions === 'function' ? config.getOptions : function () { return []; };
        var selectedValue = '';
        var selectedLabel = '';
        var panelPlaceholder = null;
        var repositionHandler = null;

        panel.classList.add('app-searchable-combobox-panel--floating');

        function ensurePanelPortaled() {
            if (panel.parentNode === document.body) {
                return;
            }
            panelPlaceholder = document.createComment('app-searchable-combobox-panel');
            wrap.appendChild(panelPlaceholder);
            document.body.appendChild(panel);
        }

        function restorePanelToWrap() {
            if (!panelPlaceholder || panel.parentNode !== document.body) {
                return;
            }
            wrap.insertBefore(panel, panelPlaceholder);
            panelPlaceholder.remove();
            panelPlaceholder = null;
        }

        function positionPanel() {
            ensurePanelPortaled();
            var rect = input.getBoundingClientRect();
            var viewportH = window.innerHeight;
            var spaceBelow = viewportH - rect.bottom - VIEWPORT_MARGIN;
            var spaceAbove = rect.top - VIEWPORT_MARGIN;
            var openBelow = spaceBelow >= MIN_PANEL_HEIGHT || spaceBelow >= spaceAbove;
            var maxHeight = Math.min(
                PREFERRED_MAX,
                Math.max(MIN_PANEL_HEIGHT, (openBelow ? spaceBelow : spaceAbove) - GAP)
            );

            panel.style.position = 'fixed';
            panel.style.left = Math.max(VIEWPORT_MARGIN, rect.left) + 'px';
            panel.style.width = Math.min(rect.width, window.innerWidth - VIEWPORT_MARGIN * 2) + 'px';
            panel.style.maxHeight = maxHeight + 'px';
            panel.style.zIndex = '2000';

            if (openBelow) {
                panel.style.top = (rect.bottom + GAP) + 'px';
                panel.style.bottom = 'auto';
            } else {
                panel.style.top = 'auto';
                panel.style.bottom = (viewportH - rect.top + GAP) + 'px';
            }
        }

        function bindReposition() {
            if (repositionHandler) {
                return;
            }
            repositionHandler = function () {
                if (!panel.hidden) {
                    positionPanel();
                }
            };
            window.addEventListener('resize', repositionHandler);
            window.addEventListener('scroll', repositionHandler, true);
        }

        function unbindReposition() {
            if (!repositionHandler) {
                return;
            }
            window.removeEventListener('resize', repositionHandler);
            window.removeEventListener('scroll', repositionHandler, true);
            repositionHandler = null;
        }

        function renderPanel(query) {
            var options = getOptions();
            var norm = (query || '').trim().toLowerCase();
            panel.innerHTML = '';
            var shown = 0;

            options.forEach(function (opt) {
                var searchText = (opt.searchText || opt.label || '').toLowerCase();
                if (norm && searchText.indexOf(norm) === -1) {
                    return;
                }
                shown += 1;
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'app-searchable-combobox-option dropdown-item';
                btn.setAttribute('role', 'option');
                btn.setAttribute('data-value', opt.value);
                btn.textContent = opt.label || opt.value;
                if (String(opt.value) === String(selectedValue)) {
                    btn.setAttribute('aria-selected', 'true');
                    btn.classList.add('selected');
                }
                btn.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                });
                btn.addEventListener('click', function () {
                    selectOption(opt);
                });
                panel.appendChild(btn);
            });

            if (!shown) {
                var empty = document.createElement('div');
                empty.className = 'app-searchable-combobox-empty text-muted';
                empty.textContent = config.emptyText || 'No matches';
                panel.appendChild(empty);
            }

            panel.hidden = false;
            input.setAttribute('aria-expanded', 'true');
            positionPanel();
            bindReposition();
        }

        function selectOption(opt) {
            selectedValue = opt.value;
            selectedLabel = opt.label || opt.value;
            input.value = selectedLabel;
            if (hidden) hidden.value = selectedValue;
            closePanel();
            if (typeof config.onSelect === 'function') {
                config.onSelect(opt);
            }
        }

        function clearSelection() {
            selectedValue = '';
            selectedLabel = '';
            input.value = '';
            if (hidden) hidden.value = '';
            closePanel();
        }

        function closePanel() {
            panel.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            unbindReposition();
            panel.style.top = '';
            panel.style.bottom = '';
            panel.style.left = '';
            panel.style.width = '';
            panel.style.maxHeight = '';
            restorePanelToWrap();
        }

        function isEventInside(e) {
            var target = e.target;
            return wrap.contains(target) || panel.contains(target);
        }

        input.addEventListener('focus', function () {
            renderPanel(input.value);
        });

        input.addEventListener('input', function () {
            if (selectedLabel && input.value !== selectedLabel) {
                selectedValue = '';
                selectedLabel = '';
                if (hidden) hidden.value = '';
            }
            renderPanel(input.value);
        });

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                closePanel();
                input.blur();
            }
        });

        document.addEventListener('click', function (e) {
            if (panel.hidden) {
                return;
            }
            if (!isEventInside(e)) {
                closePanel();
            }
        });

        return {
            refresh: function () {
                if (!panel.hidden && document.activeElement === input) {
                    renderPanel(input.value);
                }
            },
            reset: clearSelection,
            close: closePanel,
            getValue: function () { return selectedValue; },
            setValue: function (value) {
                var options = getOptions();
                var hit = options.find(function (o) { return String(o.value) === String(value); });
                if (hit) {
                    selectOption(hit);
                } else {
                    clearSelection();
                }
            }
        };
    }

    global.AppSearchableCombobox = { create: create };
})(window);
