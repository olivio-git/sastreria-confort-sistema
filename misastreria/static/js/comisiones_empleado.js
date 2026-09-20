// comisiones_empleado.js — modal de pago de comisión por selección de
// devengaciones puntuales, en el detalle de empleado.
//
// El monto ya no se tipea: se deriva de las devengaciones (pendientes o
// parciales) que el usuario marca con checkbox en la tabla del modal. Este
// script sólo mantiene el total y el contador en sincro con lo marcado,
// sincroniza el checkbox "Seleccionar todas" y evita un submit vacío. La
// validación real (pertenencia al empleado, saldo, claves manipuladas) la
// hace el servidor en `pagar_comision_empleado` — esto es sólo UX.
//
// Saldo a favor: el modal trae `data-saldo-favor` (sin localizar, punto
// decimal). El servidor lo consume primero, así que "A pagar" muestra
// max(0, seleccionado − saldo a favor).
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
  var saldoFavor = parseFloat(modal.dataset.saldoFavor) || 0;
  var enviando = false;

  function actualizar() {
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

  checkboxes.forEach(function(c) {
    c.addEventListener('change', actualizar);
  });

  if (checkTodas) {
    checkTodas.addEventListener('change', function() {
      checkboxes.forEach(function(c) { c.checked = checkTodas.checked; });
      actualizar();
    });
  }

  if (form) {
    form.addEventListener('submit', function(e) {
      if (enviando) {
        e.preventDefault();
        return;
      }
      if (!checkboxes.some(function(c) { return c.checked; })) {
        e.preventDefault();
        alert('Selecciona al menos una devengación pendiente para pagar.');
        return;
      }
      // Evita el doble submit (doble clic / Enter repetido).
      enviando = true;
      if (btnSubmit) btnSubmit.disabled = true;
    });
  }

  actualizar();
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
