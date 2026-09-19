/* Selector de prendas físicas (PrendaItem), compartido.
 *
 * Lo usan el diseñador de etiquetas y los formularios de venta y alquiler.
 * La caja HTML es _partials/selector_items.html; este archivo le pone el
 * comportamiento y no sabe nada de quién lo llama: devuelve el item elegido
 * por callback y que cada pantalla haga lo suyo.
 *
 *   const sel = SelectorItems.crear({
 *     estado: 'disponible',      // sólo lo que se puede cargar hoy
 *     sinConjunto: true,         // los conjuntos se cargan enteros, no sueltos
 *     tipo: 'alquiler',          // pestaña con la que abre
 *     agrupar: true,             // un renglón por modelo, no por unidad
 *     orden: 'desgaste',         // qué unidad asigna: 'desgaste' | 'fifo'
 *     cerrarAlElegir: false,     // seguir cargando prendas sin reabrir
 *     onElegir(item) { ... },
 *   });
 *   sel.abrir();
 */
window.SelectorItems = (function () {
  'use strict';

  const TOPE = 40;   // el endpoint corta acá; hay que avisarlo o parece la lista entera

  function escaparHtml(texto) {
    const d = document.createElement('div');
    d.textContent = String(texto ?? '');
    return d.innerHTML;
  }

  function badgeTipo(tipo, etiqueta) {
    const clase = tipo === 'venta' ? 'bg-purple-lt' : 'bg-azure-lt';
    return `<span class="badge ${clase}">${escaparHtml(etiqueta || '')}</span>`;
  }

  function fila(it) {
    return `<tr data-item="${it.prenda_item_id}">
      <td class="sel-items-unidad-cod">${escaparHtml(it.codigo_item)}</td>
      <td class="sel-items-nombre">${escaparHtml(it.sku_nombre)}</td>
      <td class="sel-items-medida">${escaparHtml(it.detalle)}</td>
      <td>${badgeTipo(it.tipo, it.tipo_label)}</td>
      <td class="text-end">
        <button type="button" class="btn btn-primary sel-items-btn" data-elegir>Elegir</button>
      </td>
    </tr>`;
  }

  // ── Modo agrupado ─────────────────────────────────────────────────────────
  // Un renglón por modelo. Nadie busca «la camisa blanca número 13»: busca una
  // camisa blanca M. Cuál de las 17 le toque lo decide el servidor por la regla
  // de asignación, y el expansor queda para cuando la unidad sí importa —una de
  // alquiler más gastada que otra.

  function filaGrupo(g, indice) {
    const varias = g.unidades.length > 1;
    const agotado = g.disponibles === 0;
    return `<tr data-grupo="${indice}" class="sel-items-modelo">
      <td>
        <div class="sel-items-nombre">${escaparHtml(g.sku_nombre)}</div>
        <div class="sel-items-codigo">${escaparHtml(g.sku_codigo)}</div>
      </td>
      <td class="sel-items-medida">${escaparHtml(g.detalle) || '—'}</td>
      <td>${badgeTipo(g.tipo, g.tipo_label)}</td>
      <td class="sel-items-disp ${agotado ? 'agotado' : ''}">
        <span class="sel-items-disp-n">${g.disponibles}</span>
        <span class="sel-items-disp-t">disponible${g.disponibles === 1 ? '' : 's'}</span>
      </td>
      <td class="text-end">
        <button type="button" class="btn btn-primary sel-items-btn" data-elegir-grupo
                ${agotado ? 'disabled' : ''}>Elegir</button>
        ${varias ? `<div class="mt-2">
          <button type="button" class="btn btn-outline-secondary btn-sm sel-items-vermas"
                  data-expandir>Ver las ${g.unidades.length} unidades</button>
        </div>` : ''}
      </td>
    </tr>`;
  }

  function filaUnidad(u, indice) {
    const usos = (u.veces_alquilado != null)
      ? `${u.veces_alquilado} alquiler${u.veces_alquilado === 1 ? '' : 'es'}`
      : '';
    const detalles = [u.condicion_label, usos, u.ubicacion].filter(Boolean);
    return `<tr data-grupo="${indice}" data-unidad="${u.prenda_item_id}" class="sel-items-unidad">
      <td class="sel-items-unidad-cod">${escaparHtml(u.codigo_item)}</td>
      <td colspan="3" class="sel-items-unidad-det">${escaparHtml(detalles.join(' · '))}</td>
      <td class="text-end">
        <button type="button" class="btn btn-outline-primary sel-items-btn-chico"
                data-elegir-unidad>Elegir esta</button>
      </td>
    </tr>`;
  }

  // La cabecera cambia con el modo: agrupado se lee «qué prenda», suelto se lee
  // «qué unidad». Con los mismos títulos, una de las dos miente.
  function pintarCabecera(agrupado) {
    const cabecera = document.getElementById('sel-items-cabecera');
    if (!cabecera) return;
    cabecera.innerHTML = agrupado
      ? `<tr><th>Prenda</th><th style="width:12rem">Talla y color</th>
         <th style="width:8rem">Tipo</th><th style="width:9rem">Cantidad</th>
         <th style="width:11rem"></th></tr>`
      : `<tr><th style="width:11rem">Código</th><th>Prenda</th>
         <th style="width:9rem">Detalle</th><th style="width:7rem">Tipo</th>
         <th style="width:11rem"></th></tr>`;
  }

  function crear(opciones) {
    const opts = opciones || {};
    const modalEl = document.getElementById('sel-items-modal');
    if (!modalEl) return { abrir() {} };   // la pantalla no incluyó el partial

    const buscador = document.getElementById('sel-items-buscar');
    const cuerpo = document.getElementById('sel-items-cuerpo');
    const aviso = document.getElementById('sel-items-aviso');
    const grupoTipo = document.getElementById('sel-items-tipo');

    let modal = null;
    let temporizador = null;
    let tipo = opts.tipo || '';
    let ultimos = [];

    // El botón activo se marca acá y no en la plantilla: la pestaña inicial
    // depende del formulario que incluye el partial, no del partial.
    function pintarTipoActivo() {
      grupoTipo.querySelectorAll('[data-tipo]').forEach((b) =>
        b.classList.toggle('active', b.dataset.tipo === tipo));
    }

    function vacio(mensaje, clase) {
      cuerpo.innerHTML = `<tr><td colspan="5" class="text-center ${clase} py-4">`
        + escaparHtml(mensaje) + '</td></tr>';
      aviso.textContent = '';
    }

    async function buscar() {
      const parametros = new URLSearchParams({ q: buscador.value.trim() });
      if (tipo) parametros.set('tipo', tipo);
      if (opts.estado) parametros.set('estado', opts.estado);
      if (opts.sinConjunto) parametros.set('sin_conjunto', '1');
      if (opts.datos) parametros.set('datos', '1');
      if (opts.agrupar) parametros.set('agrupar', '1');
      if (opts.orden) parametros.set('orden', opts.orden);

      expandidos = new Set();
      try {
        const respuesta = await fetch(`${modalEl.dataset.url}?${parametros}`);
        const datos = await respuesta.json();
        ultimos = datos.items || [];

        if (!ultimos.length) {
          vacio('Ninguna prenda coincide con la búsqueda.', 'text-muted');
          return;
        }
        pintar();
        const n = ultimos.length;
        const sustantivo = opts.agrupar
          ? `modelo${n === 1 ? '' : 's'}`
          : `prenda${n === 1 ? '' : 's'}`;
        aviso.textContent = n >= TOPE
          ? `Se muestran los primeros ${TOPE}. Afiná la búsqueda para ver el resto.`
          : `${n} ${sustantivo}.`;
      } catch (error) {
        vacio('No se pudo consultar el inventario.', 'text-danger');
      }
    }

    // Los grupos expandidos se recuerdan por índice: el cuerpo se reescribe
    // entero al elegir una unidad y sin esto el expansor se cerraría solo.
    let expandidos = new Set();

    function pintar() {
      pintarCabecera(!!opts.agrupar);
      if (!opts.agrupar) {
        cuerpo.innerHTML = ultimos.map(fila).join('');
        return;
      }
      cuerpo.innerHTML = ultimos.map((g, i) => {
        let html = filaGrupo(g, i);
        if (expandidos.has(i)) html += g.unidades.map((u) => filaUnidad(u, i)).join('');
        return html;
      }).join('');
    }

    // Al llevarse una unidad, el modelo tiene una menos. Sin esto el contador
    // sigue diciendo 5 después de cargar las 5, y la siguiente que asigne ya
    // está en la tabla del formulario.
    function consumir(indice, item) {
      const g = ultimos[indice];
      if (!g) return;
      g.unidades = g.unidades.filter(
        (u) => String(u.prenda_item_id) !== String(item.prenda_item_id));
      g.disponibles = g.unidades.length;
      if (!g.unidades.length) expandidos.delete(indice);
      pintar();
    }

    function entregar(item) {
      if (typeof opts.onElegir === 'function') opts.onElegir(item);
      if (opts.cerrarAlElegir !== false) {
        if (modal) modal.hide();
        buscador.value = '';
      }
    }

    // Un solo listener delegado en el tbody en vez de uno por fila: el cuerpo
    // se reescribe entero en cada búsqueda y los listeners por fila se pierden.
    cuerpo.addEventListener('click', (evento) => {
      const trGrupo = evento.target.closest('[data-grupo]');

      if (trGrupo && evento.target.closest('[data-expandir]')) {
        const i = Number(trGrupo.dataset.grupo);
        if (expandidos.has(i)) expandidos.delete(i); else expandidos.add(i);
        pintar();
        return;
      }

      if (trGrupo && evento.target.closest('[data-elegir-unidad]')) {
        const i = Number(trGrupo.dataset.grupo);
        const item = (ultimos[i].unidades || []).find(
          (u) => String(u.prenda_item_id) === trGrupo.dataset.unidad);
        if (!item) return;
        entregar(item);
        if (opts.cerrarAlElegir === false) consumir(i, item);
        return;
      }

      if (trGrupo && !trGrupo.dataset.unidad) {
        // Elegir el modelo se lleva la primera unidad, que el servidor ya
        // ordenó por la regla de asignación (menos usada o más vieja).
        const i = Number(trGrupo.dataset.grupo);
        const item = (ultimos[i].unidades || [])[0];
        if (!item) return;
        entregar(item);
        if (opts.cerrarAlElegir === false) consumir(i, item);
        return;
      }

      const tr = evento.target.closest('[data-item]');
      if (!tr) return;
      const item = ultimos.find((i) => String(i.prenda_item_id) === tr.dataset.item);
      if (!item) return;
      entregar(item);
      if (opts.cerrarAlElegir === false) {
        // Queda abierto para cargar varias prendas seguidas; la fila elegida se
        // apaga para no cargarla dos veces sin darse cuenta.
        tr.classList.add('sel-items-tomada');
        const boton = tr.querySelector('[data-elegir]');
        if (boton) {
          boton.disabled = true;
          boton.textContent = 'Agregada';
          boton.classList.replace('btn-primary', 'btn-outline-success');
        }
      }
    });

    buscador.addEventListener('input', () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(buscar, 300);
    });

    grupoTipo.addEventListener('click', (evento) => {
      const boton = evento.target.closest('[data-tipo]');
      if (!boton) return;
      tipo = boton.dataset.tipo;
      pintarTipoActivo();
      buscar();
    });

    // El foco se pide cuando el modal terminó de aparecer: antes no tiene
    // efecto porque el elemento todavía no es visible.
    modalEl.addEventListener('shown.bs.modal', () => buscador.focus());

    return {
      abrir() {
        // El modal se instancia al primer uso: así la pantalla no depende de
        // que el bundle de Bootstrap haya llegado antes que este archivo.
        if (!modal) modal = new bootstrap.Modal(modalEl);
        pintarTipoActivo();
        modal.show();
        buscar();          // abre con las primeras prendas ya listadas
      },
      set tipo(valor) { tipo = valor || ''; },
      get tipo() { return tipo; },
    };
  }

  return { crear };
})();
