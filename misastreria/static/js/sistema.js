// ── Debounce auto-submit para formularios de filtro ──────────────────────────
document.querySelectorAll('[data-debounce]').forEach(function(input) {
  var timer;
  var delay = parseInt(input.dataset.debounce || '400');
  input.addEventListener('input', function() {
    clearTimeout(timer);
    timer = setTimeout(function() { input.closest('form').submit(); }, delay);
  });
});

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

// ── Cliente autocomplete ───────────────────────────────────────────────────────
document.querySelectorAll('[data-cliente-search]').forEach(function(input) {
  var hiddenId = input.dataset.clienteSearch;
  var hidden = document.getElementById(hiddenId);
  var endpoint = input.dataset.endpoint || '/clientes/buscar/';
  var timer;

  // Dropdown container
  var dropdown = document.createElement('ul');
  dropdown.className = 'list-group position-absolute shadow-sm';
  dropdown.style.cssText = 'z-index:1050;width:100%;max-height:220px;overflow-y:auto;display:none;';
  input.parentElement.style.position = 'relative';
  input.parentElement.appendChild(dropdown);

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
      li.innerHTML = '<strong>' + c.ci + '</strong> — ' + c.nombre;
      li.addEventListener('mousedown', function(e) {
        e.preventDefault();
        input.value = c.nombre + (c.ci ? ' (' + c.ci + ')' : '');
        hidden.value = c.id;
        clearDropdown();
      });
      dropdown.appendChild(li);
    });
    dropdown.style.display = 'block';
  }

  input.addEventListener('input', function() {
    hidden.value = '';
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
