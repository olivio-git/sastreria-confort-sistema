/* Botón «Calibrar la impresora» de la pantalla de calibración.
 *
 * El comando de calibración lo arma el servidor y lo entrega este endpoint; acá
 * sólo se lo reenvía al puente que corre en la PC del taller, que es el único
 * que puede escribir en el USB. Mismo camino que usa el botón Imprimir del
 * diseñador.
 */
(function () {
  'use strict';

  const boton = document.getElementById('et-calibrar-impresora');
  if (!boton) return;

  const estado = document.getElementById('et-calibrar-estado');
  const PUENTE = 'http://127.0.0.1:9101';

  function avisar(texto, clase) {
    estado.textContent = texto;
    estado.className = `small align-self-center text-${clase}`;
  }

  boton.addEventListener('click', async () => {
    boton.disabled = true;
    avisar('Calibrando…', 'muted');

    let zpl;
    try {
      const respuesta = await fetch(boton.dataset.url);
      const datos = await respuesta.json();
      if (!datos.ok) throw new Error(datos.error);
      zpl = datos.zpl;
    } catch (error) {
      avisar('No se pudo pedir el comando de calibración al servidor.', 'danger');
      boton.disabled = false;
      return;
    }

    try {
      // El corte corto es a propósito: si el puente no está levantado, el
      // pedido a una dirección local falla enseguida y no tiene sentido dejar
      // al usuario esperando.
      const respuesta = await fetch(`${PUENTE}/imprimir`, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
        body: zpl,
        signal: AbortSignal.timeout(4000),
      });
      const datos = await respuesta.json();
      avisar(
        datos.ok
          ? 'Listo. La impresora avanzó midiendo y guardó la medida.'
          : datos.error,
        datos.ok ? 'success' : 'danger',
      );
    } catch (error) {
      avisar('No se encontró el puente de impresión en esta computadora.', 'warning');
    }

    boton.disabled = false;
  });
})();
