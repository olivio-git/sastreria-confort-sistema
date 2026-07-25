// ── Theme toggle ──────────────────────────────────────────────────────────────
(function() {
  var btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', function() {
    var next = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-bs-theme', next);
    localStorage.setItem('sc-theme', next);
  });
})();

// ── Debounce auto-submit para formularios de filtro ──────────────────────────
const AUTO_BUSCAR_KEY = 'auto_buscar';

document.querySelectorAll('[data-debounce]').forEach(function(input) {
  var timer;
  var delay = parseInt(input.dataset.debounce || '400');
  input.addEventListener('input', function() {
    var toggle = document.getElementById('toggleAutoBuscar');
    if (toggle && localStorage.getItem(AUTO_BUSCAR_KEY) === 'false') return;

    clearTimeout(timer);
    timer = setTimeout(function() { input.closest('form').submit(); }, delay);
  });
});

// ── Toggle auto-buscar ────────────────────────────────────────────────────────
var toggleAB = document.getElementById('toggleAutoBuscar');

function syncFilterButtons() {
  var autoBuscar = localStorage.getItem(AUTO_BUSCAR_KEY) !== 'false';
  document.querySelectorAll('[data-filter-btn]').forEach(function(btn) {
    btn.style.display = autoBuscar ? 'none' : '';
  });
}

if (toggleAB) {
  toggleAB.checked = localStorage.getItem(AUTO_BUSCAR_KEY) !== 'false';
  toggleAB.addEventListener('change', function() {
    localStorage.setItem(AUTO_BUSCAR_KEY, toggleAB.checked ? 'true' : 'false');
    syncFilterButtons();
  });
}

syncFilterButtons();

// ── Column toggle ... (resto sin cambios)
// ── Column toggle (mostrar/ocultar columnas) ──────────────────────────────────
document.querySelectorAll('[data-col-toggle]').forEach(function(btn) {
  var tableId = btn.dataset.colToggle;
  var table = document.getElementById(tableId);
  if (!table) return;

  var headers = Array.from(table.querySelectorAll('thead th'));
  var storageKey = 'col-hidden-' + tableId;
  var hidden = JSON.parse(localStorage.getItem(storageKey) || '[]');

  function applyHidden() {
    headers.forEach(function(th, i) {
      var cells = table.querySelectorAll('tr > *:nth-child(' + (i + 1) + ')');
      var isHidden = hidden.includes(i);
      cells.forEach(function(c) { c.style.display = isHidden ? 'none' : ''; });
    });
    localStorage.setItem(storageKey, JSON.stringify(hidden));
  }

  // Build dropdown
  var menu = document.createElement('div');
  menu.className = 'dropdown-menu p-2 col-toggle-menu';
  menu.style.cssText = 'min-width:180px;font-size:.82rem;';
  headers.forEach(function(th, i) {
    if (th.dataset.noToggle !== undefined) return;
    var label = document.createElement('label');
    label.className = 'd-flex align-items-center gap-2 py-1 px-1 rounded cursor-pointer';
    label.style.cursor = 'pointer';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = !hidden.includes(i);
    cb.addEventListener('change', function() {
      if (cb.checked) hidden = hidden.filter(function(x) { return x !== i; });
      else if (!hidden.includes(i)) hidden.push(i);
      applyHidden();
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(' ' + th.textContent.trim()));
    menu.appendChild(label);
  });

  var wrapper = document.createElement('div');
  wrapper.className = 'dropdown d-inline-block';
  btn.parentNode.insertBefore(wrapper, btn);
  wrapper.appendChild(btn);
  btn.setAttribute('data-bs-toggle', 'dropdown');
  btn.setAttribute('aria-expanded', 'false');
  wrapper.appendChild(menu);

  applyHidden();
});

// ── Botón limpiar campo de fecha ──────────────────────────────────────────────
document.addEventListener('click', function(e) {
  var btn = e.target.closest('[data-clear-target]');
  if (!btn) return;
  var target = document.getElementById(btn.dataset.clearTarget);
  if (target) target.value = '';
});

// ── Combobox genérico (carga todos al inicio, filtra localmente) ───────────────
function makeCombobox(input, hiddenId, endpoint) {
  var hidden  = document.getElementById(hiddenId);
  if (!hidden) return;
  var allItems = [];
  var wrapper  = input.parentElement;

  var chevron = document.createElement('span');
  chevron.style.cssText = 'position:absolute;right:0.6rem;top:50%;transform:translateY(-50%);pointer-events:none;color:#6c757d;line-height:1;';
  chevron.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
  wrapper.appendChild(chevron);

  var clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.style.cssText = 'position:absolute;right:0;top:0;height:100%;width:2.2rem;border:none;background:transparent;cursor:pointer;display:none;z-index:2;color:#6c757d;padding:0;';
  clearBtn.title = 'Limpiar selección';
  clearBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  wrapper.appendChild(clearBtn);

  // Dropdown va al body con position:fixed para no quedar recortado por el
  // overflow del contenedor (ej: table-responsive, card-body).
  var dropdown = document.createElement('ul');
  dropdown.className = 'combobox-dropdown';
  dropdown.style.cssText = 'position:fixed;z-index:9999;display:none;margin:0;padding:0;list-style:none;max-height:240px;overflow-y:auto;';
  document.body.appendChild(dropdown);

  function positionDropdown() {
    var rect = input.getBoundingClientRect();
    dropdown.style.top   = (rect.bottom + 2) + 'px';
    dropdown.style.left  = rect.left + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  function syncUI() {
    var has = !!hidden.value;
    clearBtn.style.display = has ? 'block' : 'none';
    chevron.style.display  = has ? 'none'  : 'block';
    input.style.paddingRight = '2rem';
  }

  clearBtn.addEventListener('click', function() {
    input.value = ''; hidden.value = '';
    syncUI();
    if (input.dataset.autosubmit) input.closest('form').submit();
    else input.focus();
  });

  syncUI();

  function closeDropdown() { dropdown.innerHTML = ''; dropdown.style.display = 'none'; }

  function renderList(list) {
    closeDropdown();
    positionDropdown();
    if (!list.length) {
      var li = document.createElement('li');
      li.className = 'combobox-empty';
      li.textContent = 'Sin resultados';
      dropdown.appendChild(li);
      dropdown.style.display = 'block';
      return;
    }
    list.forEach(function(c) {
      var li = document.createElement('li');
      li.className = 'combobox-item';
      li.innerHTML = (c.ci ? '<strong>' + c.ci + '</strong> — ' : '') + c.nombre;
      li.addEventListener('mouseover', function() { li.classList.add('combobox-item-active'); });
      li.addEventListener('mouseout',  function() { li.classList.remove('combobox-item-active'); });
      li.addEventListener('mousedown', function(e) {
        e.preventDefault();
        input.value  = c.nombre + (c.ci ? ' (' + c.ci + ')' : '');
        hidden.value = c.id;
        closeDropdown(); syncUI();
        if (input.dataset.autosubmit) input.closest('form').submit();
      });
      dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
  }

  // Búsqueda contra el servidor (el endpoint filtra por ?q=), con debounce.
  // Antes el combobox solo filtraba en el navegador la lista inicial, que el
  // servidor recorta (ej: prendas a 200). Cualquier registro fuera de ese tope
  // nunca aparecía por más que se escribiera. Ahora cada búsqueda va al servidor.
  var searchSeq   = 0;
  var searchTimer = null;

  function renderServerResults(q) {
    var seq = ++searchSeq;
    var url = endpoint + (endpoint.indexOf('?') === -1 ? '?' : '&') + 'q=' + encodeURIComponent(q);
    fetch(url)
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (seq !== searchSeq) return;   // respuesta obsoleta (llegó fuera de orden)
        renderList(data);
      })
      .catch(function() {});
  }

  function filterAndShow() {
    var q = input.value.trim();
    // Sin texto: mostrar la lista inicial ya cargada (modo "explorar")
    if (!q) {
      if (searchTimer) { clearTimeout(searchTimer); searchTimer = null; }
      renderList(allItems);
      return;
    }
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(function() { renderServerResults(q); }, 250);
  }

  fetch(endpoint)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      allItems = data;
      // Pre-poblar el texto si el hidden ya tiene un ID (ej: filtro activo en la URL)
      if (hidden.value && !input.value) {
        var match = allItems.find(function(c) { return String(c.id) === String(hidden.value); });
        if (match) { input.value = match.nombre + (match.ci ? ' (' + match.ci + ')' : ''); syncUI(); }
      }
    })
    .catch(function() {});

  input.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    var active = dropdown.querySelector('.combobox-item-active') || dropdown.querySelector('.combobox-item');
    if (active) active.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  });
  input.addEventListener('focus', function() { if (!hidden.value) filterAndShow(); });
  input.addEventListener('input', function() { hidden.value = ''; syncUI(); filterAndShow(); });
  input.addEventListener('blur',  function() { setTimeout(closeDropdown, 200); });

  // Reposicionar si el dropdown está abierto y la página se desplaza/redimensiona
  window.addEventListener('scroll', function() {
    if (dropdown.style.display !== 'none') positionDropdown();
  }, true);
  window.addEventListener('resize', function() {
    if (dropdown.style.display !== 'none') positionDropdown();
  });

  // Cuando el dropdown está abierto, redirigir el wheel al dropdown
  document.addEventListener('wheel', function(e) {
    if (dropdown.style.display === 'none') return;
    if (dropdown.contains(e.target)) return;
    dropdown.scrollTop += e.deltaY;
    e.preventDefault();
  }, { passive: false });
}

// ── Combobox local (filtra array pre-cargado, sin AJAX) ──────────────────────
// items: [{id, nombre, info?}]  — nombre va al input, info se muestra en dropdown
// El dropdown se monta en document.body con position:fixed para escapar cualquier
// contenedor con overflow:hidden/auto (ej: table-responsive, card-body).
function makeLocalCombobox(input, hidden, items) {
  var wrapper = input.parentElement;

  var chevron = document.createElement('span');
  chevron.style.cssText = 'position:absolute;right:0.6rem;top:50%;transform:translateY(-50%);pointer-events:none;color:#6c757d;line-height:1;';
  chevron.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
  wrapper.appendChild(chevron);

  var clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.style.cssText = 'position:absolute;right:0;top:0;height:100%;width:2.2rem;border:none;background:transparent;cursor:pointer;display:none;z-index:2;color:#6c757d;padding:0;';
  clearBtn.title = 'Limpiar';
  clearBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  wrapper.appendChild(clearBtn);

  // Dropdown va al body para no quedar recortado por overflow del contenedor
  var dropdown = document.createElement('ul');
  dropdown.className = 'combobox-dropdown';
  dropdown.style.cssText = 'position:fixed;z-index:9999;display:none;margin:0;padding:0;list-style:none;max-height:240px;overflow-y:auto;';
  document.body.appendChild(dropdown);

  function positionDropdown() {
    var rect = input.getBoundingClientRect();
    dropdown.style.top   = (rect.bottom + 2) + 'px';
    dropdown.style.left  = rect.left + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  function syncUI() {
    var has = !!hidden.value;
    clearBtn.style.display = has ? 'block' : 'none';
    chevron.style.display  = has ? 'none'  : 'block';
    input.style.paddingRight = '2rem';
  }

  clearBtn.addEventListener('click', function() {
    input.value = ''; hidden.value = '';
    syncUI(); input.focus();
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
  });

  syncUI();

  function closeDropdown() { dropdown.innerHTML = ''; dropdown.style.display = 'none'; }

  function renderList(list) {
    closeDropdown();
    positionDropdown();
    if (!list.length) {
      var li = document.createElement('li');
      li.className = 'combobox-empty';
      li.textContent = 'Sin resultados';
      dropdown.appendChild(li);
      dropdown.style.display = 'block';
      return;
    }
    list.forEach(function(it) {
      var li = document.createElement('li');
      li.className = 'combobox-item';
      li.appendChild(document.createTextNode(it.nombre));
      if (it.info) {
        var span = document.createElement('span');
        span.className = 'combobox-item-info';
        span.textContent = it.info;
        li.appendChild(span);
      }
      li.addEventListener('mouseover',  function() { li.classList.add('combobox-item-active'); });
      li.addEventListener('mouseout',   function() { li.classList.remove('combobox-item-active'); });
      li.addEventListener('mousedown',  function(e) {
        e.preventDefault();
        input.value  = it.nombre;
        hidden.value = it.id;
        closeDropdown(); syncUI();
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      });
      dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
  }

  function filterAndShow() {
    var q = input.value.trim().toLowerCase();
    renderList(q ? items.filter(function(it) {
      return it.nombre.toLowerCase().includes(q);
    }) : items);
  }

  input.addEventListener('keydown', function(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault(); // evitar submit del form
    var active = dropdown.querySelector('.combobox-item-active') || dropdown.querySelector('.combobox-item');
    if (active) active.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  });
  input.addEventListener('focus',  function() { filterAndShow(); });
  input.addEventListener('input',  function() { hidden.value = ''; syncUI(); filterAndShow(); });
  input.addEventListener('blur',   function() { setTimeout(closeDropdown, 200); });

  // Cuando el dropdown está abierto, redirigir el wheel al dropdown
  // en lugar de dejar que mueva la página
  document.addEventListener('wheel', function(e) {
    if (dropdown.style.display === 'none') return;
    if (dropdown.contains(e.target)) return;
    dropdown.scrollTop += e.deltaY;
    e.preventDefault();
  }, { passive: false });

  if (hidden.value) {
    var match = items.find(function(it) { return String(it.id) === String(hidden.value); });
    if (match) { input.value = match.nombre; syncUI(); }
  }
}

window.makeLocalCombobox = makeLocalCombobox;
window.makeCombobox      = makeCombobox;

// Selector flyout para prendas: agrupa por SKU en el dropdown principal,
// flyout lateral muestra las unidades individuales al hover.
// prendas: array flat de _prenda_items_json (con sku_codigo, sku_nombre, talla, color, condicion, etc.)
function makePrendaFlyoutCombobox(input, hidden, prendas) {
  var wrapper = input.parentElement;

  var chevron = document.createElement('span');
  chevron.style.cssText = 'position:absolute;right:0.6rem;top:50%;transform:translateY(-50%);pointer-events:none;color:#6c757d;line-height:1;';
  chevron.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';
  wrapper.appendChild(chevron);

  var clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.style.cssText = 'position:absolute;right:0;top:0;height:100%;width:2.2rem;border:none;background:transparent;cursor:pointer;display:none;z-index:2;color:#6c757d;padding:0;';
  clearBtn.title = 'Limpiar';
  clearBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  wrapper.appendChild(clearBtn);

  // Agrupar por SKU
  var skuMap = new Map();
  prendas.forEach(function(p) {
    if (!skuMap.has(p.sku_codigo)) {
      var lbl = p.sku_nombre + (p.talla ? ' T' + p.talla : '') + (p.color ? ' ' + p.color : '');
      skuMap.set(p.sku_codigo, { codigo: p.sku_codigo, label: lbl, items: [] });
    }
    skuMap.get(p.sku_codigo).items.push(p);
  });
  var skus = Array.from(skuMap.values());

  var dropdown = document.createElement('ul');
  dropdown.className = 'combobox-dropdown';
  dropdown.style.cssText = 'position:fixed;z-index:9999;display:none;margin:0;padding:0;list-style:none;max-height:280px;overflow-y:auto;min-width:200px;';
  document.body.appendChild(dropdown);

  var flyout = document.createElement('ul');
  flyout.className = 'combobox-dropdown';
  flyout.style.cssText = 'position:fixed;z-index:10000;display:none;margin:0;padding:0;list-style:none;max-height:300px;overflow-y:auto;min-width:260px;';
  document.body.appendChild(flyout);

  var activeSkuEl = null;
  var closeTimer  = null;

  function syncUI() {
    var has = !!hidden.value;
    clearBtn.style.display = has ? 'block' : 'none';
    chevron.style.display  = has ? 'none'  : 'block';
    input.style.paddingRight = '2rem';
  }

  clearBtn.addEventListener('click', function() {
    input.value = ''; hidden.value = '';
    syncUI(); input.focus();
    hidden.dispatchEvent(new Event('change', { bubbles: true }));
  });

  syncUI();

  function closeAll() {
    dropdown.style.display = 'none'; flyout.style.display = 'none';
    dropdown.innerHTML = ''; flyout.innerHTML = '';
    activeSkuEl = null;
  }

  function positionDropdown() {
    var rect = input.getBoundingClientRect();
    dropdown.style.top   = (rect.bottom + 2) + 'px';
    dropdown.style.left  = rect.left + 'px';
    dropdown.style.width = rect.width + 'px';
  }

  function showFlyout(skuLi, sku) {
    flyout.innerHTML = '';
    sku.items.forEach(function(item) {
      var li = document.createElement('li');
      li.className = 'combobox-item';

      var code = document.createElement('span');
      code.className = 'prenda-flyout-code';
      code.textContent = item.codigo_item;

      var badge = document.createElement('span');
      badge.className = 'prenda-flyout-badge ' + item.condicion;
      badge.textContent = item.condicion_label;

      li.appendChild(code);
      li.appendChild(badge);

      if (item.ubicacion) {
        var ub = document.createElement('span');
        ub.className = 'prenda-flyout-ubic';
        ub.textContent = '[' + item.ubicacion + ']';
        li.appendChild(ub);
      }

      li.addEventListener('mouseover',  function() { li.classList.add('combobox-item-active'); });
      li.addEventListener('mouseout',   function() { li.classList.remove('combobox-item-active'); });
      li.addEventListener('mousedown',  function(e) {
        e.preventDefault();
        input.value  = item.label;
        hidden.value = item.prenda_item_id;
        closeAll(); syncUI();
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
      });
      flyout.appendChild(li);
    });

    // Medir primero (offscreen) para saber la altura real antes de posicionar
    flyout.style.top     = '-9999px';
    flyout.style.left    = '-9999px';
    flyout.style.display = 'block';

    var ddRect  = dropdown.getBoundingClientRect();
    var liRect  = skuLi.getBoundingClientRect();
    var flyW    = flyout.offsetWidth  || 260;
    var flyH    = flyout.offsetHeight || 0;
    var vw      = window.innerWidth;
    var vh      = window.innerHeight;

    // Horizontal: derecha si cabe, sino izquierda
    var flyLeft = (ddRect.right + 4 + flyW <= vw) ? ddRect.right + 4 : ddRect.left - flyW - 4;
    // Vertical: alinear con el item, pero clampear para no salir del viewport
    var flyTop  = liRect.top;
    if (flyTop + flyH > vh - 8) flyTop = Math.max(8, vh - flyH - 8);

    flyout.style.top  = flyTop + 'px';
    flyout.style.left = flyLeft + 'px';
  }

  function renderSkus(filtered) {
    dropdown.innerHTML = '';
    positionDropdown();
    if (!filtered.length) {
      var empty = document.createElement('li');
      empty.className = 'combobox-empty';
      empty.textContent = 'Sin resultados';
      dropdown.appendChild(empty);
      dropdown.style.display = 'block';
      return;
    }
    filtered.forEach(function(sku) {
      var li = document.createElement('li');
      li.className = 'combobox-item';
      li.style.cssText = 'display:flex;align-items:center;';

      var name = document.createElement('span');
      name.style.flex = '1';
      name.textContent = sku.label;

      var cnt = document.createElement('span');
      cnt.className = 'prenda-flyout-cnt';
      cnt.textContent = sku.items.length + ' disp.';

      var arrow = document.createElement('span');
      arrow.className = 'prenda-flyout-arrow';
      arrow.textContent = '▶';

      li.appendChild(name); li.appendChild(cnt); li.appendChild(arrow);

      li.addEventListener('mouseover', function() {
        if (closeTimer) clearTimeout(closeTimer);
        if (activeSkuEl) activeSkuEl.classList.remove('combobox-item-active');
        activeSkuEl = li;
        li.classList.add('combobox-item-active');
        showFlyout(li, sku);
      });
      dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
  }

  function filterAndShow() {
    var q = input.value.trim().toLowerCase();
    renderSkus(q ? skus.filter(function(s) { return s.label.toLowerCase().includes(q); }) : skus);
  }

  dropdown.addEventListener('mouseleave', function() {
    closeTimer = setTimeout(function() {
      if (!flyout.matches(':hover')) {
        flyout.style.display = 'none';
        if (activeSkuEl) activeSkuEl.classList.remove('combobox-item-active');
      }
    }, 150);
  });
  flyout.addEventListener('mouseenter', function() { if (closeTimer) clearTimeout(closeTimer); });
  flyout.addEventListener('mouseleave', function() {
    closeTimer = setTimeout(function() {
      flyout.style.display = 'none';
      if (activeSkuEl) activeSkuEl.classList.remove('combobox-item-active');
    }, 150);
  });

  input.addEventListener('focus',  function() { filterAndShow(); });
  input.addEventListener('input',  function() { hidden.value = ''; syncUI(); filterAndShow(); });
  input.addEventListener('blur',   function() { setTimeout(closeAll, 250); });

  // Restaurar label si el hidden ya tiene valor (edición)
  if (hidden.value) {
    var match = prendas.find(function(p) { return String(p.prenda_item_id) === String(hidden.value); });
    if (match) { input.value = match.label; syncUI(); }
  }
}

window.makePrendaFlyoutCombobox = makePrendaFlyoutCombobox;
window.makeLocalCombobox = makeLocalCombobox;

document.querySelectorAll('[data-cliente-search]').forEach(function(input) {
  makeCombobox(input, input.dataset.clienteSearch, input.dataset.endpoint || '/clientes/buscar/');
});

document.querySelectorAll('[data-empleado-search]').forEach(function(input) {
  makeCombobox(input, input.dataset.empleadoSearch, input.dataset.endpoint || '/empleados/buscar/');
});

document.querySelectorAll('[data-prenda-inventario-search]').forEach(function(input) {
  makeCombobox(input, input.dataset.prendaInventarioSearch, input.dataset.endpoint);
});

document.querySelectorAll('[data-confeccion-search]').forEach(function(input) {
  makeCombobox(input, input.dataset.confeccionSearch, input.dataset.endpoint);
});

// ── Modal de confirmación de eliminación ──────────────────────────────────────
document.addEventListener('click', function(e) {
  var btn = e.target.closest('[data-delete-url]');
  if (!btn) return;
  e.preventDefault();
  var url  = btn.dataset.deleteUrl;
  var name = btn.dataset.deleteName || '';
  document.getElementById('deleteModalForm').action = url;
  document.getElementById('deleteModalName').textContent = name;
  var modalEl = document.getElementById('deleteModal');
  var modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
  modal.show();
});

// ── Conjuntos — addConjuntoToForm ─────────────────────────────────────────────
// Devuelve { agregadas: N, faltantes: [prenda_item_nombre, ...] }
// ctx = { PRENDAS, tbody, addRow, nextGrupo }
window.addConjuntoToForm = function(conjunto, slotsIncluidos, ctx) {
  var slotsActivos = conjunto.slots
    .filter(function(s) { return slotsIncluidos.has(s.id); })
    .sort(function(a, b) { return a.orden - b.orden; });

  var n = slotsActivos.length;
  if (!n) return { agregadas: 0, faltantes: [] };

  var precioTotal = conjunto.precio_sugerido || 0;
  var base  = Math.round((precioTotal / n) * 100) / 100;
  var ajuste = Math.round((precioTotal - base * n) * 100) / 100;

  var grupoNum = (typeof ctx.nextGrupo === 'function') ? ctx.nextGrupo() : null;

  ctx.tbody.querySelectorAll('.item-row').forEach(function(row) {
    var h = row.querySelector('[name="item_prenda_item"]');
    if (h && !h.value) row.remove();
  });

  var usados = new Set(
    Array.from(ctx.tbody.querySelectorAll('[name="item_prenda_item"]'))
      .map(function(i) { return i.value; })
      .filter(Boolean)
  );

  var faltantes = [];
  slotsActivos.forEach(function(slot, idx) {
    var precioFallback = (idx === 0) ? (base + ajuste) : base;
    var idStr = slot.prenda_item_id ? String(slot.prenda_item_id) : null;
    // Precio: usar precio base del slot (sin depreciación); si no hay, buscar en PRENDAS; si no, proporcional del conjunto
    var precio = precioFallback;
    if (slot.precio_alquiler_base != null) {
      precio = slot.precio_alquiler_base;
    } else if (idStr && ctx.PRENDAS) {
      var prendaData = ctx.PRENDAS.find(function(p) { return String(p.prenda_item_id) === idStr; });
      if (prendaData && prendaData.precio_alquiler_base != null) {
        precio = prendaData.precio_alquiler_base;
      }
    }
    // Disponibilidad: usar slot.disponible (el backend ya sabe si está libre, incluso si es slot de conjunto)
    if (idStr && slot.disponible && !usados.has(idStr)) {
      usados.add(idStr);
      ctx.addRow(slot.prenda_item_id, precio, grupoNum);
    } else {
      faltantes.push(slot.prenda_item_nombre || 'Sin asignar');
      ctx.addRow(null, precioFallback, grupoNum);
    }
  });

  return { agregadas: slotsActivos.length, faltantes: faltantes };
};

// ── Conjuntos — initConjuntoModal ─────────────────────────────────────────────
// modalId: ID del elemento modal
// CONJUNTOS: array de conjuntos del contexto
// onConfirm: función(conjunto, slotsIncluidosSet) llamada al confirmar
window.initConjuntoModal = function(modalId, CONJUNTOS, onConfirm) {
  var modalEl = document.getElementById(modalId);
  if (!modalEl) return;

  var btnAgregar = document.getElementById('btnAgregarConjunto');
  if (btnAgregar) {
    btnAgregar.style.display = (!CONJUNTOS || CONJUNTOS.length === 0) ? 'none' : '';
  }

  var body = document.getElementById('modalConjuntosBody');
  var btnConfirmar = document.getElementById('btnConfirmarConjunto');
  if (!body) return;

  var selectedConjunto = null;

  function dispBadge(disp) {
    if (disp === 'completo')       return '<span class="badge bg-success ms-1">Disponible</span>';
    if (disp === 'parcial')        return '<span class="badge bg-warning text-dark ms-1">Parcial</span>';
    return '<span class="badge bg-danger ms-1">No disponible</span>';
  }

  function slotBadge(disponible) {
    return disponible
      ? '<span class="badge bg-success-subtle text-success border border-success-subtle ms-1">ok</span>'
      : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle ms-1">no disp.</span>';
  }

  function renderDetail(c) {
    var detail = document.getElementById('conjuntoDetail');
    if (!detail) return;
    if (!c) { detail.innerHTML = ''; return; }

    var html = '<div class="mt-3 border-top pt-3"><p class="fw-semibold mb-2">Composición de <em>' + c.nombre + '</em>:</p><ul class="list-unstyled mb-0">';
    c.slots.forEach(function(s) {
      var badge = slotBadge(s.disponible);
      if (s.opcional) {
        html += '<li class="d-flex align-items-center gap-2 mb-1">' +
          '<input type="checkbox" class="form-check-input slot-check flex-shrink-0" data-slot-id="' + s.id + '" checked>' +
          '<span class="small">' + (s.prenda_item_codigo ? '<code>' + s.prenda_item_codigo + '</code> — ' : '') + s.prenda_item_nombre + ' <span class="text-muted">(opcional)</span>' + badge + '</span>' +
          '</li>';
      } else {
        html += '<li class="d-flex align-items-center gap-2 mb-1">' +
          '<input type="hidden" class="slot-check" data-slot-id="' + s.id + '" value="on">' +
          '<i data-lucide="check" class="text-success flex-shrink-0" style="width:16px;height:16px"></i>' +
          '<span class="small">' + (s.prenda_item_codigo ? '<code>' + s.prenda_item_codigo + '</code> — ' : '') + s.prenda_item_nombre + badge + '</span>' +
          '</li>';
      }
    });
    html += '</ul></div>';
    detail.innerHTML = html;
    if (typeof lucide !== 'undefined') lucide.createIcons({ nodes: [detail] });
  }

  function updateConfirmarBtn() {
    if (!btnConfirmar) return;
    if (!selectedConjunto) {
      btnConfirmar.disabled = true;
      return;
    }
    btnConfirmar.disabled = false;
  }

  function renderConjuntos() {
    selectedConjunto = null;
    updateConfirmarBtn();
    var detail = document.getElementById('conjuntoDetail');
    if (detail) detail.innerHTML = '';

    body.innerHTML = '';
    if (!CONJUNTOS || CONJUNTOS.length === 0) {
      body.innerHTML = '<p class="text-muted">No hay conjuntos activos.</p>';
      return;
    }

    var table = document.createElement('table');
    table.className = 'table table-hover table-sm align-middle mb-0';
    table.innerHTML =
      '<thead><tr>' +
        '<th>Nombre</th>' +
        '<th class="text-end">Precio</th>' +
        '<th>Composición</th>' +
        '<th>Disponibilidad</th>' +
      '</tr></thead>';
    var tbody = document.createElement('tbody');

    CONJUNTOS.forEach(function(c) {
      var tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      var slotCount = c.slots.length;
      var slotLabel = slotCount + ' prenda' + (slotCount !== 1 ? 's' : '');
      tr.innerHTML =
        '<td class="fw-semibold">' + c.nombre + (c.descripcion ? '<br><small class="text-muted fw-normal">' + c.descripcion + '</small>' : '') + '</td>' +
        '<td class="text-end text-nowrap">Bs. ' + c.precio_sugerido.toFixed(2) + '</td>' +
        '<td><span class="badge bg-secondary-subtle text-secondary border">' + slotLabel + '</span></td>' +
        '<td>' + dispBadge(c.disponibilidad) + '</td>';

      tr.addEventListener('click', function() {
        tbody.querySelectorAll('tr').forEach(function(r) { r.classList.remove('table-active'); });
        tr.classList.add('table-active');
        selectedConjunto = c;
        renderDetail(c);
        updateConfirmarBtn();
      });

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    body.appendChild(table);

    var detailDiv = document.createElement('div');
    detailDiv.id = 'conjuntoDetail';
    body.appendChild(detailDiv);
  }

  if (btnConfirmar) {
    btnConfirmar.addEventListener('click', function() {
      if (!selectedConjunto) return;
      var included = new Set();
      var detail = document.getElementById('conjuntoDetail');
      if (detail) {
        detail.querySelectorAll('.slot-check').forEach(function(el) {
          if ((el.type === 'checkbox' && el.checked) || el.type === 'hidden') {
            included.add(parseInt(el.dataset.slotId));
          }
        });
      }
      if (included.size === 0) return;
      var bsModal = bootstrap.Modal.getInstance(modalEl);
      if (bsModal) bsModal.hide();
      onConfirm(selectedConjunto, included);
    });
  }

  modalEl.addEventListener('show.bs.modal', renderConjuntos);
};

// ── Filtro de filas client-side por atributo (chips) ──────────────────────────
// Uso: contenedor de botones con [data-row-filter="tablaId"] y
// [data-row-filter-attr="tipo"]; cada botón lleva data-value. Las filas del
// tbody se filtran por su atributo data-{attr}. Botón con data-value="" = todas.
document.querySelectorAll('[data-row-filter]').forEach(function(group) {
  var table = document.getElementById(group.dataset.rowFilter);
  if (!table) return;
  var attr = group.dataset.rowFilterAttr || 'tipo';
  var buttons = Array.from(group.querySelectorAll('button[data-value]'));
  var emptyRow = table.querySelector('[data-row-filter-empty]');

  function apply(value) {
    var visibles = 0;
    table.querySelectorAll('tbody tr[data-' + attr + ']').forEach(function(row) {
      var match = !value || row.getAttribute('data-' + attr) === value;
      row.style.display = match ? '' : 'none';
      if (match) visibles++;
    });
    if (emptyRow) emptyRow.classList.toggle('d-none', visibles > 0);
    buttons.forEach(function(b) {
      b.classList.toggle('active', b.dataset.value === value);
    });
  }

  group.addEventListener('click', function(e) {
    var btn = e.target.closest('button[data-value]');
    if (btn) apply(btn.dataset.value);
  });
});
