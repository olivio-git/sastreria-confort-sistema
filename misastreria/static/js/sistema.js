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

// ── Cliente autocomplete ───────────────────────────────────────────────────────
document.querySelectorAll('[data-cliente-search]').forEach(function(input) {
  var hiddenId = input.dataset.clienteSearch;
  var hidden = document.getElementById(hiddenId);
  var endpoint = input.dataset.endpoint || '/clientes/buscar/';
  var timer;

  // Wrapper already has position:relative from the template
  var wrapper = input.parentElement;

  // Dropdown container
  var dropdown = document.createElement('ul');
  dropdown.className = 'list-group position-absolute shadow-sm';
  dropdown.style.cssText = 'z-index:1050;width:100%;max-height:220px;overflow-y:auto;display:none;top:100%;left:0;';
  wrapper.appendChild(dropdown);

  // Clear (X) button — shown when a client is selected
  var clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn btn-sm btn-outline-secondary';
  clearBtn.style.cssText = 'position:absolute;right:0;top:0;height:100%;border-radius:0 0.375rem 0.375rem 0;display:none;z-index:2;';
  clearBtn.innerHTML = '<i class="bi bi-x-lg"></i>';
  clearBtn.title = 'Limpiar selección';
  wrapper.appendChild(clearBtn);

  function updateClearBtn() {
    clearBtn.style.display = hidden.value ? 'block' : 'none';
    input.style.paddingRight = hidden.value ? '2.5rem' : '';
  }

  clearBtn.addEventListener('click', function() {
    input.value = '';
    hidden.value = '';
    updateClearBtn();
    input.focus();
  });

  // Show clear btn on load if already has a value (edit forms)
  updateClearBtn();

  function clearDropdown() {
    dropdown.innerHTML = '';
    dropdown.style.display = 'none';
  }

  function showResults(results) {
    clearDropdown();
    if (!results.length) {
      var li = document.createElement('li');
      li.className = 'list-group-item list-group-item-secondary text-muted';
      li.textContent = 'Sin resultados';
      dropdown.appendChild(li);
      dropdown.style.display = 'block';
      return;
    }
    results.forEach(function(c) {
      var li = document.createElement('li');
      li.className = 'list-group-item list-group-item-action';
      li.style.cursor = 'pointer';
      li.style.fontSize = '.85rem';
      li.innerHTML = '<strong>' + (c.ci || '—') + '</strong> — ' + c.nombre;
      li.addEventListener('mousedown', function(e) {
        e.preventDefault();
        input.value = c.nombre + (c.ci ? ' (' + c.ci + ')' : '');
        hidden.value = c.id;
        clearDropdown();
        updateClearBtn();
      });
      dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
  }

  input.addEventListener('input', function() {
    hidden.value = '';
    updateClearBtn();
    var q = input.value.trim();
    clearTimeout(timer);
    if (q.length < 2) { clearDropdown(); return; }
    timer = setTimeout(function() {
      fetch(endpoint + '?q=' + encodeURIComponent(q))
        .then(function(r) { return r.json(); })
        .then(showResults)
        .catch(clearDropdown);
    }, 300);
  });

  input.addEventListener('blur', function() {
    setTimeout(clearDropdown, 200);
  });
});
