// comisiones_empleado.js — modal de pago de comisión en el detalle de
// empleado. Dos modos, los dos aplicados a devengaciones concretas:
//
//   - Por selección: el usuario marca con checkbox las devengaciones
//     (pendientes o parciales) que paga y el monto es su suma.
//   - Por monto: el usuario tipea un monto y el servidor lo reparte de la
//     devengación más vieja a la más nueva. Acá sólo se muestra la vista
//     previa de ese reparto, en el orden que manda el servidor (data-orden).
//
// Esto es sólo UX. La validación real (pertenencia al empleado, saldo,
// claves manipuladas, tope del monto) la hace `pagar_comision_empleado`.
//
// Saldo a favor: el modal trae `data-saldo-favor` (sin localizar, punto
// decimal). El servidor lo consume primero, así que en selección "A pagar"
// es max(0, seleccionado − saldo a favor), y por monto el saldo a favor
// cubre las devengaciones más viejas antes que el monto tipeado.
(function() {
  var modal = document.getElementById('modalPagarComision');
  if (!modal) return;

  var checkboxes = Array.from(modal.querySelectorAll('.sel-devengacion'));
  var checkTodas = modal.querySelector('#selTodasComision');
  var totalEl = modal.querySelector('#totalSeleccionComision');
  var contadorEl = modal.querySelector('#contadorSeleccionComision');
  var form = modal.querySelector('form');
  var btnSubmit = modal.querySelector('#btnRegistrarPagoComision');
  var aPagarEl = modal.querySelector('#aPagarSeleccionComision');
  var montoInput = modal.querySelector('input[name="monto"]');
  var radiosModo = Array.from(modal.querySelectorAll('input[name="modo"]'));
  var soloModo = Array.from(modal.querySelectorAll('[data-modo-solo]'));
  var saldoFavor = parseFloat(modal.dataset.saldoFavor) || 0;
  var saldoComision = parseFloat(modal.dataset.saldoComision) || 0;
  var enviando = false;

  // Filas en orden de reparto (la más vieja primero).
  var filasFifo = Array.from(modal.querySelectorAll('tr.fila-devengacion')).sort(function(a, b) {
    return (parseInt(a.dataset.orden, 10) || 0) - (parseInt(b.dataset.orden, 10) || 0);
  });

  if (montoInput) montoInput.max = saldoComision.toFixed(2);

  function modoActual() {
    var r = radiosModo.find(function(x) { return x.checked; });
    return r ? r.value : 'seleccion';
  }

  // Centavos enteros: los montos salen de sumar floats.
  function cent(v) { return Math.round(v * 100); }

  function actualizarSeleccion() {
    var seleccionadas = checkboxes.filter(function(c) { return c.checked; });
    var total = seleccionadas.reduce(function(acc, c) {
      return acc + (parseFloat(c.dataset.pendiente) || 0);
    }, 0);
    if (totalEl) totalEl.textContent = total.toFixed(2);
    if (aPagarEl) aPagarEl.textContent = Math.max(0, total - saldoFavor).toFixed(2);
    if (contadorEl) contadorEl.textContent = seleccionadas.length;
    if (btnSubmit) btnSubmit.disabled = enviando || seleccionadas.length === 0;
    if (checkTodas && checkboxes.length) {
      checkTodas.checked = seleccionadas.length === checkboxes.length;
      checkTodas.indeterminate = seleccionadas.length > 0 && seleccionadas.length < checkboxes.length;
    }
  }

  function actualizarMonto() {
    var monto = parseFloat(montoInput && montoInput.value) || 0;
    var restante = cent(saldoFavor) + cent(monto);
    var cubierto = 0;
    var alcanzadas = 0;
    filasFifo.forEach(function(tr) {
      var pendiente = cent(parseFloat(tr.dataset.pendiente) || 0);
      var tomar = Math.min(restante, pendiente);
      restante -= tomar;
      cubierto += tomar;
      if (tomar > 0) alcanzadas++;
      var celda = tr.querySelector('[data-reparto]');
      if (celda) {
        celda.textContent = tomar > 0 ? 'Bs. ' + (tomar / 100).toFixed(2) + (tomar < pendiente ? ' (parcial)' : '') : '—';
        celda.classList.toggle('fw-semibold', tomar > 0);
        celda.classList.toggle('text-muted', tomar === 0);
      }
    });
    var valido = monto > 0 && cent(monto) <= cent(saldoComision);
    if (montoInput) montoInput.classList.toggle('is-invalid', monto > 0 && !valido);
    if (totalEl) totalEl.textContent = (cubierto / 100).toFixed(2);
    if (aPagarEl) aPagarEl.textContent = monto.toFixed(2);
    if (contadorEl) contadorEl.textContent = alcanzadas;
    if (btnSubmit) btnSubmit.disabled = enviando || !valido;
  }

  function actualizar() {
    if (modoActual() === 'monto') actualizarMonto();
    else actualizarSeleccion();
  }

  // Muestra lo del modo activo y deshabilita los campos del otro: un campo
  // deshabilitado no viaja en el POST, así el servidor no recibe checkboxes
  // marcados en un pago por monto ni un monto viejo en uno por selección.
  function aplicarModo() {
    var modo = modoActual();
    soloModo.forEach(function(el) {
      el.classList.toggle('d-none', el.dataset.modoSolo !== modo);
    });
    checkboxes.forEach(function(c) { c.disabled = modo === 'monto'; });
    if (checkTodas) checkTodas.disabled = modo === 'monto';
    if (montoInput) {
      montoInput.disabled = modo !== 'monto';
      if (modo === 'monto') montoInput.focus();
    }
    actualizar();
  }

  checkboxes.forEach(function(c) {
    c.addEventListener('change', actualizar);
  });

  if (checkTodas) {
    checkTodas.addEventListener('change', function() {
      checkboxes.forEach(function(c) { c.checked = checkTodas.checked; });
      actualizar();
    });
  }

  if (montoInput) montoInput.addEventListener('input', actualizar);
  radiosModo.forEach(function(r) { r.addEventListener('change', aplicarModo); });

  if (form) {
    form.addEventListener('submit', function(e) {
      if (enviando) {
        e.preventDefault();
        return;
      }
      if (modoActual() === 'seleccion' && !checkboxes.some(function(c) { return c.checked; })) {
        e.preventDefault();
        alert('Selecciona al menos una devengación pendiente para pagar.');
        return;
      }
      // Evita el doble submit (doble clic / Enter repetido).
      enviando = true;
      if (btnSubmit) btnSubmit.disabled = true;
    });
  }

  aplicarModo();
})();

// Detalle de devengaciones de un pago, en modal.
//
// Antes el detalle se dibujaba dentro de la celda "Descripción": un pago que
// cubre 19 devengaciones producía una fila de 19 renglones que rompía la
// altura de la tabla, y empeora a medida que se pagan más. Ahora la fila
// muestra sólo la cantidad y el detalle vive en un <template> que este modal
// clona al abrirse.
//
// Un solo modal para toda la tabla, instanciado en el primer uso y no al
// arrancar: así el script no depende de que el bundle de Bootstrap haya
// llegado antes que él.
(function () {
  var modalEl = document.getElementById('modalDevengacionesPago');
  if (!modalEl) return;

  var cuerpo = modalEl.querySelector('#devengacionesPagoCuerpo');
  var resumen = modalEl.querySelector('#devengacionesPagoResumen');
  var instancia = null;

  // Delegado en document: las filas se renderizan del lado del servidor, pero
  // así sigue funcionando si alguna vez se repaginan sin recargar.
  document.addEventListener('click', function (e) {
    var boton = e.target.closest('[data-devengaciones-de]');
    if (!boton) return;

    var plantilla = document.getElementById(boton.dataset.devengacionesDe);
    if (!plantilla) return;

    cuerpo.replaceChildren(plantilla.content.cloneNode(true));
    resumen.textContent = boton.dataset.resumen || '';

    if (!instancia) instancia = new bootstrap.Modal(modalEl);
    instancia.show();
  });
})();
