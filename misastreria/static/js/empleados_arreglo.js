/* Empleados asignados al arreglo de una prenda, en venta y en alquiler.
 *
 * Cada fila de la tabla de prendas guarda sus empleados en un <input hidden>
 * con JSON: [{empleado_id, empleado_nombre, monto}]. Este módulo abre el modal
 * sobre ese campo y lo reescribe al guardar.
 *
 *   EmpleadosArreglo.init(EMPLEADOS);                     // una vez por página
 *   EmpleadosArreglo.abrir(inputOculto, etiqueta, boton); // por fila
 */
window.EmpleadosArreglo = (function () {
  'use strict';

  var empleados = [];
  var modal = null;
  var destino = null;     // input oculto de la fila en edición
  var botonFila = null;   // botón de esa fila, para actualizar el contador

  function el(id) { return document.getElementById(id); }

  // El nombre del empleado es texto libre del formulario de empleados. Sin
  // escapar, un nombre guardado como `<img src=x onerror=…>` se ejecuta cada
  // vez que alguien abre este modal en una venta o un alquiler.
  function escaparHtml(texto) {
    const d = document.createElement('div');
    d.textContent = String(texto ?? '');
    return d.innerHTML;
  }

  function leer(input) {
    try { return JSON.parse(input.value || '[]'); } catch (e) { return []; }
  }

  function opciones(asig) {
    var seleccionado = asig && asig.empleado_id;
    var html = '<option value="">— Elegir empleado —</option>';
    var encontrado = false;
    empleados.forEach(function (e) {
      var esta = String(e.id) === String(seleccionado);
      if (esta) encontrado = true;
      html += '<option value="' + Number(e.id) + '"' + (esta ? ' selected' : '') +
              '>' + escaparHtml(e.nombre) + '</option>';
    });
    // El empleado asignado puede haber sido desactivado: la lista sólo trae
    // activos. Sin esta opción el select cae a vacío, `recolectar` descarta la
    // fila y guardar le borra la comisión sin avisar.
    if (seleccionado && !encontrado) {
      html += '<option value="' + Number(seleccionado) + '" selected>' +
              escaparHtml(asig.empleado_nombre || ('Empleado ' + seleccionado)) +
              ' (inactivo)</option>';
    }
    return html;
  }

  function filaHtml(asig) {
    return '<tr>' +
      '<td><select class="form-select form-select-sm emp-sel">' +
        opciones(asig) + '</select></td>' +
      '<td><input type="number" step="0.01" min="0" class="form-control form-control-sm emp-monto" ' +
        'value="' + (asig && asig.monto != null ? Number(asig.monto) : '') + '" placeholder="0.00"></td>' +
      '<td class="text-end"><button type="button" class="btn btn-sm btn-icon btn-ghost-danger emp-quitar" ' +
        'title="Quitar">✕</button></td>' +
    '</tr>';
  }

  function total() {
    var suma = 0;
    el('emp-arreglo-cuerpo').querySelectorAll('.emp-monto').forEach(function (i) {
      suma += parseFloat(i.value) || 0;
    });
    el('emp-arreglo-total').textContent = suma.toFixed(2);
  }

  function recolectar() {
    var salida = [], vistos = {};
    el('emp-arreglo-cuerpo').querySelectorAll('tr').forEach(function (tr) {
      var sel = tr.querySelector('.emp-sel');
      var id = sel.value;
      // Sin empleado la fila no significa nada, y repetido choca con la
      // restricción única de la base: se descartan acá y no al guardar.
      if (!id || vistos[id]) return;
      vistos[id] = true;
      salida.push({
        empleado_id: parseInt(id, 10),
        empleado_nombre: sel.options[sel.selectedIndex].textContent,
        monto: parseFloat(tr.querySelector('.emp-monto').value) || 0,
      });
    });
    return salida;
  }

  function etiquetar(boton, n) {
    if (!boton) return;
    boton.textContent = n ? 'Empleados (' + n + ')' : 'Empleados';
    boton.classList.toggle('btn-outline-primary', n > 0);
    boton.classList.toggle('btn-outline-secondary', n === 0);
  }

  function init(lista) {
    empleados = lista || [];
    var cuerpo = el('emp-arreglo-cuerpo');
    if (!cuerpo) return;   // la pantalla no incluyó el partial

    el('emp-arreglo-agregar').addEventListener('click', function () {
      cuerpo.insertAdjacentHTML('beforeend', filaHtml(null));
      total();
    });
    cuerpo.addEventListener('click', function (ev) {
      if (!ev.target.closest('.emp-quitar')) return;
      ev.target.closest('tr').remove();
      total();
    });
    cuerpo.addEventListener('input', total);

    el('emp-arreglo-guardar').addEventListener('click', function () {
      if (!destino) return;
      var datos = recolectar();
      destino.value = JSON.stringify(datos);
      etiquetar(botonFila, datos.length);
      if (modal) modal.hide();
    });
  }

  function abrir(input, contexto, boton) {
    var cuerpo = el('emp-arreglo-cuerpo');
    if (!cuerpo) return;
    destino = input;
    botonFila = boton;
    el('emp-arreglo-contexto').textContent = contexto || '';
    var actuales = leer(input);
    cuerpo.innerHTML = actuales.length
      ? actuales.map(filaHtml).join('')
      : filaHtml(null);       // arranca con una fila lista para usar
    total();
    if (!modal) modal = new bootstrap.Modal(el('emp-arreglo-modal'));
    modal.show();
  }

  return { init: init, abrir: abrir, etiquetar: etiquetar };
})();
