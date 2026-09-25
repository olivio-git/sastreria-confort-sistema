// imprimir_etiquetas.js — imprimir en la térmica desde la prenda y sus unidades.
//
// Los botones [data-imprimir-etiqueta] antes abrían un PDF, que el navegador
// mandaba a la impresora por el driver de Windows: sin la calibración del
// sistema, con los márgenes y el tamaño de hoja del driver, y con el texto
// rasterizado a 203 dpi. La etiqueta salía corrida, recortada y serruchada.
//
// Ahora hacen lo mismo que el diseñador: le piden el ZPL al servidor (la misma
// plantilla, la misma calibración) y se lo pasan al puente de la PC del taller.
// Si no hay puente, ofrecen el PDF avisando que puede salir mal.
(function () {
  'use strict';

  function contenedor() {
    return document.querySelector('.page-body .container-xl') || document.body;
  }

  // Mismo aspecto que los mensajes de Django (_partials/mensajes.html). El
  // texto va con textContent: los errores vienen del servidor.
  function avisar(tipo, texto, enlace) {
    var alerta = document.createElement('div');
    alerta.className = 'alert alert-' + tipo + ' alert-dismissible fade show mb-3';
    alerta.setAttribute('role', 'alert');
    alerta.appendChild(document.createTextNode(texto));
    if (enlace) {
      alerta.appendChild(document.createTextNode(' '));
      var a = document.createElement('a');
      a.href = enlace.href;
      a.target = '_blank';
      a.className = 'alert-link';
      a.textContent = enlace.texto;
      alerta.appendChild(a);
    }
    var cerrar = document.createElement('button');
    cerrar.type = 'button';
    cerrar.className = 'btn-close';
    cerrar.setAttribute('data-bs-dismiss', 'alert');
    alerta.appendChild(cerrar);
    var c = contenedor();
    c.insertBefore(alerta, c.firstChild);
    alerta.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  document.addEventListener('click', async function (e) {
    var boton = e.target.closest('[data-imprimir-etiqueta]');
    if (!boton || boton.disabled) return;
    boton.disabled = true;
    try {
      var datos;
      try {
        datos = await (await fetch(boton.dataset.imprimirEtiqueta,
                                   { credentials: 'same-origin' })).json();
      } catch (error) {
        avisar('danger', 'No se pudo generar la etiqueta. Probá de nuevo.');
        return;
      }
      if (!datos.ok) {
        avisar('danger', datos.error || 'No se pudo generar la etiqueta.');
        return;
      }

      var salida;
      try {
        salida = await window.PuenteImpresion.imprimir(datos.zpl);
      } catch (error) {
        avisar('warning',
          'No se encontró el puente de impresión en esta computadora: fijate que esté '
          + 'abierto (el ícono al lado del reloj). Como alternativa podés',
          { href: boton.dataset.pdf,
            texto: 'abrir el PDF, pero impreso desde el navegador puede salir corrido o recortado.' });
        return;
      }

      if (salida.ok) {
        avisar('success', datos.cantidad === 1
          ? 'Etiqueta enviada a la impresora.'
          : datos.cantidad + ' etiquetas enviadas a la impresora.');
      } else {
        avisar('danger', salida.error || 'La impresora no respondió.');
      }
    } finally {
      boton.disabled = false;
    }
  });
})();
