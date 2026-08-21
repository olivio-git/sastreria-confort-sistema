/* Botón «Calibrar la impresora» de la pantalla de ajustes de impresora.
 *
 * El trabajo real lo hace `etiquetas_puente.js`; acá sólo se traduce el
 * resultado a un mensajito al lado del botón.
 */
(function () {
  'use strict';

  const boton = document.getElementById('et-calibrar-impresora');
  if (!boton) return;

  const estado = document.getElementById('et-calibrar-estado');

  function avisar(texto, clase) {
    estado.textContent = texto;
    estado.className = `small align-self-center text-${clase}`;
  }

  boton.addEventListener('click', async () => {
    boton.disabled = true;
    avisar('Calibrando…', 'muted');

    const salida = await window.PuenteImpresion.calibrar(boton.dataset.url);
    avisar(salida.mensaje, salida.ok ? 'success' : 'danger');

    boton.disabled = false;
  });
})();
