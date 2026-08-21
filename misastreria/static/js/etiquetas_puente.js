/* Cliente del puente de impresión.
 *
 * El puente corre en la PC del taller y es el único que puede escribir en el
 * USB de la impresora — el servidor es Linux y no ve el puerto. Ver
 * puente_impresion/README.md.
 *
 * Vive en su propio archivo porque lo usan dos pantallas: la de ajustes de
 * impresora y el diseñador. Cuando el modal de ajustes entró al diseñador,
 * tener la dirección y el timeout escritos en dos lugares habría sido
 * garantía de que uno de los dos quedara viejo.
 *
 * Expone `window.PuenteImpresion`.
 */
(function () {
  'use strict';

  const PUENTE = 'http://127.0.0.1:9101';

  /* El corte corto es a propósito: si el puente no está levantado, el pedido a
     una dirección local falla enseguida y no tiene sentido dejar al usuario
     esperando antes de pasar al plan B. */
  const CORTE_MS = 4000;

  /* Manda ZPL crudo al puente. Devuelve lo que responde el puente
     (`{ok, mensaje}` o `{ok:false, error}`); si no hay puente escuchando,
     lanza — que es lo que deja al llamador decidir el plan B. */
  async function imprimir(zpl) {
    const respuesta = await fetch(`${PUENTE}/imprimir`, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      body: zpl,
      signal: AbortSignal.timeout(CORTE_MS),
    });
    return respuesta.json();
  }

  /* Le hace medir a la impresora dónde termina cada etiqueta.
   *
   * El comando lo arma el servidor y lo entrega `url`: el conocimiento de ZPL
   * vive en un solo lugar del código, no acá. Devuelve `{ok, mensaje}` con el
   * texto ya listo para mostrarle al usuario. */
  async function calibrar(url) {
    let zpl;
    try {
      const datos = await (await fetch(url)).json();
      if (!datos.ok) throw new Error(datos.error);
      zpl = datos.zpl;
    } catch (error) {
      return { ok: false, mensaje: 'No se pudo pedir el comando de calibración al servidor.' };
    }

    try {
      const salida = await imprimir(zpl);
      return {
        ok: !!salida.ok,
        mensaje: salida.ok
          ? 'Listo. La impresora avanzó midiendo y guardó la medida.'
          : salida.error,
      };
    } catch (error) {
      return { ok: false, mensaje: 'No se encontró el puente de impresión en esta computadora.' };
    }
  }

  window.PuenteImpresion = { imprimir, calibrar };
})();
