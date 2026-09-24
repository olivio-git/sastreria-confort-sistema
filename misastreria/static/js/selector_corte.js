// selector_corte.js — elegir el corte de una unidad desde un modal con buscador.
//
// Reemplaza al <select> con todos los cortes, que con cincuenta ya no se podía
// usar. Cada formulario tiene un bloque [data-corte-picker] con cuatro ocultos
// (corte_modo, corte, nuevo_corte_sigla, nuevo_corte_tela) que el servidor lee
// con _resolver_corte(). Este script sólo los llena; la validación que cuenta
// es la del servidor.
//
// Un solo modal para los dos formularios: se recuerda qué selector lo abrió.
// Se instancia en el primer uso y no al arrancar, para no depender de que el
// bundle de Bootstrap del CDN haya llegado antes que este archivo.
(function () {
  'use strict';

  var modalEl = document.getElementById('modalCorte');
  if (!modalEl) return;

  var endpoint    = modalEl.dataset.endpoint;
  var buscar      = document.getElementById('corteBuscar');
  var filas       = document.getElementById('corteFilas');
  var vacio       = document.getElementById('corteVacio');
  var hayMas      = document.getElementById('corteHayMas');
  var siguienteEl = document.getElementById('corteSiguiente');
  var nuevoWrap   = document.getElementById('corteNuevoWrap');
  var siglaIn     = document.getElementById('corteNuevoSigla');
  var telaIn      = document.getElementById('corteNuevoTela');
  var errorEl     = document.getElementById('corteNuevoError');

  // Espejo de Corte.sigla_parece_numero (models.py). Acá es sólo para avisar
  // antes de guardar; si difieren, gana el servidor.
  var SIGLA_CON_FORMA_DE_NUMERO = /^C\s*-?\s*\d+$/i;

  var instancia = null;
  var pickerActivo = null;
  var temporizador = null;
  var pedido = 0;

  function oculto(picker, nombre) {
    return picker.querySelector('input[name="' + nombre + '"]');
  }

  // estado: {modo:'ninguno'} | {modo:'existente', id, texto}
  //       | {modo:'nuevo', sigla, tela, numero}
  function setear(picker, estado) {
    if (!picker) return;
    var modo = estado.modo;
    oculto(picker, 'corte_modo').value        = modo;
    oculto(picker, 'corte').value             = modo === 'existente' ? estado.id : '';
    oculto(picker, 'nuevo_corte_sigla').value = modo === 'nuevo' ? (estado.sigla || '') : '';
    oculto(picker, 'nuevo_corte_tela').value  = modo === 'nuevo' ? (estado.tela || '') : '';

    var texto = picker.querySelector('[data-corte-texto]');
    if (modo === 'existente') {
      texto.textContent = estado.texto;
    } else if (modo === 'nuevo') {
      var partes = ['Nuevo: ' + (estado.numero || 'corte nuevo')];
      if (estado.sigla) partes.push(estado.sigla.toUpperCase());
      texto.textContent = partes.join(' · ') + (estado.tela ? ' (' + estado.tela + ')' : '');
    } else {
      texto.textContent = 'Sin corte';
    }
    texto.classList.toggle('text-muted', modo === 'ninguno');
  }
  window.selectorCorteSetear = setear;

  function celda(texto, clase) {
    var td = document.createElement('td');
    td.textContent = texto || '—';
    if (clase) td.className = clase;
    return td;
  }

  function pintar(data) {
    filas.replaceChildren();
    data.resultados.forEach(function (c) {
      var tr = document.createElement('tr');
      tr.appendChild(celda(c.numero, 'fw-semibold'));
      tr.appendChild(celda(c.sigla));
      tr.appendChild(celda(c.tela));
      tr.appendChild(celda(c.fecha, 'text-muted'));
      tr.appendChild(celda(String(c.unidades), 'text-end'));
      tr.addEventListener('click', function () {
        elegir({ modo: 'existente', id: c.id, texto: c.texto });
      });
      filas.appendChild(tr);
    });

    var sinResultados = data.resultados.length === 0;
    vacio.style.display = sinResultados ? '' : 'none';
    vacio.textContent = buscar.value.trim()
      ? 'Ningún corte coincide con la búsqueda.'
      : 'Todavía no hay cortes. Creá el primero con «Crear corte nuevo».';
    hayMas.textContent = data.hay_mas ? 'Hay más: afiná la búsqueda.' : '';
    siguienteEl.textContent = data.siguiente;
  }

  function cargar() {
    var n = ++pedido;
    fetch(endpoint + '?q=' + encodeURIComponent(buscar.value.trim()),
          { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (n !== pedido) return;  // llegó tarde: ya hay una búsqueda más nueva
        pintar(data);
      })
      .catch(function () {
        if (n !== pedido) return;
        filas.replaceChildren();
        vacio.style.display = '';
        vacio.textContent = 'No se pudieron cargar los cortes. Probá de nuevo.';
      });
  }

  function elegir(estado) {
    setear(pickerActivo, estado);
    if (instancia) instancia.hide();
  }

  function abrir(picker) {
    pickerActivo = picker;
    buscar.value = '';
    siglaIn.value = '';
    telaIn.value = '';
    errorEl.style.display = 'none';
    nuevoWrap.style.display = 'none';
    if (!instancia) instancia = new bootstrap.Modal(modalEl);
    instancia.show();
    cargar();
  }

  document.addEventListener('click', function (e) {
    var boton = e.target.closest('[data-corte-abrir]');
    if (!boton) return;
    abrir(boton.closest('[data-corte-picker]'));
  });

  // focus() antes de que el modal sea visible no tiene efecto.
  modalEl.addEventListener('shown.bs.modal', function () { buscar.focus(); });

  buscar.addEventListener('input', function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(cargar, 250);
  });

  document.getElementById('corteSinCorte').addEventListener('click', function () {
    elegir({ modo: 'ninguno' });
  });

  document.getElementById('corteNuevoToggle').addEventListener('click', function () {
    var visible = nuevoWrap.style.display !== 'none';
    nuevoWrap.style.display = visible ? 'none' : '';
    if (!visible) siglaIn.focus();
  });

  document.getElementById('corteNuevoUsar').addEventListener('click', function () {
    var sigla = siglaIn.value.trim();
    if (SIGLA_CON_FORMA_DE_NUMERO.test(sigla)) {
      errorEl.textContent = '«' + sigla + '» parece un número de corte. El número lo '
        + 'pone el sistema; la sigla es un apodo opcional, por ejemplo AZUL-LANA.';
      errorEl.style.display = '';
      siglaIn.focus();
      return;
    }
    elegir({ modo: 'nuevo', sigla: sigla, tela: telaIn.value.trim(),
             numero: siguienteEl.textContent });
  });
})();
