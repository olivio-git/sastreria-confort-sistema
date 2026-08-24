/* Editor de etiquetas.
 *
 * El lienzo es un espejo de los renderers del servidor (etiquetas_pdf.py y
 * etiquetas_zpl.py): dibuja la MISMA lista de elementos con las mismas reglas de
 * posición, ajuste y alineación. Por eso las constantes de abajo repiten las de
 * `etiquetas.py` — si allá cambian, acá también.
 *
 * Lo que el lienzo NO puede garantizar es la tipografía: usa las fuentes del
 * navegador y el PDF las de PostScript, así que un texto al límite puede entrar
 * acá y no allá. Para eso está «Ver PDF», que es la verdad.
 *
 * Unidades: todo se guarda en puntos de cabezal a 203 dpi, con el origen arriba
 * a la izquierda. `escala` es cuántos píxeles de pantalla vale un punto.
 */
(function () {
  'use strict';

  const app = document.getElementById('et-app');
  if (!app) return;

  // ── Constantes espejadas del servidor ──────────────────────────────────────
  const ASCENDENTE = 0.78;   // fracción del cuerpo por encima de la línea base
  const INTERLINEA = 1.15;
  const FAMILIAS = {
    sans:  'Helvetica, Arial, sans-serif',
    serif: '"Times New Roman", Times, serif',
    mono:  '"Courier New", Courier, monospace',
  };
  // Un Code 128 B ocupa 35 módulos fijos más 11 por carácter.
  const modulosCode128 = (dato) => 35 + 11 * dato.length;
  const PUNTOS_POR_MM = 203 / 25.4;
  const QR_TAM_MIN = 58;

  // El diseño se guarda en puntos de cabezal, pero al usuario se le habla
  // siempre en milímetros: es lo que puede medir con una regla contra el rollo.
  // Los puntos no aparecen en ninguna parte de la interfaz.
  const aMm = (puntos) => puntos / PUNTOS_POR_MM;
  const aPuntos = (mm) => Math.round(mm * PUNTOS_POR_MM);

  // ── Constantes del editor ──────────────────────────────────────────────────
  const REGLA = 20;          // ancho de las reglas, en píxeles de pantalla
  const IMAN = 5;            // distancia de enganche, en píxeles de pantalla
  const MANIJA = 7;          // lado de las manijas de redimensión, en píxeles
  const esCuadrado = (el) => el.tipo === 'simbolo'
    || (el.tipo === 'barcode' && el.simbologia === 'qr');

  // ── Lectura de datos iniciales ─────────────────────────────────────────────
  const leer = (id) => JSON.parse(document.getElementById(id).textContent);

  // El catálogo y el ancho se leen ANTES que `estado` porque `normalizar()` los
  // necesita al completar los elementos iniciales, y en ese momento `estado`
  // todavía está en su zona muerta temporal.
  const CATALOGO = leer('et-datos-simbolos');
  const CAMPOS = leer('et-datos-campos');
  const MUESTRA = leer('et-datos-muestra');
  let anchoActual = parseInt(app.dataset.ancho, 10) || 400;

  const estado = {
    elementos: leer('et-datos-elementos').map(normalizar),
    ancho: anchoActual,
    alto: parseInt(app.dataset.alto, 10) || 240,
    seleccion: -1,
    escala: 2,
    herramienta: 'seleccion',
    grilla: false,
    iman: true,
    itemId: null,
    guardado: !!app.dataset.id,
    sucio: false,
  };

  const csrf = app.querySelector('[name=csrfmiddlewaretoken]').value;
  const lienzo = document.getElementById('et-lienzo');
  const ctx = lienzo.getContext('2d');

  // Contexto aparte, sin transformaciones, sólo para medir texto: si se midiera
  // con el contexto del dibujo habría que descontar la escala en cada llamada.
  const medidor = document.createElement('canvas').getContext('2d');

  // Los símbolos se piden al servidor como PNG (el mismo dibujo que va al ^GF y
  // al PDF) y se cachean: el lienzo se repinta muchas veces por segundo al
  // arrastrar y no puede estar pidiendo la misma imagen cada vez.
  const cacheSimbolos = new Map();

  function imagenSimbolo(clave, tam) {
    const llave = `${clave}@${tam}`;
    if (cacheSimbolos.has(llave)) return cacheSimbolos.get(llave);
    const img = new Image();
    img.onload = dibujar;      // al llegar, se repinta con el símbolo ya puesto
    img.src = app.dataset.urlSimbolo.replace('CLAVE', encodeURIComponent(clave))
              + '?tam=' + tam;
    cacheSimbolos.set(llave, img);
    return img;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Normalización (espejo de etiquetas.normalizar_elemento)
  // ═══════════════════════════════════════════════════════════════════════════

  function clamp(valor, min, max) {
    const n = Math.round(+valor);
    return Number.isFinite(n) ? Math.max(min, Math.min(max, n)) : min;
  }

  const clonar = (valor) => JSON.parse(JSON.stringify(valor));

  function primerSimbolo() {
    const grupos = Object.values(CATALOGO);
    return grupos.length && grupos[0].length ? grupos[0][0].clave : 'seco';
  }

  function normalizar(bruto) {
    const el = Object.assign({}, bruto);
    el.tipo = el.tipo || 'texto';
    el.x = Math.max(0, Math.round(+el.x || 0));
    el.y = Math.max(0, Math.round(+el.y || 0));
    el.rotacion = ['N', 'R', 'I', 'B'].includes(el.rotacion) ? el.rotacion : 'N';
    el.visible = el.visible !== false;
    el.bloqueado = !!el.bloqueado;
    el.nombre = String(el.nombre ?? '').slice(0, 60);

    if (el.tipo === 'texto') {
      el.texto = el.texto ?? '';
      el.tamano = clamp(el.tamano ?? 24, 6, 400);
      el.fuente = FAMILIAS[el.fuente] ? el.fuente : 'sans';
      el.negrita = !!el.negrita;
      el.alineacion = ['izquierda', 'centro', 'derecha'].includes(el.alineacion)
        ? el.alineacion : 'izquierda';
      el.renglones = clamp(el.renglones ?? 1, 1, 9);
      el.tracking = Math.max(0, Math.min(40, +el.tracking || 0));
      el.autoajustar = !!el.autoajustar;
      el.tamano_min = clamp(el.tamano_min ?? 10, 4, el.tamano);
      el.ancho_bloque = clamp(el.ancho_bloque ?? 0, 0, 4000)
        || Math.max(1, anchoActual - el.x);
    } else if (el.tipo === 'barcode') {
      el.texto = el.texto || '{codigo_barra}';
      el.simbologia = ['code128', 'code39', 'ean13', 'qr'].includes(el.simbologia)
        ? el.simbologia : 'code128';
      el.modulo = clamp(el.modulo ?? 2, 1, 10);
      el.alto_barra = clamp(el.alto_barra ?? 100, 10, 800);
      el.mostrar_texto = el.mostrar_texto !== false;
      el.centrar = !!el.centrar;
      el.tamano_texto = clamp(el.tamano_texto ?? 18, 6, 100);
      if (el.simbologia === 'qr') el.alto_barra = clamp(el.alto_barra, QR_TAM_MIN, 800);
    } else if (el.tipo === 'simbolo') {
      el.clave = el.clave || primerSimbolo();
      el.tam = clamp(el.tam ?? 48, 16, 300);
      el.leyenda = el.leyenda ?? '';
      el.leyenda_lado = el.leyenda_lado === 'derecha' ? 'derecha' : 'abajo';
      el.tam_leyenda = clamp(el.tam_leyenda ?? 14, 4, 100);
    } else if (el.tipo === 'linea') {
      el.rotacion = 'N';
      el.orientacion = el.orientacion === 'vertical' ? 'vertical' : 'horizontal';
      const largoAnterior = el.orientacion === 'vertical' ? el.alto : el.ancho;
      el.largo = clamp(el.largo ?? largoAnterior ?? 120, 1, 4000);
      el.grosor = clamp(el.grosor ?? 2, 1, 50);
    } else {
      el.tipo = 'caja';
      el.rotacion = 'N';
      el.ancho = clamp(el.ancho ?? 200, 1, 4000);
      el.alto = clamp(el.alto ?? 2, 1, 4000);
      el.grosor = clamp(el.grosor ?? 2, 1, 200);
      el.redondeo = clamp(el.redondeo ?? 0, 0, 100);
      el.relleno = !!el.relleno;
    }
    return el;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Historial
  //
  // Se guardan instantáneas completas de la lista y no diffs: una etiqueta son
  // diez o veinte elementos chicos, así que copiar todo cuesta nada y evita toda
  // la complejidad de invertir operaciones.
  // ═══════════════════════════════════════════════════════════════════════════

  const historial = { pila: [], indice: -1 };
  const LIMITE_HISTORIAL = 60;

  function instantanea() {
    return JSON.stringify({
      elementos: estado.elementos, ancho: estado.ancho, alto: estado.alto,
    });
  }

  function registrar() {
    const actual = instantanea();
    if (historial.pila[historial.indice] === actual) return;
    // Al hacer algo nuevo después de deshacer, se descarta lo que había adelante.
    historial.pila.splice(historial.indice + 1);
    historial.pila.push(actual);
    if (historial.pila.length > LIMITE_HISTORIAL) historial.pila.shift();
    historial.indice = historial.pila.length - 1;
    marcarSucio();
    refrescarHistorial();
  }

  function restaurar(paso) {
    const destino = historial.indice + paso;
    if (destino < 0 || destino >= historial.pila.length) return;
    historial.indice = destino;
    const datos = JSON.parse(historial.pila[destino]);
    estado.elementos = datos.elementos.map(normalizar);
    aplicarMedidas(datos.ancho, datos.alto, { silencioso: true });
    if (estado.seleccion >= estado.elementos.length) estado.seleccion = -1;
    marcarSucio();
    refrescarHistorial();
    repintarTodo();
  }

  function refrescarHistorial() {
    document.getElementById('et-deshacer').disabled = historial.indice <= 0;
    document.getElementById('et-rehacer').disabled =
      historial.indice >= historial.pila.length - 1;
  }

  function marcarSucio() {
    estado.sucio = true;
    document.getElementById('et-sin-guardar').hidden = false;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Datos de la vista previa
  // ═══════════════════════════════════════════════════════════════════════════

  let datosActuales = Object.assign({}, MUESTRA);

  function sustituir(texto) {
    let salida = String(texto ?? '');
    for (const [clave, valor] of Object.entries(datosActuales)) {
      salida = salida.split('{' + clave + '}').join(valor ?? '');
    }
    return salida;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Medición y ajuste de texto (espejo del renderer PDF)
  // ═══════════════════════════════════════════════════════════════════════════

  function fuenteCss(el, tamano) {
    return `${el.negrita ? 'bold ' : ''}${tamano}px ${FAMILIAS[el.fuente]}`;
  }

  function anchoTexto(texto, el, tamano) {
    medidor.font = fuenteCss(el, tamano);
    return medidor.measureText(texto).width + el.tracking * Math.max(0, texto.length - 1);
  }

  function partir(texto, el, tamano, anchoMax) {
    const lineas = [];
    for (const parrafo of String(texto).split('\n')) {
      let actual = '';
      for (const palabra of parrafo.split(/\s+/).filter(Boolean)) {
        const tentativa = actual ? actual + ' ' + palabra : palabra;
        if (actual && anchoTexto(tentativa, el, tamano) > anchoMax) {
          lineas.push(actual);
          actual = palabra;
        } else {
          actual = tentativa;
        }
      }
      lineas.push(actual);
    }
    return lineas;
  }

  function tamanoQueEntra(texto, el, anchoMax) {
    let tamano = el.tamano;
    while (tamano > el.tamano_min) {
      const lineas = partir(texto, el, tamano, anchoMax);
      if (lineas.length <= el.renglones
          && lineas.every((ln) => anchoTexto(ln, el, tamano) <= anchoMax)) break;
      tamano -= 0.5;
    }
    return Math.max(tamano, el.tamano_min);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Caja envolvente
  // ═══════════════════════════════════════════════════════════════════════════

  function caja(el) {
    if (el.tipo === 'texto') {
      const texto = sustituir(el.texto) || ' ';
      const tamano = el.autoajustar ? tamanoQueEntra(texto, el, el.ancho_bloque) : el.tamano;
      const lineas = partir(texto, el, tamano, el.ancho_bloque).slice(0, el.renglones);
      return {
        x: el.x, y: el.y, ancho: el.ancho_bloque,
        alto: Math.max(tamano, lineas.length * tamano * INTERLINEA),
      };
    }
    if (el.tipo === 'barcode') {
      const dato = sustituir(el.texto).trim() || ' ';
      if (el.simbologia === 'qr') {
        return { x: el.x, y: el.y, ancho: el.alto_barra, alto: el.alto_barra };
      }
      const ancho = modulosCode128(dato) * el.modulo;
      const x = el.centrar ? Math.max(0, Math.round((estado.ancho - ancho) / 2)) : el.x;
      const extra = el.mostrar_texto ? el.tamano_texto + 2 : 0;
      return { x, y: el.y, ancho, alto: el.alto_barra + extra };
    }
    if (el.tipo === 'simbolo') {
      const leyenda = sustituir(el.leyenda).trim();
      if (!leyenda) return { x: el.x, y: el.y, ancho: el.tam, alto: el.tam };
      medidor.font = `${el.tam_leyenda}px ${FAMILIAS.sans}`;
      const anchoLeyenda = medidor.measureText(leyenda).width;
      if (el.leyenda_lado === 'derecha') {
        return {
          x: el.x, y: el.y,
          ancho: el.tam + 6 + anchoLeyenda,
          alto: Math.max(el.tam, el.tam_leyenda),
        };
      }
      return {
        x: el.x, y: el.y,
        ancho: Math.max(el.tam, anchoLeyenda),
        alto: el.tam + 4 + el.tam_leyenda,
      };
    }
    if (el.tipo === 'linea') {
      return el.orientacion === 'vertical'
        ? { x: el.x, y: el.y, ancho: el.grosor, alto: el.largo }
        : { x: el.x, y: el.y, ancho: el.largo, alto: el.grosor };
    }
    return { x: el.x, y: el.y, ancho: el.ancho, alto: el.alto };
  }

  function cajaTransformacion(el) {
    // La leyenda forma parte de los límites y del hit-test, pero no se escala al
    // redimensionar el icono. Las manijas deben seguir el cuadrado transformable.
    if (el.tipo === 'simbolo') {
      return { x: el.x, y: el.y, ancho: el.tam, alto: el.tam };
    }
    return caja(el);
  }

  /* Traduce una caja nueva de vuelta a las propiedades del elemento.
   * Cada tipo se redimensiona por lo que tiene sentido: un texto por su ancho de
   * bloque y su cuerpo, un código por el grosor de barra y el alto, un símbolo
   * por su lado (siempre cuadrado, que es como los define la norma). */
  function aplicarCaja(el, nueva, original) {
    el.x = Math.max(0, Math.round(nueva.x));
    el.y = Math.max(0, Math.round(nueva.y));

    const factorH = original.alto > 0 ? nueva.alto / original.alto : 1;

    if (el.tipo === 'texto') {
      el.ancho_bloque = clamp(nueva.ancho, 8, 4000);
      el.tamano = clamp(el.tamano * factorH, 6, 400);
      el.tamano_min = clamp(el.tamano_min * factorH, 4, el.tamano);
    } else if (el.tipo === 'barcode') {
      if (el.simbologia === 'qr') {
        el.alto_barra = clamp(Math.min(nueva.ancho, nueva.alto), QR_TAM_MIN, 800);
      } else {
        const dato = sustituir(el.texto).trim() || ' ';
        el.modulo = clamp(nueva.ancho / modulosCode128(dato), 1, 10);
        const extra = el.mostrar_texto ? el.tamano_texto + 2 : 0;
        el.alto_barra = clamp(nueva.alto - extra, 10, 800);
      }
    } else if (el.tipo === 'simbolo') {
      el.tam = clamp(Math.min(nueva.ancho, nueva.alto), 16, 300);
    } else if (el.tipo === 'linea') {
      if (el.orientacion === 'vertical') {
        el.largo = clamp(nueva.alto, 1, 4000);
        el.grosor = clamp(nueva.ancho, 1, 50);
      } else {
        el.largo = clamp(nueva.ancho, 1, 4000);
        el.grosor = clamp(nueva.alto, 1, 50);
      }
    } else {
      el.ancho = clamp(nueva.ancho, 1, 4000);
      el.alto = clamp(nueva.alto, 1, 4000);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Dibujo
  // ═══════════════════════════════════════════════════════════════════════════

  let guiasVisibles = [];      // guías de enganche activas mientras se arrastra
  let frameDibujo = null;

  function dibujar() {
    if (frameDibujo !== null) return;
    frameDibujo = window.requestAnimationFrame(() => {
      frameDibujo = null;
      dibujarAhora();
    });
  }

  function dibujarAhora() {
    const dpr = window.devicePixelRatio || 1;
    const anchoPx = estado.ancho * estado.escala;
    const altoPx = estado.alto * estado.escala;
    const anchoBuffer = Math.max(1, Math.round((anchoPx + REGLA) * dpr));
    const altoBuffer = Math.max(1, Math.round((altoPx + REGLA) * dpr));

    // Cambiar width/height recrea todo el backing store. Antes ocurría en cada
    // pointermove aunque el tamaño no hubiera cambiado y producía tirones.
    if (lienzo.width !== anchoBuffer) lienzo.width = anchoBuffer;
    if (lienzo.height !== altoBuffer) lienzo.height = altoBuffer;
    lienzo.style.width = (anchoPx + REGLA) + 'px';
    lienzo.style.height = (altoPx + REGLA) + 'px';

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, anchoPx + REGLA, altoPx + REGLA);

    dibujarReglas(anchoPx, altoPx);

    // A partir de acá se dibuja en unidades de la etiqueta.
    ctx.save();
    ctx.translate(REGLA, REGLA);
    ctx.scale(estado.escala, estado.escala);

    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, estado.ancho, estado.alto);
    if (estado.grilla) dibujarGrilla();

    for (const el of estado.elementos) {
      if (!el.visible) continue;
      ctx.save();
      const grados = { N: 0, R: 90, I: 180, B: 270 }[el.rotacion];
      if (grados) {
        ctx.translate(el.x, el.y);
        ctx.rotate((grados * Math.PI) / 180);
        ctx.translate(-el.x, -el.y);
      }
      ctx.fillStyle = '#000';
      ctx.strokeStyle = '#000';
      if (el.tipo === 'texto') dibujarTexto(el);
      else if (el.tipo === 'barcode') dibujarBarcode(el);
      else if (el.tipo === 'simbolo') dibujarSimbolo(el);
      else if (el.tipo === 'linea') dibujarLinea(el);
      else dibujarCaja(el);
      ctx.restore();
    }
    ctx.restore();

    // Adornos del editor: en píxeles de pantalla, para que no engorden al hacer
    // zoom. Un marco de selección de 1 px tiene que medir 1 px siempre.
    dibujarGuias();
    if (estado.seleccion >= 0) dibujarSeleccion(estado.elementos[estado.seleccion]);
  }

  const aPantallaX = (x) => REGLA + x * estado.escala;
  const aPantallaY = (y) => REGLA + y * estado.escala;

  function dibujarReglas(anchoPx, altoPx) {
    ctx.fillStyle = '#eef1f5';
    ctx.fillRect(0, 0, anchoPx + REGLA, REGLA);
    ctx.fillRect(0, 0, REGLA, altoPx + REGLA);
    ctx.strokeStyle = '#c7ced8';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, REGLA - .5); ctx.lineTo(anchoPx + REGLA, REGLA - .5);
    ctx.moveTo(REGLA - .5, 0); ctx.lineTo(REGLA - .5, altoPx + REGLA);
    ctx.stroke();

    // Marcas cada 5 mm, con número cada 10 mm. Si el zoom las apretuja, se pasa
    // a cada 10 y 20: una regla ilegible estorba más de lo que ayuda.
    const pasoMm = 5 * PUNTOS_POR_MM * estado.escala < 22 ? 10 : 5;
    const paso = pasoMm * PUNTOS_POR_MM;
    ctx.fillStyle = '#6b7688';
    ctx.font = '8px system-ui, sans-serif';
    ctx.textBaseline = 'top';
    ctx.strokeStyle = '#9aa5b5';

    ctx.beginPath();
    for (let p = 0, mm = 0; p <= estado.ancho; p += paso, mm += pasoMm) {
      const x = Math.round(aPantallaX(p)) + .5;
      const largo = mm % (pasoMm * 2) === 0 ? 7 : 4;
      ctx.moveTo(x, REGLA - largo); ctx.lineTo(x, REGLA);
      if (mm % (pasoMm * 2) === 0) ctx.fillText(String(mm), x + 2, 2);
    }
    for (let p = 0, mm = 0; p <= estado.alto; p += paso, mm += pasoMm) {
      const y = Math.round(aPantallaY(p)) + .5;
      const largo = mm % (pasoMm * 2) === 0 ? 7 : 4;
      ctx.moveTo(REGLA - largo, y); ctx.lineTo(REGLA, y);
      if (mm % (pasoMm * 2) === 0) ctx.fillText(String(mm), 2, y + 2);
    }
    ctx.stroke();
  }

  function dibujarGrilla() {
    const paso = 5 * PUNTOS_POR_MM;       // una línea cada 5 mm
    ctx.save();
    ctx.strokeStyle = 'rgba(37, 99, 235, .16)';
    ctx.lineWidth = 1 / estado.escala;
    ctx.beginPath();
    for (let x = paso; x < estado.ancho; x += paso) {
      ctx.moveTo(x, 0); ctx.lineTo(x, estado.alto);
    }
    for (let y = paso; y < estado.alto; y += paso) {
      ctx.moveTo(0, y); ctx.lineTo(estado.ancho, y);
    }
    ctx.stroke();
    ctx.restore();
  }

  function dibujarTexto(el) {
    const texto = sustituir(el.texto);
    if (!texto.trim()) return;

    const anchoMax = el.ancho_bloque;
    const tamano = el.autoajustar ? tamanoQueEntra(texto, el, anchoMax) : el.tamano;
    const lineas = partir(texto, el, tamano, anchoMax).slice(0, el.renglones);

    ctx.font = fuenteCss(el, tamano);
    ctx.textBaseline = 'alphabetic';
    // letterSpacing es lo que da el aire de etiqueta textil. Donde no existe se
    // dibuja carácter por carácter: más lento, pero se ve igual.
    const soportaSpacing = 'letterSpacing' in ctx;
    if (soportaSpacing) ctx.letterSpacing = el.tracking + 'px';

    lineas.forEach((linea, i) => {
      const ancho = anchoTexto(linea, el, tamano);
      let x = el.x;
      if (el.alineacion === 'centro') x += (anchoMax - ancho) / 2;
      else if (el.alineacion === 'derecha') x += anchoMax - ancho;
      const y = el.y + tamano * ASCENDENTE + i * tamano * INTERLINEA;

      if (soportaSpacing || !el.tracking) {
        ctx.fillText(linea, x, y);
      } else {
        let cursor = x;
        for (const caracter of linea) {
          ctx.fillText(caracter, cursor, y);
          cursor += medidor.measureText(caracter).width + el.tracking;
        }
      }
    });
    if (soportaSpacing) ctx.letterSpacing = '0px';
  }

  /* Barras de la vista previa.
   *
   * No se codifica un Code 128 de verdad: la tabla del estándar son 107 entradas
   * y en el lienzo no aportan nada, porque lo que el usuario necesita decidir es
   * DÓNDE va el código y CUÁNTO ocupa, no qué barras lleva. Lo que sí es real es
   * la ESTRUCTURA —arranque de 11 módulos, 11 por carácter, checksum de 11 y
   * cierre de 13, que suman los 35 + 11n de la fórmula del servidor—, así que si
   * acá entra en la etiqueta, en el papel también. */
  const ARRANQUE = [2, 1, 1, 2, 1, 4];        // 11 módulos, el de Code 128 B
  const CIERRE = [2, 3, 3, 1, 1, 1, 2];       // 13 módulos
  const PATRONES = [
    [2, 1, 2, 2, 2, 2], [2, 2, 2, 1, 2, 2], [2, 2, 2, 2, 2, 1],
    [1, 2, 1, 3, 2, 2], [1, 2, 1, 2, 2, 3], [1, 3, 1, 2, 2, 2],
    [1, 2, 2, 3, 2, 1], [1, 2, 2, 1, 2, 3], [3, 2, 1, 2, 2, 1],
  ];

  function dibujarBarcode(el) {
    const dato = sustituir(el.texto).trim();
    if (!dato) return;
    if (el.simbologia === 'qr') { dibujarQr(el, dato); return; }

    const anchoTotal = modulosCode128(dato) * el.modulo;
    const x = el.centrar ? Math.max(0, Math.round((estado.ancho - anchoTotal) / 2)) : el.x;

    let cursor = x;
    const grupo = (patron) => patron.forEach((modulos, i) => {
      if (i % 2 === 0) ctx.fillRect(cursor, el.y, modulos * el.modulo, el.alto_barra);
      cursor += modulos * el.modulo;
    });

    grupo(ARRANQUE);
    let suma = 0;
    for (let i = 0; i < dato.length; i++) {
      suma += dato.charCodeAt(i) * (i + 1);
      grupo(PATRONES[dato.charCodeAt(i) % PATRONES.length]);
    }
    grupo(PATRONES[suma % PATRONES.length]);   // checksum
    grupo(CIERRE);

    if (el.mostrar_texto) {
      ctx.font = `${el.tamano_texto}px ${FAMILIAS.sans}`;
      ctx.textBaseline = 'alphabetic';
      medidor.font = ctx.font;
      const anchoLetras = medidor.measureText(dato).width;
      ctx.fillText(dato, x + (anchoTotal - anchoLetras) / 2,
                   el.y + el.alto_barra + el.tamano_texto);
    }
  }

  function dibujarQr(el, dato) {
    const lado = el.alto_barra;
    const celdas = 21;
    const paso = lado / celdas;
    let semilla = 0;
    for (let i = 0; i < dato.length; i++) semilla = (semilla * 31 + dato.charCodeAt(i)) >>> 0;

    for (let f = 0; f < celdas; f++) {
      for (let c = 0; c < celdas; c++) {
        semilla = (semilla * 1103515245 + 12345) >>> 0;
        const esOjo = (f < 7 && c < 7) || (f < 7 && c >= celdas - 7) || (f >= celdas - 7 && c < 7);
        const pintado = esOjo
          ? (f % 6 === 0 || c % 6 === 0 || (f > 1 && f < 5 && c > 1 && c < 5))
          : ((semilla >>> 16) & 1);
        if (pintado) ctx.fillRect(el.x + c * paso, el.y + f * paso, paso, paso);
      }
    }
  }

  function dibujarSimbolo(el) {
    const img = imagenSimbolo(el.clave, el.tam);
    if (img.complete && img.naturalWidth) {
      ctx.drawImage(img, el.x, el.y, el.tam, el.tam);
    } else {
      ctx.strokeRect(el.x, el.y, el.tam, el.tam);   // marco mientras carga
    }

    const leyenda = sustituir(el.leyenda).trim();
    if (!leyenda) return;
    ctx.font = `${el.tam_leyenda}px ${FAMILIAS.sans}`;
    ctx.textBaseline = 'alphabetic';
    medidor.font = ctx.font;
    if (el.leyenda_lado === 'derecha') {
      ctx.fillText(leyenda, el.x + el.tam + 6, el.y + el.tam / 2 + el.tam_leyenda * 0.35);
    } else {
      const ancho = medidor.measureText(leyenda).width;
      ctx.fillText(leyenda, el.x + (el.tam - ancho) / 2,
                   el.y + el.tam + 4 + el.tam_leyenda);
    }
  }

  function dibujarCaja(el) {
    if (el.relleno) { ctx.fillRect(el.x, el.y, el.ancho, el.alto); return; }
    // ZPL dibuja el borde hacia adentro; el canvas lo centra en el trazo. Se
    // compensa medio grosor, igual que en el renderer PDF.
    const g = el.grosor;
    ctx.lineWidth = g;
    const x = el.x + g / 2, y = el.y + g / 2;
    const w = Math.max(0.1, el.ancho - g), h = Math.max(0.1, el.alto - g);
    ctx.beginPath();
    if (el.redondeo > 0 && ctx.roundRect) ctx.roundRect(x, y, w, h, el.redondeo);
    else ctx.rect(x, y, w, h);
    ctx.stroke();
  }

  function dibujarLinea(el) {
    if (el.orientacion === 'vertical') {
      ctx.fillRect(el.x, el.y, el.grosor, el.largo);
    } else {
      ctx.fillRect(el.x, el.y, el.largo, el.grosor);
    }
  }

  // ── Adornos ────────────────────────────────────────────────────────────────

  function manijas(c) {
    const x0 = aPantallaX(c.x), y0 = aPantallaY(c.y);
    const x1 = aPantallaX(c.x + c.ancho), y1 = aPantallaY(c.y + c.alto);
    const xm = (x0 + x1) / 2, ym = (y0 + y1) / 2;
    return {
      nw: [x0, y0], n: [xm, y0], ne: [x1, y0], e: [x1, ym],
      se: [x1, y1], s: [xm, y1], sw: [x0, y1], w: [x0, ym],
    };
  }

  function manijasPermitidas(el) {
    if (esCuadrado(el)) return ['nw', 'ne', 'se', 'sw'];
    if (el.tipo === 'linea') {
      return el.orientacion === 'vertical' ? ['n', 's'] : ['w', 'e'];
    }
    return Object.keys(manijas(cajaTransformacion(el)));
  }

  function dibujarSeleccion(el) {
    if (!el.visible) return;
    const c = cajaTransformacion(el);
    const x = aPantallaX(c.x), y = aPantallaY(c.y);
    const w = c.ancho * estado.escala, h = c.alto * estado.escala;

    ctx.save();
    ctx.strokeStyle = '#2563eb';
    ctx.lineWidth = 1;
    ctx.setLineDash(el.bloqueado ? [3, 3] : []);
    ctx.strokeRect(Math.round(x) + .5, Math.round(y) + .5, Math.round(w), Math.round(h));
    ctx.setLineDash([]);

    if (!el.bloqueado) {
      const puntos = manijas(c);
      const permitidas = manijasPermitidas(el);
      ctx.fillStyle = '#fff';
      for (const nombre of permitidas) {
        const [px, py] = puntos[nombre];
        ctx.fillRect(px - MANIJA / 2, py - MANIJA / 2, MANIJA, MANIJA);
        ctx.strokeRect(Math.round(px - MANIJA / 2) + .5, Math.round(py - MANIJA / 2) + .5,
                       MANIJA - 1, MANIJA - 1);
      }
    }
    ctx.restore();
  }

  function dibujarGuias() {
    if (!guiasVisibles.length) return;
    ctx.save();
    ctx.strokeStyle = '#e5484d';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    for (const guia of guiasVisibles) {
      if (guia.eje === 'x') {
        const x = Math.round(aPantallaX(guia.valor)) + .5;
        ctx.moveTo(x, REGLA); ctx.lineTo(x, REGLA + estado.alto * estado.escala);
      } else {
        const y = Math.round(aPantallaY(guia.valor)) + .5;
        ctx.moveTo(REGLA, y); ctx.lineTo(REGLA + estado.ancho * estado.escala, y);
      }
    }
    ctx.stroke();
    ctx.restore();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Enganche a guías
  //
  // Los candidatos son los bordes y el centro de la etiqueta más los bordes y
  // centros de los demás elementos. Es lo que hace que alinear a ojo dé un
  // resultado exacto, que en una etiqueta de 50 mm se nota mucho.
  // ═══════════════════════════════════════════════════════════════════════════

  function candidatos(indiceExcluido, paraRedimension = false) {
    const x = [0, estado.ancho / 2, estado.ancho];
    const y = [0, estado.alto / 2, estado.alto];
    estado.elementos.forEach((el, i) => {
      if (i === indiceExcluido || !el.visible) return;
      const c = caja(el);
      x.push(c.x, c.x + c.ancho / 2, c.x + c.ancho);
      y.push(c.y, c.y + c.alto / 2, c.y + c.alto);
      if (paraRedimension) {
        const t = cajaTransformacion(el);
        x.push(t.x, t.x + t.ancho / 2, t.x + t.ancho);
        y.push(t.y, t.y + t.alto / 2, t.y + t.alto);
      }
    });
    return { x, y };
  }

  /* Devuelve el desplazamiento que hay que sumar para enganchar, y anota las
   * guías que se dibujan mientras tanto. */
  function enganchar(c, indice) {
    guiasVisibles = [];
    if (!estado.iman) return { dx: 0, dy: 0 };

    const tolerancia = IMAN / estado.escala;
    const listas = candidatos(indice);
    const resultado = { dx: 0, dy: 0 };

    const buscar = (valores, bordes, eje) => {
      let mejor = null;
      for (const borde of bordes) {
        for (const valor of valores) {
          const distancia = Math.abs(valor - borde);
          if (distancia <= tolerancia && (!mejor || distancia < mejor.distancia)) {
            mejor = { distancia, ajuste: valor - borde, valor };
          }
        }
      }
      if (mejor) {
        guiasVisibles.push({ eje, valor: mejor.valor });
        return mejor.ajuste;
      }
      return 0;
    };

    resultado.dx = buscar(listas.x, [c.x, c.x + c.ancho / 2, c.x + c.ancho], 'x');
    resultado.dy = buscar(listas.y, [c.y, c.y + c.alto / 2, c.y + c.alto], 'y');
    return resultado;
  }

  function engancharRedimension(punto, manija, indice) {
    guiasVisibles = [];
    const resultado = { punto: { ...punto }, referencias: [] };
    if (!estado.iman) return resultado;

    const tolerancia = IMAN / estado.escala;
    const listas = candidatos(indice, true);
    const buscar = (valores, valor, eje) => {
      let mejor = null;
      for (const candidato of valores) {
        const distancia = Math.abs(candidato - valor);
        if (distancia <= tolerancia && (!mejor || distancia < mejor.distancia)) {
          mejor = { distancia, valor: candidato, eje };
        }
      }
      if (mejor) resultado.referencias.push(mejor);
      return mejor ? mejor.valor : valor;
    };

    if (manija.includes('w') || manija.includes('e')) {
      resultado.punto.x = buscar(listas.x, punto.x, 'x');
    }
    if (manija.includes('n') || manija.includes('s')) {
      resultado.punto.y = buscar(listas.y, punto.y, 'y');
    }
    return resultado;
  }

  function confirmarGuiasRedimension(c, manija, referencias) {
    const bordes = {
      x: manija.includes('w') ? c.x : c.x + c.ancho,
      y: manija.includes('n') ? c.y : c.y + c.alto,
    };
    const tolerancia = 1 / estado.escala;
    guiasVisibles = referencias
      .filter((ref) => Math.abs(bordes[ref.eje] - ref.valor) <= tolerancia)
      .map((ref) => ({ eje: ref.eje, valor: ref.valor }));
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Interacción con el lienzo
  // ═══════════════════════════════════════════════════════════════════════════

  const CURSORES = {
    nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize',
    n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
  };

  let gesto = null;      // { modo: 'mover'|'redimensionar', ... }

  function puntoDesdeEvento(evento) {
    const rect = lienzo.getBoundingClientRect();
    return {
      x: (evento.clientX - rect.left - REGLA) / estado.escala,
      y: (evento.clientY - rect.top - REGLA) / estado.escala,
      px: evento.clientX - rect.left,
      py: evento.clientY - rect.top,
    };
  }

  function manijaEn(punto) {
    if (estado.seleccion < 0) return null;
    const el = estado.elementos[estado.seleccion];
    if (el.bloqueado || !el.visible) return null;
    const puntos = manijas(cajaTransformacion(el));
    const permitidas = manijasPermitidas(el);
    for (const nombre of permitidas) {
      const [px, py] = puntos[nombre];
      if (Math.abs(punto.px - px) <= MANIJA && Math.abs(punto.py - py) <= MANIJA) return nombre;
    }
    return null;
  }

  function elementosEn(punto) {
    const encontrados = [];
    // De arriba hacia abajo: el último dibujado aparece primero.
    for (let i = estado.elementos.length - 1; i >= 0; i--) {
      const el = estado.elementos[i];
      if (!el.visible || el.bloqueado) continue;
      const c = caja(el);
      if (punto.x >= c.x - 2 && punto.x <= c.x + c.ancho + 2
          && punto.y >= c.y - 2 && punto.y <= c.y + c.alto + 2) encontrados.push(i);
    }
    return encontrados;
  }

  function elementoEn(punto) {
    return elementosEn(punto)[0] ?? -1;
  }

  lienzo.addEventListener('pointerdown', (evento) => {
    const punto = puntoDesdeEvento(evento);

    // Con una herramienta de creación activa, el clic coloca el elemento.
    if (estado.herramienta !== 'seleccion') {
      crearElemento(estado.herramienta, punto);
      elegirHerramienta('seleccion');
      return;
    }

    const seleccionarDebajo = evento.ctrlKey || evento.metaKey;
    const manija = seleccionarDebajo ? null : manijaEn(punto);
    if (manija) {
      const el = estado.elementos[estado.seleccion];
      const inicial = cajaTransformacion(el);
      const elementoInicial = clonar(el);
      // Al redimensionar manualmente un código centrado, su X visual pasa a ser
      // explícita. Si se conservara `centrar`, cada cambio de ancho recalcularía
      // la X y el código saltaría hacia la izquierda debajo del puntero.
      if (elementoInicial.tipo === 'barcode' && elementoInicial.centrar) {
        elementoInicial.x = inicial.x;
        elementoInicial.centrar = false;
      }
      gesto = { modo: 'redimensionar', manija, inicial, elementoInicial };
      lienzo.setPointerCapture(evento.pointerId);
      return;
    }

    const superpuestos = elementosEn(punto);
    let indice = superpuestos[0] ?? -1;
    if (seleccionarDebajo && superpuestos.length > 1) {
      const actual = superpuestos.indexOf(estado.seleccion);
      indice = actual >= 0
        ? superpuestos[(actual + 1) % superpuestos.length]
        : superpuestos[0];
    }
    seleccionar(indice, false);
    if (indice < 0) return;

    const el = estado.elementos[indice];
    const c = caja(el);
    if (seleccionarDebajo) lienzo.style.cursor = 'move';
    gesto = { modo: 'mover', dx: punto.x - c.x, dy: punto.y - c.y, ancho: c.ancho, alto: c.alto };
    lienzo.setPointerCapture(evento.pointerId);
  });

  lienzo.addEventListener('pointermove', (evento) => {
    const punto = puntoDesdeEvento(evento);
    mostrarPosicion(punto);

    if (!gesto) {
      // Cursor según lo que haya debajo: es la pista de que algo se puede agarrar.
      if (estado.herramienta !== 'seleccion') lienzo.style.cursor = 'crosshair';
      else {
        const manija = (evento.ctrlKey || evento.metaKey) ? null : manijaEn(punto);
        lienzo.style.cursor = manija ? CURSORES[manija]
          : (elementoEn(punto) >= 0 ? 'move' : 'default');
      }
      return;
    }

    const el = estado.elementos[estado.seleccion];
    if (gesto.modo === 'mover') {
      const propuesta = {
        x: punto.x - gesto.dx, y: punto.y - gesto.dy,
        ancho: gesto.ancho, alto: gesto.alto,
      };
      // Alt permite mover con precisión sin que el imán capture el objeto.
      const ajuste = evento.altKey ? { dx: 0, dy: 0 } : enganchar(propuesta, estado.seleccion);
      const maxX = Math.max(0, estado.ancho - gesto.ancho);
      const maxY = Math.max(0, estado.alto - gesto.alto);
      el.x = Math.max(0, Math.min(maxX, Math.round(propuesta.x + ajuste.dx)));
      el.y = Math.max(0, Math.min(maxY, Math.round(propuesta.y + ajuste.dy)));
      // Un código centrado ignora su X. Al moverlo a mano pasa a posición libre.
      if (el.tipo === 'barcode' && el.centrar) el.centrar = false;
      estado.elementos[estado.seleccion] = normalizar(el);
    } else {
      // Cada frame parte del elemento al inicio del gesto. Aplicar el factor
      // sobre el resultado del frame anterior hacía que los textos crecieran o
      // se achicaran de forma acumulativa y terminaran dando saltos.
      const base = clonar(gesto.elementoInicial);
      const enganche = evento.altKey
        ? { punto, referencias: [] }
        : engancharRedimension(punto, gesto.manija, estado.seleccion);
      const ejePreferido = enganche.referencias.length
        ? enganche.referencias.reduce((mejor, ref) => ref.distancia < mejor.distancia ? ref : mejor).eje
        : null;
      const nueva = redimensionarCaja(gesto.inicial, gesto.manija, enganche.punto,
                                      esCuadrado(base) || evento.shiftKey, ejePreferido,
                                      base.tipo === 'linea' ? 1 : 4);
      aplicarCaja(base, nueva, gesto.inicial);
      estado.elementos[estado.seleccion] = traerAlLienzo(normalizar(base));
      const cajaFinal = cajaTransformacion(estado.elementos[estado.seleccion]);
      confirmarGuiasRedimension(cajaFinal, gesto.manija, enganche.referencias);
      mostrarTamano(cajaFinal);
    }

    dibujar();
    actualizarControlesPropiedades(estado.elementos[estado.seleccion]);
  });

  function redimensionarCaja(inicial, manija, punto, proporcional, ejePreferido = null,
                              minimo = 4) {
    let { x, y, ancho, alto } = inicial;
    const derecha = x + ancho, abajo = y + alto;

    if (manija.includes('w')) { x = Math.min(punto.x, derecha - minimo); ancho = derecha - x; }
    if (manija.includes('e')) { ancho = Math.max(minimo, punto.x - x); }
    if (manija.includes('n')) { y = Math.min(punto.y, abajo - minimo); alto = abajo - y; }
    if (manija.includes('s')) { alto = Math.max(minimo, punto.y - y); }

    if (proporcional && inicial.ancho > 0 && inicial.alto > 0) {
      const cambiaX = manija.includes('w') || manija.includes('e');
      const cambiaY = manija.includes('n') || manija.includes('s');
      const escalaX = ancho / inicial.ancho;
      const escalaY = alto / inicial.alto;
      let escala;

      if (cambiaX && cambiaY && ejePreferido) {
        escala = ejePreferido === 'x' ? escalaX : escalaY;
      } else if (cambiaX && cambiaY) {
        escala = Math.abs(escalaX - 1) >= Math.abs(escalaY - 1) ? escalaX : escalaY;
      } else {
        escala = cambiaX ? escalaX : escalaY;
      }

      const centroX = inicial.x + inicial.ancho / 2;
      const centroY = inicial.y + inicial.alto / 2;
      const maxAncho = manija.includes('w') ? derecha
        : (manija.includes('e') ? estado.ancho - inicial.x
          : 2 * Math.min(centroX, estado.ancho - centroX));
      const maxAlto = manija.includes('n') ? abajo
        : (manija.includes('s') ? estado.alto - inicial.y
          : 2 * Math.min(centroY, estado.alto - centroY));
      const escalaMinima = Math.max(minimo / inicial.ancho, minimo / inicial.alto);
      const escalaMaxima = Math.min(maxAncho / inicial.ancho, maxAlto / inicial.alto);
      escala = Math.max(escalaMinima, Math.min(escalaMaxima, escala));

      ancho = inicial.ancho * escala;
      alto = inicial.alto * escala;
      x = manija.includes('w') ? derecha - ancho
        : (manija.includes('e') ? inicial.x : centroX - ancho / 2);
      y = manija.includes('n') ? abajo - alto
        : (manija.includes('s') ? inicial.y : centroY - alto / 2);
    }
    return limitarCajaAlLienzo({ x, y, ancho, alto }, minimo);
  }

  function limitarCajaAlLienzo(c, minimo = 4) {
    let izquierda = Math.max(0, c.x);
    let arriba = Math.max(0, c.y);
    let derecha = Math.min(estado.ancho, c.x + c.ancho);
    let abajo = Math.min(estado.alto, c.y + c.alto);

    if (derecha - izquierda < minimo) {
      izquierda = Math.max(0, Math.min(izquierda, estado.ancho - minimo));
      derecha = Math.min(estado.ancho, izquierda + minimo);
    }
    if (abajo - arriba < minimo) {
      arriba = Math.max(0, Math.min(arriba, estado.alto - minimo));
      abajo = Math.min(estado.alto, arriba + minimo);
    }
    return {
      x: izquierda, y: arriba,
      ancho: derecha - izquierda, alto: abajo - arriba,
    };
  }

  function traerAlLienzo(el) {
    const c = caja(el);
    let dx = 0, dy = 0;
    if (c.x < 0) dx = -c.x;
    else if (c.x + c.ancho > estado.ancho) dx = estado.ancho - c.x - c.ancho;
    if (c.y < 0) dy = -c.y;
    else if (c.y + c.alto > estado.alto) dy = estado.alto - c.y - c.alto;
    const ajustar = (valor, delta) => delta < 0
      ? Math.floor(valor + delta)
      : (delta > 0 ? Math.ceil(valor + delta) : Math.round(valor));
    el.x = Math.max(0, ajustar(el.x, dx));
    el.y = Math.max(0, ajustar(el.y, dy));
    return el;
  }

  function terminarGesto() {
    if (!gesto) return;
    gesto = null;
    guiasVisibles = [];
    document.getElementById('et-posicion-estado').textContent = '';
    registrar();
    dibujar();
    pintarCapas();
  }
  lienzo.addEventListener('pointerup', terminarGesto);
  lienzo.addEventListener('pointercancel', terminarGesto);
  lienzo.addEventListener('pointerleave', () => {
    document.getElementById('et-posicion-estado').textContent = '';
  });

  function mostrarPosicion(punto) {
    if (punto.x < 0 || punto.y < 0 || punto.x > estado.ancho || punto.y > estado.alto) {
      document.getElementById('et-posicion-estado').textContent = '';
      return;
    }
    document.getElementById('et-posicion-estado').textContent =
      `x ${(punto.x / PUNTOS_POR_MM).toFixed(1)} · y ${(punto.y / PUNTOS_POR_MM).toFixed(1)} mm`;
  }

  function mostrarTamano(c) {
    document.getElementById('et-posicion-estado').textContent =
      `${Math.round(c.ancho)} × ${Math.round(c.alto)} pt · `
      + `${(c.ancho / PUNTOS_POR_MM).toFixed(1)} × ${(c.alto / PUNTOS_POR_MM).toFixed(1)} mm`;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Herramientas y alta de elementos
  // ═══════════════════════════════════════════════════════════════════════════

  const NUEVOS = {
    texto: (p) => ({ tipo: 'texto', x: p.x, y: p.y, texto: 'Texto nuevo', tamano: 24,
                     ancho_bloque: Math.max(40, estado.ancho - p.x - 20), alineacion: 'izquierda' }),
    barcode: (p) => ({ tipo: 'barcode', x: p.x, y: p.y, texto: '{codigo_barra}',
                       simbologia: 'code128', modulo: 2, alto_barra: 60 }),
    qr: (p) => ({ tipo: 'barcode', x: p.x, y: p.y, texto: '{codigo_barra}', nombre: 'Código QR',
                  simbologia: 'qr', modulo: 3, alto_barra: 72, mostrar_texto: false }),
    simbolo: (p) => ({ tipo: 'simbolo', x: p.x, y: p.y,
                       tam: Math.min(40, estado.ancho, estado.alto), clave: primerSimbolo() }),
    linea: (p) => ({ tipo: 'linea', x: p.x, y: p.y, nombre: 'Línea',
                     orientacion: 'horizontal',
                     largo: Math.max(40, Math.round(estado.ancho / 3)), grosor: 2 }),
    rectangulo: (p) => ({ tipo: 'caja', x: p.x, y: p.y, nombre: 'Rectángulo',
                          ancho: Math.max(50, Math.round(estado.ancho / 3)),
                          alto: Math.max(30, Math.round(estado.alto / 4)), grosor: 2 }),
    bloque: (p) => ({ tipo: 'caja', x: p.x, y: p.y, nombre: 'Bloque sólido',
                      ancho: Math.max(50, Math.round(estado.ancho / 3)),
                      alto: Math.max(20, Math.round(estado.alto / 6)), relleno: true }),
  };

  function ajustarNuevoAlLienzo(el) {
    if (el.tipo === 'barcode' && el.simbologia === 'qr') {
      const lado = Math.min(el.alto_barra, estado.ancho, estado.alto);
      if (lado < QR_TAM_MIN) return null;
      el.alto_barra = lado;
    } else if (el.tipo === 'barcode') {
      const dato = sustituir(el.texto).trim() || ' ';
      const moduloMaximo = Math.floor(estado.ancho / modulosCode128(dato));
      if (moduloMaximo < 1) return null;
      el.modulo = Math.min(el.modulo, moduloMaximo);
      const extra = el.mostrar_texto ? el.tamano_texto + 2 : 0;
      if (estado.alto - extra < 10) return null;
      el.alto_barra = Math.min(el.alto_barra, estado.alto - extra);
    } else if (el.tipo === 'simbolo') {
      if (Math.min(estado.ancho, estado.alto) < 16) return null;
      el.tam = Math.min(el.tam, estado.ancho, estado.alto);
    } else if (el.tipo === 'linea') {
      const disponible = el.orientacion === 'vertical' ? estado.alto : estado.ancho;
      el.largo = Math.min(el.largo, disponible);
      el.grosor = Math.min(el.grosor,
        el.orientacion === 'vertical' ? estado.ancho : estado.alto);
    } else if (el.tipo === 'caja') {
      el.ancho = Math.min(el.ancho, estado.ancho);
      el.alto = Math.min(el.alto, estado.alto);
    } else if (el.tipo === 'texto') {
      el.ancho_bloque = Math.min(el.ancho_bloque, estado.ancho);
    }
    return traerAlLienzo(normalizar(el));
  }

  function crearElemento(tipo, punto) {
    const el = ajustarNuevoAlLienzo(normalizar(NUEVOS[tipo]({
      x: Math.max(0, Math.round(punto.x)), y: Math.max(0, Math.round(punto.y)),
    })));
    if (!el) {
      avisar('El papel es demasiado pequeño para esta herramienta.', 'warning');
      return;
    }
    estado.elementos.push(el);
    registrar();
    seleccionar(estado.elementos.length - 1);
  }

  function elegirHerramienta(tipo) {
    estado.herramienta = tipo;
    document.querySelectorAll('[data-herramienta]').forEach((boton) =>
      boton.classList.toggle('activa', boton.dataset.herramienta === tipo));
    lienzo.style.cursor = tipo === 'seleccion' ? 'default' : 'crosshair';
  }

  document.querySelectorAll('[data-herramienta]').forEach((boton) =>
    boton.addEventListener('click', () => elegirHerramienta(boton.dataset.herramienta)));

  // ═══════════════════════════════════════════════════════════════════════════
  // Operaciones sobre el elemento seleccionado
  // ═══════════════════════════════════════════════════════════════════════════

  function seleccionado() {
    return estado.seleccion >= 0 ? estado.elementos[estado.seleccion] : null;
  }

  /* `reconstruirCapas` en false actualiza sólo la marca de capa activa en vez de
   * rehacer la lista. Es lo que permite renombrar con doble clic desde el panel:
   * si cada clic reconstruyera las filas, el segundo caería sobre un nodo nuevo
   * y el navegador nunca llegaría a disparar el dblclick. */
  function seleccionar(indice, reconstruirCapas = true) {
    estado.seleccion = indice;
    dibujar();
    if (reconstruirCapas) pintarCapas(); else marcarCapaActiva();
    pintarPropiedades();
    refrescarBotones();
  }

  function marcarCapaActiva() {
    document.querySelectorAll('#et-capas .et-capa').forEach((fila) =>
      fila.classList.toggle('activa', +fila.dataset.indice === estado.seleccion));
  }

  function repintarTodo() {
    dibujar();
    pintarCapas();
    pintarPropiedades();
    refrescarBotones();
  }

  function duplicar() {
    const el = seleccionado();
    if (!el) return;
    const copia = normalizar(Object.assign(JSON.parse(JSON.stringify(el)), {
      x: el.x + 8, y: el.y + 8, centrar: false,
    }));
    estado.elementos.splice(estado.seleccion + 1, 0, copia);
    registrar();
    seleccionar(estado.seleccion + 1);
  }

  function eliminar() {
    if (estado.seleccion < 0) return;
    estado.elementos.splice(estado.seleccion, 1);
    registrar();
    seleccionar(-1);
  }

  function reordenar(accion) {
    const i = estado.seleccion;
    if (i < 0) return;
    const [el] = estado.elementos.splice(i, 1);
    const destino = {
      frente: estado.elementos.length,
      fondo: 0,
      subir: Math.min(estado.elementos.length, i + 1),
      bajar: Math.max(0, i - 1),
    }[accion];
    estado.elementos.splice(destino, 0, el);
    registrar();
    seleccionar(destino);
  }

  function alinear(donde) {
    const el = seleccionado();
    if (!el || el.bloqueado) return;
    const c = caja(el);
    const posiciones = {
      izquierda: { x: 0 },
      'centro-h': { x: Math.round((estado.ancho - c.ancho) / 2) },
      derecha:    { x: Math.max(0, estado.ancho - c.ancho) },
      arriba:     { y: 0 },
      'centro-v': { y: Math.round((estado.alto - c.alto) / 2) },
      abajo:      { y: Math.max(0, estado.alto - c.alto) },
    }[donde];

    // Un código centrado por bandera no se puede alinear a mano: son dos
    // mecanismos peleando por la misma x.
    if (el.tipo === 'barcode' && el.centrar && 'x' in posiciones) el.centrar = false;
    Object.assign(el, posiciones);
    estado.elementos[estado.seleccion] = normalizar(el);
    registrar();
    repintarTodo();
  }

  document.querySelectorAll('[data-objeto]').forEach((boton) =>
    boton.addEventListener('click', () =>
      (boton.dataset.objeto === 'duplicar' ? duplicar : eliminar)()));
  document.querySelectorAll('[data-orden]').forEach((boton) =>
    boton.addEventListener('click', () => reordenar(boton.dataset.orden)));
  document.querySelectorAll('[data-alinear]').forEach((boton) =>
    boton.addEventListener('click', () => alinear(boton.dataset.alinear)));

  function refrescarBotones() {
    const hay = estado.seleccion >= 0;
    document.querySelectorAll('[data-objeto],[data-orden],[data-alinear]')
      .forEach((boton) => { boton.disabled = !hay; });
    document.getElementById('et-conteo-capas').textContent =
      estado.elementos.length + (estado.elementos.length === 1 ? ' capa' : ' capas');
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Teclado
  // ═══════════════════════════════════════════════════════════════════════════

  let portapapeles = null;

  document.addEventListener('keydown', (evento) => {
    if (document.querySelector('.modal.show')) return;
    const foco = document.activeElement;
    const escribiendo = foco && (['INPUT', 'TEXTAREA', 'SELECT'].includes(foco.tagName)
      || foco.isContentEditable);

    if ((evento.ctrlKey || evento.metaKey) && !escribiendo) {
      const atajos = {
        z: () => restaurar(evento.shiftKey ? 1 : -1),
        y: () => restaurar(1),
        d: duplicar,
        c: () => { const el = seleccionado(); if (el) portapapeles = JSON.stringify(el); },
        v: () => {
          if (!portapapeles) return;
          const copia = normalizar(JSON.parse(portapapeles));
          copia.x += 8; copia.y += 8; copia.centrar = false;
          estado.elementos.push(copia);
          registrar();
          seleccionar(estado.elementos.length - 1);
        },
      };
      const accion = atajos[evento.key.toLowerCase()];
      if (accion) { evento.preventDefault(); accion(); }
      return;
    }
    if (escribiendo) return;

    // Herramientas y vista, con la inicial como en cualquier editor.
    const teclas = {
      v: () => elegirHerramienta('seleccion'),
      t: () => elegirHerramienta('texto'),
      b: () => elegirHerramienta('barcode'),
      q: () => elegirHerramienta('qr'),
      s: () => elegirHerramienta('simbolo'),
      l: () => elegirHerramienta('linea'),
      r: () => elegirHerramienta('rectangulo'),
      f: () => elegirHerramienta('bloque'),
      g: () => alternarGrilla(),
      m: () => alternarIman(),
      '0': () => ajustarZoom(),
      '+': () => zoom(0.5), '=': () => zoom(0.5), '-': () => zoom(-0.5),
      Escape: () => seleccionar(-1),
      Delete: eliminar,
      Backspace: eliminar,
    };
    if (teclas[evento.key]) { evento.preventDefault(); teclas[evento.key](); return; }

    const el = seleccionado();
    if (!el || el.bloqueado) return;
    const paso = evento.shiftKey ? 10 : 1;
    const movimientos = {
      ArrowLeft: [-paso, 0], ArrowRight: [paso, 0],
      ArrowUp: [0, -paso], ArrowDown: [0, paso],
    };
    if (!movimientos[evento.key]) return;

    evento.preventDefault();
    if (el.tipo === 'barcode' && el.centrar && movimientos[evento.key][0]) el.centrar = false;
    el.x = Math.max(0, el.x + movimientos[evento.key][0]);
    el.y = Math.max(0, el.y + movimientos[evento.key][1]);
    registrar();
    dibujar();
    pintarPropiedades();
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // Panel de capas
  // ═══════════════════════════════════════════════════════════════════════════

  const NOMBRES = { texto: 'Texto', barcode: 'Código', simbolo: 'Símbolo', linea: 'Línea', caja: 'Caja' };
  const ICONOS = { texto: 'type', barcode: 'barcode', simbolo: 'shirt', linea: 'minus', caja: 'square' };

  function nombreTipo(el) {
    if (el.tipo === 'barcode' && el.simbologia === 'qr') return 'Código QR';
    if (el.tipo !== 'caja') return NOMBRES[el.tipo];
    if (el.relleno) return 'Bloque sólido';
    if (Math.min(el.ancho, el.alto) <= Math.max(4, el.grosor * 2)) return 'Línea';
    return 'Rectángulo';
  }

  function iconoTipo(el) {
    if (el.tipo === 'barcode' && el.simbologia === 'qr') return 'qr-code';
    if (el.tipo === 'caja' && el.relleno) return 'rectangle-horizontal';
    if (el.tipo === 'caja' && nombreTipo(el) === 'Línea') return 'minus';
    return ICONOS[el.tipo];
  }

  function nombreSimbolo(clave) {
    for (const lista of Object.values(CATALOGO)) {
      const encontrado = lista.find((s) => s.clave === clave);
      if (encontrado) return encontrado.nombre;
    }
    return clave;
  }

  function nombreCapa(el) {
    if (el.nombre) return el.nombre;
    if (el.tipo === 'texto') return el.texto || '(texto vacío)';
    if (el.tipo === 'barcode') return el.texto;
    if (el.tipo === 'simbolo') return nombreSimbolo(el.clave);
    if (el.tipo === 'linea') return `Línea ${el.largo} pt`;
    return el.relleno ? `Barra ${el.ancho}×${el.alto}` : `Marco ${el.ancho}×${el.alto}`;
  }

  function escaparHtml(texto) {
    const d = document.createElement('div');
    d.textContent = String(texto ?? '');
    return d.innerHTML;
  }

  let capaArrastrada = null;

  function pintarCapas() {
    const panel = document.getElementById('et-capas');
    panel.innerHTML = '';
    if (!estado.elementos.length) {
      panel.innerHTML = '<div class="text-muted small p-2">Todavía no hay capas. '
        + 'Elegí una herramienta de arriba y hacé clic en la etiqueta.</div>';
      return;
    }

    // Se listan al revés: lo que está arriba en el dibujo, arriba en la lista.
    for (let i = estado.elementos.length - 1; i >= 0; i--) {
      const el = estado.elementos[i];
      const fila = document.createElement('div');
      fila.className = 'et-capa'
        + (i === estado.seleccion ? ' activa' : '')
        + (el.visible ? '' : ' oculta');
      fila.draggable = true;
      fila.dataset.indice = i;
      fila.innerHTML = `
        <button class="et-mini" data-accion="visible" title="Mostrar u ocultar">
          <i data-lucide="${el.visible ? 'eye' : 'eye-off'}"></i></button>
        <button class="et-mini" data-accion="bloquear" title="Bloquear o desbloquear">
          <i data-lucide="${el.bloqueado ? 'lock' : 'lock-open'}"></i></button>
        <i data-lucide="${iconoTipo(el)}" style="width:.85rem;height:.85rem;flex-shrink:0"></i>
        <span class="et-capa-nombre" title="${escaparHtml(nombreTipo(el))} — doble clic para renombrar"
              >${escaparHtml(nombreCapa(el))}</span>`;

      fila.addEventListener('click', (evento) => {
        const boton = evento.target.closest('[data-accion]');
        if (!boton) { seleccionar(i, false); return; }
        if (boton.dataset.accion === 'visible') {
          el.visible = !el.visible;
          if (!el.visible && estado.seleccion === i) estado.seleccion = -1;
        }
        else {
          el.bloqueado = !el.bloqueado;
          if (el.bloqueado && estado.seleccion === i) estado.seleccion = -1;
        }
        registrar();
        repintarTodo();
      });

      const etiqueta = fila.querySelector('.et-capa-nombre');
      etiqueta.addEventListener('dblclick', () => {
        etiqueta.contentEditable = 'true';
        etiqueta.focus();
        document.execCommand?.('selectAll', false, null);
      });
      etiqueta.addEventListener('blur', () => {
        etiqueta.contentEditable = 'false';
        const nuevo = etiqueta.textContent.trim().slice(0, 60);
        if (nuevo !== nombreCapa(el)) { el.nombre = nuevo; registrar(); }
        pintarCapas();
      });
      etiqueta.addEventListener('keydown', (evento) => {
        if (evento.key === 'Enter') { evento.preventDefault(); etiqueta.blur(); }
        if (evento.key === 'Escape') { etiqueta.textContent = nombreCapa(el); etiqueta.blur(); }
      });

      // Reordenar arrastrando, que es como se espera que funcione una lista de
      // capas. Los botones de subir y bajar de la barra hacen lo mismo.
      fila.addEventListener('dragstart', () => {
        capaArrastrada = i;
        fila.classList.add('arrastrando');
      });
      fila.addEventListener('dragend', () => {
        capaArrastrada = null;
        pintarCapas();
      });
      fila.addEventListener('dragover', (evento) => {
        evento.preventDefault();
        fila.classList.add('destino');
      });
      fila.addEventListener('dragleave', () => fila.classList.remove('destino'));
      fila.addEventListener('drop', (evento) => {
        evento.preventDefault();
        fila.classList.remove('destino');
        if (capaArrastrada === null || capaArrastrada === i) return;
        const [movido] = estado.elementos.splice(capaArrastrada, 1);
        estado.elementos.splice(i, 0, movido);
        registrar();
        seleccionar(i);
      });

      panel.appendChild(fila);
    }
    if (window.lucide) lucide.createIcons();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Panel de propiedades
  // ═══════════════════════════════════════════════════════════════════════════

  const seccion = (titulo) => `<div class="et-seccion">${titulo}</div>`;

  function campo(etiqueta, html, ayuda) {
    return `<div class="et-prop"><label>${etiqueta}</label>${html}`
      + (ayuda ? `<div class="form-hint">${ayuda}</div>` : '') + '</div>';
  }
  const numero = (clave, valor, min, max, paso) =>
    `<input type="number" class="form-control form-control-sm" id="prop-${clave}"
      data-prop="${clave}" value="${valor}" min="${min}" max="${max}" step="${paso || 1}">`;
  const texto = (clave, valor) =>
    `<input type="text" class="form-control form-control-sm" data-prop="${clave}"
      value="${escaparHtml(valor)}">`;
  const opciones = (clave, valor, lista) =>
    `<select class="form-select form-select-sm" data-prop="${clave}">`
    + lista.map(([v, t]) => `<option value="${v}" ${v === valor ? 'selected' : ''}>${t}</option>`).join('')
    + '</select>';
  const casilla = (clave, valor, etiqueta) =>
    `<label class="form-check"><input class="form-check-input" type="checkbox"
      data-prop="${clave}" ${valor ? 'checked' : ''}>
      <span class="form-check-label small">${etiqueta}</span></label>`;

  function pintarPropiedades() {
    const panel = document.getElementById('et-propiedades');
    const el = seleccionado();

    if (!el) {
      panel.innerHTML = `${seccion('Etiqueta')}
        <div class="text-muted small">
          ${estado.elementos.length} capa${estado.elementos.length === 1 ? '' : 's'} ·
          ${(estado.ancho * 25.4 / 203).toFixed(1)} × ${(estado.alto * 25.4 / 203).toFixed(1)} mm
        </div>
        <div class="text-muted small mt-3">
          Elegí una capa para editarla, o una herramienta de la barra para agregar algo.
        </div>`;
      return;
    }

    let html = seccion(nombreTipo(el));
    html += campo('Nombre de la capa', texto('nombre', el.nombre), 'Opcional.');
    html += `<div class="row g-2">
      <div class="col-6">${campo('X', numero('x', el.x, 0, 4000))}</div>
      <div class="col-6">${campo('Y', numero('y', el.y, 0, 4000))}</div></div>`;

    if (el.tipo === 'texto') {
      const lista = Object.entries(CAMPOS)
        .map(([clave, nombre]) => `<option value="{${clave}}">${nombre}</option>`).join('');
      html += seccion('Contenido');
      html += campo('Texto',
        `<textarea class="form-control form-control-sm" rows="2" data-prop="texto">${escaparHtml(el.texto)}</textarea>`);
      html += campo('Insertar campo',
        `<select class="form-select form-select-sm" id="prop-insertar">
           <option value="">Elegir…</option>${lista}</select>`,
        'Se reemplaza por el dato real al imprimir.');
      html += seccion('Tipografía');
      html += campo('Fuente', opciones('fuente', el.fuente,
        [['sans', 'Sans (Helvetica)'], ['serif', 'Serif (Times)'], ['mono', 'Monoespaciada']]),
        'La fuente y el espaciado sólo se aplican en el PDF: la impresora térmica tiene una sola tipografía.');
      html += `<div class="row g-2">
        <div class="col-6">${campo('Cuerpo', numero('tamano', el.tamano, 6, 400))}</div>
        <div class="col-6">${campo('Espaciado', numero('tracking', el.tracking, 0, 40, 0.5))}</div></div>`;
      html += campo('Alineación', opciones('alineacion', el.alineacion,
        [['izquierda', 'Izquierda'], ['centro', 'Centro'], ['derecha', 'Derecha']]));
      html += `<div class="row g-2">
        <div class="col-6">${campo('Ancho bloque', numero('ancho_bloque', el.ancho_bloque, 1, 4000))}</div>
        <div class="col-6">${campo('Renglones', numero('renglones', el.renglones, 1, 9))}</div></div>`;
      html += casilla('negrita', el.negrita, 'Negrita');
      html += casilla('autoajustar', el.autoajustar, 'Achicar si no entra');
      if (el.autoajustar) html += campo('Cuerpo mínimo', numero('tamano_min', el.tamano_min, 4, 400));

    } else if (el.tipo === 'barcode') {
      html += seccion('Contenido');
      html += campo('Dato', texto('texto', el.texto),
        'Usá {codigo_barra}: es el mismo código comprimido a dígitos, ocupa un '
        + 'tercio del ancho y el lector no lo deforma. El {codigo} largo va en un texto aparte.');
      html += campo('Simbología', opciones('simbologia', el.simbologia,
        [['code128', 'Code 128'], ['code39', 'Code 39'], ['ean13', 'EAN-13'], ['qr', 'QR']]));
      html += seccion('Tamaño');
      if (el.simbologia === 'qr') {
        html += campo('Lado', numero('alto_barra', el.alto_barra, QR_TAM_MIN, 800),
          'PDF y ZPL usan exactamente esta medida.');
      } else {
        html += `<div class="row g-2">
          <div class="col-6">${campo('Alto barra', numero('alto_barra', el.alto_barra, 10, 800))}</div>
          <div class="col-6">${campo('Ancho barra', numero('modulo', el.modulo, 1, 10))}</div></div>`;
        html += casilla('mostrar_texto', el.mostrar_texto, 'Mostrar el código en letras');
        if (el.mostrar_texto) html += campo('Cuerpo del código', numero('tamano_texto', el.tamano_texto, 6, 100));
        html += casilla('centrar', el.centrar, 'Centrar siempre en la etiqueta');
      }

    } else if (el.tipo === 'simbolo') {
      const grupos = Object.entries(CATALOGO).map(([grupo, lista]) =>
        `<optgroup label="${grupo}">` + lista.map((s) =>
          `<option value="${s.clave}" ${s.clave === el.clave ? 'selected' : ''}>${s.nombre}</option>`
        ).join('') + '</optgroup>').join('');
      html += seccion('Símbolo');
      html += campo('Cuidado', `<select class="form-select form-select-sm" data-prop="clave">${grupos}</select>`);
      html += campo('Tamaño', numero('tam', el.tam, 16, 300));
      html += seccion('Leyenda');
      html += campo('Texto', texto('leyenda', el.leyenda), 'Opcional.');
      if (el.leyenda) {
        html += campo('Posición', opciones('leyenda_lado', el.leyenda_lado,
          [['abajo', 'Debajo'], ['derecha', 'A la derecha']]));
        html += campo('Cuerpo', numero('tam_leyenda', el.tam_leyenda, 4, 100));
      }

    } else if (el.tipo === 'linea') {
      html += seccion('Trazo');
      html += campo('Orientación', opciones('orientacion', el.orientacion,
        [['horizontal', 'Horizontal'], ['vertical', 'Vertical']]));
      html += `<div class="row g-2">
        <div class="col-7">${campo('Longitud', numero('largo', el.largo, 1, 4000))}</div>
        <div class="col-5">${campo('Grosor', numero('grosor', el.grosor, 1, 50))}</div></div>`;

    } else {
      html += seccion('Tamaño');
      html += `<div class="row g-2">
        <div class="col-6">${campo('Ancho', numero('ancho', el.ancho, 1, 4000))}</div>
        <div class="col-6">${campo('Alto', numero('alto', el.alto, 1, 4000))}</div></div>`;
      html += casilla('relleno', el.relleno, 'Relleno sólido');
      if (!el.relleno) {
        html += `<div class="row g-2">
          <div class="col-6">${campo('Grosor', numero('grosor', el.grosor, 1, 200))}</div>
          <div class="col-6">${campo('Redondeo', numero('redondeo', el.redondeo, 0, 100))}</div></div>`;
      }
    }

    html += seccion('Capa');
    if (el.tipo !== 'caja' && el.tipo !== 'linea') {
      html += campo('Rotación', opciones('rotacion', el.rotacion,
        [['N', 'Normal'], ['R', '90°'], ['I', '180°'], ['B', '270°']]));
    }
    html += casilla('visible', el.visible, 'Visible (se imprime)');
    html += casilla('bloqueado', el.bloqueado, 'Bloqueada');

    panel.innerHTML = html;
    conectarPropiedades();
  }

  // Cambios que abren o cierran otros campos: hay que repintar el panel entero.
  const REPINTAN = ['relleno', 'autoajustar', 'simbologia', 'mostrar_texto',
                    'leyenda', 'visible', 'bloqueado'];

  function actualizarControlesPropiedades(el) {
    document.querySelectorAll('#et-propiedades [data-prop]').forEach((control) => {
      const clave = control.dataset.prop;
      if (!(clave in el) || document.activeElement === control) return;
      if (control.type === 'checkbox') control.checked = !!el[clave];
      else control.value = el[clave];
    });
  }

  function conectarPropiedades() {
    const panel = document.getElementById('et-propiedades');

    panel.querySelectorAll('[data-prop]').forEach((control) => {
      const clave = control.dataset.prop;
      const esInmediato = control.type === 'checkbox' || control.tagName === 'SELECT';
      control.addEventListener(esInmediato ? 'change' : 'input', () => {
        const indice = estado.seleccion;
        const actual = estado.elementos[indice];
        if (!actual) return;
        if (control.type === 'checkbox') actual[clave] = control.checked;
        else if (control.type === 'number') actual[clave] = +control.value || 0;
        else actual[clave] = control.value;

        estado.elementos[indice] = normalizar(actual);
        if (clave === 'orientacion') {
          estado.elementos[indice] = traerAlLienzo(estado.elementos[indice]);
        }
        if (clave === 'visible' && !estado.elementos[indice].visible) estado.seleccion = -1;
        if (clave === 'bloqueado' && estado.elementos[indice].bloqueado) estado.seleccion = -1;
        dibujar();
        // Los controles de texto no reconstruyen paneles mientras se escribe:
        // hacerlo en cada tecla quitaba el foco, especialmente en la leyenda.
        if (esInmediato) {
          pintarCapas();
          if (REPINTAN.includes(clave)) pintarPropiedades();
        }
      });
      // El historial se anota al soltar, no en cada tecla: si no, deshacer
      // borraría letra por letra.
      control.addEventListener('change', () => {
        if (!esInmediato) {
          pintarCapas();
          if (REPINTAN.includes(clave)) pintarPropiedades();
        }
        registrar();
      });
    });

    const insertar = document.getElementById('prop-insertar');
    if (insertar) {
      insertar.addEventListener('change', () => {
        if (!insertar.value) return;
        const area = panel.querySelector('[data-prop="texto"]');
        area.value += insertar.value;
        area.dispatchEvent(new Event('input'));
        registrar();
        insertar.value = '';
      });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Papel y vista
  // ═══════════════════════════════════════════════════════════════════════════

  const selectorTamano = document.getElementById('et-tamano');
  const campoAncho = document.getElementById('et-ancho');
  const campoAlto = document.getElementById('et-alto');
  const grupoCustom = document.getElementById('et-custom');
  let ultimoCambioOrientacion = null;

  function aplicarMedidas(ancho, alto, opciones = {}) {
    estado.ancho = Math.max(8, Math.min(4000, Math.round(ancho)));
    estado.alto = Math.max(8, Math.min(4000, Math.round(alto)));
    anchoActual = estado.ancho;      // lo usa normalizar() al crear elementos

    // Los campos se escriben en mm, pero sólo si no los está tipeando el
    // usuario: reescribirlos mientras escribe le movería el cursor.
    if (document.activeElement !== campoAncho) {
      campoAncho.value = aMm(estado.ancho).toFixed(1);
    }
    if (document.activeElement !== campoAlto) {
      campoAlto.value = aMm(estado.alto).toFixed(1);
    }

    const orientacion = estado.ancho >= estado.alto ? 'horizontal' : 'vertical';
    document.getElementById('et-medidas-estado').textContent =
      `${aMm(estado.ancho).toFixed(1)} × ${aMm(estado.alto).toFixed(1)} mm · ${orientacion}`;

    // El selector se sincroniza para que no quede mostrando una medida que ya
    // no es la del papel (pasa al girar la orientación).
    const clave = `${estado.ancho}x${estado.alto}`;
    const existe = [...selectorTamano.options].some((o) => o.value === clave);
    selectorTamano.value = existe ? clave : 'custom';
    grupoCustom.hidden = selectorTamano.value !== 'custom';

    if (!opciones.silencioso) dibujar();
  }

  selectorTamano.addEventListener('change', () => {
    if (selectorTamano.value === 'custom') {
      grupoCustom.hidden = false;
      campoAncho.focus();
      campoAncho.select();
      return;
    }
    const [ancho, alto] = selectorTamano.value.split('x').map(Number);
    aplicarMedidas(ancho, alto);
    registrar();
  });

  [campoAncho, campoAlto].forEach((control) => {
    control.addEventListener('input', () => {
      // Un campo vacío o a medio tipear no debe reventar el lienzo: se ignora
      // hasta que sea un número usable.
      const anchoMm = parseFloat(campoAncho.value);
      const altoMm = parseFloat(campoAlto.value);
      if (!(anchoMm > 0) || !(altoMm > 0)) return;
      aplicarMedidas(aPuntos(anchoMm), aPuntos(altoMm));
    });
    control.addEventListener('change', registrar);
  });

  const MEDIDAS_ESCALABLES = [
    'ancho', 'alto', 'grosor', 'redondeo', 'ancho_bloque',
    'tamano', 'tamano_min', 'tracking', 'tam', 'tam_leyenda',
    'alto_barra', 'tamano_texto', 'largo',
  ];

  function limitesDelDiseno() {
    const visibles = estado.elementos.filter((el) => el.visible);
    if (!visibles.length) {
      return { x: 0, y: 0, ancho: estado.ancho, alto: estado.alto };
    }
    const cajas = visibles.map(caja);
    const izquierda = Math.min(...cajas.map((c) => c.x));
    const arriba = Math.min(...cajas.map((c) => c.y));
    const derecha = Math.max(...cajas.map((c) => c.x + c.ancho));
    const abajo = Math.max(...cajas.map((c) => c.y + c.alto));
    return {
      x: izquierda, y: arriba,
      ancho: Math.max(1, derecha - izquierda),
      alto: Math.max(1, abajo - arriba),
    };
  }

  document.getElementById('et-orientacion').addEventListener('click', () => {
    const antes = instantanea();
    if (ultimoCambioOrientacion && antes === ultimoCambioOrientacion.despues) {
      const anterior = JSON.parse(ultimoCambioOrientacion.antes);
      aplicarMedidas(anterior.ancho, anterior.alto, { silencioso: true });
      estado.elementos = anterior.elementos.map(normalizar);
      ultimoCambioOrientacion = null;
      registrar();
      ajustarZoom();
      repintarTodo();
      avisar('Se restauró la orientación y el tamaño anterior del diseño.', 'info');
      return;
    }

    const anchoAnterior = estado.ancho;
    const altoAnterior = estado.alto;
    const nuevoAncho = altoAnterior;
    const nuevoAlto = anchoAnterior;
    const limites = limitesDelDiseno();

    // Mantiene los textos derechos y adapta proporcionalmente el diseño entero
    // al nuevo papel. Dejar las coordenadas intactas hacía que, al pasar de
    // horizontal a vertical, la mitad derecha quedara fuera del marco.
    const margen = Math.min(8, nuevoAncho / 10, nuevoAlto / 10);
    const factor = Math.min(
      1,
      (nuevoAncho - margen * 2) / limites.ancho,
      (nuevoAlto - margen * 2) / limites.alto,
    );
    const offsetX = (nuevoAncho - limites.ancho * factor) / 2 - limites.x * factor;
    const offsetY = (nuevoAlto - limites.alto * factor) / 2 - limites.y * factor;

    aplicarMedidas(nuevoAncho, nuevoAlto, { silencioso: true });
    estado.elementos = estado.elementos.map((original) => {
      const el = clonar(original);
      el.x = Math.round((+el.x || 0) * factor + offsetX);
      el.y = Math.round((+el.y || 0) * factor + offsetY);

      for (const clave of MEDIDAS_ESCALABLES) {
        if (!(clave in el)) continue;
        const valor = Number(el[clave]);
        if (!Number.isFinite(valor)) continue;
        el[clave] = clave === 'tracking'
          ? Math.round(valor * factor * 100) / 100
          : Math.round(valor * factor);
      }
      if ('modulo' in el) el.modulo = clamp(el.modulo * factor, 1, 10);
      return traerAlLienzo(normalizar(el));
    });

    ultimoCambioOrientacion = { antes, despues: instantanea() };
    registrar();
    ajustarZoom();
    repintarTodo();
    avisar('Orientación cambiada: el diseño se adaptó y centró dentro del papel.', 'info');
  });

  let anclaZoom = null;
  let frameZoom = null;

  function zoom(delta) {
    if (!anclaZoom) {
      const escenario = document.getElementById('et-escenario');
      const rectEscenario = escenario.getBoundingClientRect();
      const rectLienzo = lienzo.getBoundingClientRect();
      const centroX = rectEscenario.left + escenario.clientWidth / 2;
      const centroY = rectEscenario.top + escenario.clientHeight / 2;
      anclaZoom = {
        escenario,
        focoX: Math.max(0, Math.min(estado.ancho,
          (centroX - rectLienzo.left - REGLA) / estado.escala)),
        focoY: Math.max(0, Math.min(estado.alto,
          (centroY - rectLienzo.top - REGLA) / estado.escala)),
      };
    }
    estado.escala = Math.max(0.5, Math.min(8, estado.escala + delta));
    actualizarIndicadorZoom();
    if (frameZoom !== null) return;

    // Varios clics rápidos se agrupan: todos reutilizan el foco del primer clic
    // y el canvas sólo adopta la escala final una vez.
    frameZoom = window.requestAnimationFrame(() => {
      frameZoom = null;
      if (frameDibujo !== null) {
        window.cancelAnimationFrame(frameDibujo);
        frameDibujo = null;
      }
      dibujarAhora();
      const { escenario, focoX, focoY } = anclaZoom;
      const nuevoLienzo = lienzo.getBoundingClientRect();
      const nuevoEscenario = escenario.getBoundingClientRect();
      const nuevoCentroX = nuevoEscenario.left + escenario.clientWidth / 2;
      const nuevoCentroY = nuevoEscenario.top + escenario.clientHeight / 2;
      const focoPantallaX = nuevoLienzo.left + REGLA + focoX * estado.escala;
      const focoPantallaY = nuevoLienzo.top + REGLA + focoY * estado.escala;
      escenario.scrollLeft += focoPantallaX - nuevoCentroX;
      escenario.scrollTop += focoPantallaY - nuevoCentroY;
      anclaZoom = null;
    });
  }

  function ajustarZoom() {
    const escenario = document.getElementById('et-escenario');
    const rect = escenario.getBoundingClientRect();
    const disponibleX = rect.width - REGLA - 48;
    const disponibleY = rect.height - REGLA - 48;
    if (disponibleX <= 0 || disponibleY <= 0) return;
    estado.escala = Math.max(0.5, Math.min(8,
      Math.min(disponibleX / estado.ancho, disponibleY / estado.alto)));
    actualizarZoom();
  }

  // Escala a la que la etiqueta se ve en pantalla del tamaño que va a tener en
  // el papel: un punto de cabezal mide 25,4/203 mm y un píxel CSS 25,4/96 mm.
  const ESCALA_REAL = 96 / 203;

  function actualizarIndicadorZoom() {
    document.getElementById('et-zoom-estado').textContent =
      Math.round(estado.escala / ESCALA_REAL * 100) + '%';
  }

  function actualizarZoom() {
    actualizarIndicadorZoom();
    dibujar();
  }

  document.getElementById('et-zoom-mas').addEventListener('click', () => zoom(0.5));
  document.getElementById('et-zoom-menos').addEventListener('click', () => zoom(-0.5));
  document.getElementById('et-zoom-ajustar').addEventListener('click', ajustarZoom);

  function alternarGrilla() {
    estado.grilla = !estado.grilla;
    document.getElementById('et-grilla').classList.toggle('activa', estado.grilla);
    dibujar();
  }
  function alternarIman() {
    estado.iman = !estado.iman;
    document.getElementById('et-iman').classList.toggle('activa', estado.iman);
  }
  document.getElementById('et-grilla').addEventListener('click', alternarGrilla);
  document.getElementById('et-iman').addEventListener('click', alternarIman);

  document.getElementById('et-deshacer').addEventListener('click', () => restaurar(-1));
  document.getElementById('et-rehacer').addEventListener('click', () => restaurar(1));

  ['et-nombre', 'et-descripcion'].forEach((id) =>
    document.getElementById(id).addEventListener('input', marcarSucio));
  document.getElementById('et-predeterminada').addEventListener('change', marcarSucio);

  // ═══════════════════════════════════════════════════════════════════════════
  // Prenda real para la vista previa
  // ═══════════════════════════════════════════════════════════════════════════

  const buscador = document.getElementById('et-buscar-item');
  const cuerpoItems = document.getElementById('et-items-cuerpo');
  const avisoItems = document.getElementById('et-items-aviso');
  const cartel = document.getElementById('et-datos-estado');
  let temporizador = null;

  // El modal se instancia al primer uso y no al arrancar: así el diseñador no
  // depende de que el bundle de Bootstrap haya llegado antes que este archivo.
  let modalItems = null;
  const abrirModalItems = () => {
    if (!modalItems) {
      modalItems = new bootstrap.Modal(document.getElementById('et-modal-items'));
    }
    modalItems.show();
  };

  document.getElementById('et-abrir-items').addEventListener('click', () => {
    abrirModalItems();
    buscarItems();          // se abre con las primeras prendas ya listadas
  });

  // El foco al buscador se pide cuando el modal terminó de aparecer: hacerlo
  // antes no tiene efecto porque el elemento todavía no es visible.
  document.getElementById('et-modal-items').addEventListener('shown.bs.modal', () => {
    buscador.focus();
    buscador.select();
  });

  buscador.addEventListener('input', () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(buscarItems, 300);
  });

  function filaItem(it) {
    return `<tr data-item="${it.id}">
      <td class="et-item-codigo">${escaparHtml(it.codigo)}</td>
      <td>${escaparHtml(it.nombre)}</td>
      <td class="et-item-detalle">${escaparHtml(it.detalle)}</td>
    </tr>`;
  }

  async function buscarItems() {
    const consulta = buscador.value.trim();
    try {
      const respuesta = await fetch(`${app.dataset.urlItems}?q=${encodeURIComponent(consulta)}`);
      const datos = await respuesta.json();

      if (!datos.items.length) {
        cuerpoItems.innerHTML =
          '<tr><td colspan="3" class="text-muted py-4 text-center">'
          + 'Ninguna prenda coincide con la búsqueda.</td></tr>';
        avisoItems.textContent = '';
        return;
      }

      cuerpoItems.innerHTML = datos.items.map(filaItem).join('');

      // El servidor corta en 40. Si vinieron 40 justos es casi seguro que hay
      // más, y sin avisarlo el usuario cree que la prenda que busca no existe.
      avisoItems.textContent = datos.items.length >= 40
        ? 'Se muestran las primeras 40. Escribí un poco más para achicar la lista.'
        : `${datos.items.length} prenda${datos.items.length === 1 ? '' : 's'}.`;

      cuerpoItems.querySelectorAll('[data-item]').forEach((fila) => {
        const item = datos.items.find((i) => String(i.id) === fila.dataset.item);
        fila.addEventListener('click', () => elegirItem(item));
      });
    } catch (error) {
      cuerpoItems.innerHTML =
        '<tr><td colspan="3" class="text-muted py-4 text-center">'
        + 'No se pudo consultar el inventario.</td></tr>';
      avisoItems.textContent = '';
    }
  }

  function elegirItem(item) {
    estado.itemId = item.id;
    if (modalItems) modalItems.hide();
    buscador.value = '';
    datosActuales = Object.assign({}, MUESTRA, item.datos || {
      codigo: item.codigo, prenda: item.nombre, subtitulo: item.detalle,
    });
    cartel.innerHTML = `<strong>${escaparHtml(item.codigo)}</strong>
      <a href="#" id="et-quitar-item" class="ms-1">✕</a>`;
    document.getElementById('et-quitar-item').addEventListener('click', (evento) => {
      evento.preventDefault();
      estado.itemId = null;
      datosActuales = Object.assign({}, MUESTRA);
      cartel.textContent = 'Datos de muestra';
      dibujar();
    });
    dibujar();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Acciones
  // ═══════════════════════════════════════════════════════════════════════════

  function cuerpo() {
    return JSON.stringify({
      nombre: document.getElementById('et-nombre').value,
      descripcion: document.getElementById('et-descripcion').value,
      predeterminada: document.getElementById('et-predeterminada').checked,
      elementos: estado.elementos,
      ancho: estado.ancho,
      alto: estado.alto,
      item_id: estado.itemId,
      copias: +document.getElementById('et-copias').value || 1,
    });
  }

  const cabeceras = { 'Content-Type': 'application/json', 'X-CSRFToken': csrf };

  function avisar(mensaje, tipo) {
    const aviso = document.createElement('div');
    aviso.className = `alert alert-${tipo} position-fixed shadow`;
    aviso.style.cssText = 'bottom:1rem;left:50%;transform:translateX(-50%);z-index:1080;max-width:28rem';
    aviso.textContent = mensaje;
    document.body.appendChild(aviso);
    setTimeout(() => aviso.remove(), 5000);
  }

  document.getElementById('et-guardar').addEventListener('click', async () => {
    const respuesta = await fetch(app.dataset.urlGuardar,
      { method: 'POST', headers: cabeceras, body: cuerpo() });
    const datos = await respuesta.json();
    if (!datos.ok) { avisar(datos.error, 'danger'); return; }

    estado.sucio = false;
    document.getElementById('et-sin-guardar').hidden = true;
    avisar(datos.mensaje, 'success');
    // Si era nueva, se pasa a la URL de edición para que guardar otra vez
    // actualice esta plantilla en vez de crear una tercera.
    if (!estado.guardado && datos.url) window.location = datos.url;
  });

  document.getElementById('et-ver-pdf').addEventListener('click', async () => {
    // La ventana se abre AHORA, con el clic todavía en curso: si se abriera
    // después del fetch, el bloqueador de emergentes la cortaría.
    const ventana = window.open('', '_blank');
    const respuesta = await fetch(app.dataset.urlPdf,
      { method: 'POST', headers: cabeceras, body: cuerpo() });
    if (!respuesta.ok) {
      if (ventana) ventana.close();
      avisar(await respuesta.text() || 'No se pudo generar el PDF.', 'danger');
      return;
    }
    const url = URL.createObjectURL(await respuesta.blob());
    if (ventana) ventana.location = url; else window.location = url;
  });

  document.getElementById('et-ver-zpl').addEventListener('click', async () => {
    const respuesta = await fetch(app.dataset.urlZpl,
      { method: 'POST', headers: cabeceras, body: cuerpo() });
    const datos = await respuesta.json();
    if (!respuesta.ok || !datos.ok) {
      avisar(datos.error || 'No se pudo generar el ZPL.', 'danger');
      return;
    }
    document.getElementById('et-zpl').textContent = datos.zpl || '';
    new bootstrap.Modal(document.getElementById('et-modal-zpl')).show();
  });

  document.getElementById('et-descargar-zpl').addEventListener('click', async () => {
    const respuesta = await fetch(app.dataset.urlZplDescargar,
      { method: 'POST', headers: cabeceras, body: cuerpo() });
    if (!respuesta.ok) {
      const datos = await respuesta.json();
      avisar(datos.error || 'No se pudo descargar el ZPL.', 'danger');
      return;
    }
    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(await respuesta.blob());
    enlace.download = 'etiqueta.zpl';
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  });

  // El puente de impresión corre en la PC del taller y es el único que puede
  // tocar el USB de la impresora. El cliente vive en etiquetas_puente.js porque
  // también lo usa la pantalla suelta de ajustes. Ver puente_impresion/README.md.
  const imprimirPorPuente = window.PuenteImpresion.imprimir;

  /* Manda a imprimir lo que hay AHORA en el lienzo, guardado o no.
   *
   * Tres intentos en orden: el servidor arma el ZPL, el puente lo tira al USB
   * y, si no hay puente, se prueba que imprima el propio Django (sólo sirve
   * cuando corre en la misma PC que la impresora). */
  async function imprimirLienzo() {
    // Paso 1: el ZPL siempre lo arma el servidor, que es donde vive la plantilla
    // y la configuración del cabezal. El puente sólo lo reenvía al USB.
    const respuesta = await fetch(app.dataset.urlZpl,
      { method: 'POST', headers: cabeceras, body: cuerpo() });
    const datos = await respuesta.json();
    if (!respuesta.ok || !datos.ok) {
      avisar(datos.error || 'No se pudo generar el ZPL.', 'danger');
      return;
    }

    // Paso 2: el puente en la PC del taller.
    try {
      const salida = await imprimirPorPuente(datos.zpl);
      avisar(salida.ok ? salida.mensaje : salida.error,
             salida.ok ? 'success' : 'danger');
      return;
    } catch (error) {
      // No hay puente escuchando. Se sigue con el plan B en vez de cortar acá.
    }

    // Paso 3: plan B — que imprima el propio servidor. Sólo funciona cuando
    // Django corre en la misma PC que la impresora (desarrollo, o instalación
    // local sin hosting). En producción esto falla y se cae al aviso final.
    try {
      const local = await fetch(app.dataset.urlImprimir,
        { method: 'POST', headers: cabeceras, body: cuerpo() });
      const resultado = await local.json();
      if (resultado.ok) {
        avisar(resultado.mensaje, 'success');
        return;
      }
    } catch (error) {
      // Sin conexión con el servidor: cae al aviso de abajo igual.
    }

    avisar('No se encontró el puente de impresión. Verificá que esté corriendo '
           + 'en esta PC, o usá «Descargar ZPL» para imprimir a mano.', 'warning');
  }

  document.getElementById('et-imprimir').addEventListener('click', imprimirLienzo);

  // ═══════════════════════════════════════════════════════════════════════════
  // Ajustes de la impresora
  //
  // Encontrar la oscuridad y el encuadre correctos es prueba y error contra el
  // rollo: tocar un número, imprimir, mirar, corregir. Por eso el modal guarda
  // por fetch y NO recarga: una recarga acá se llevaría puesto el diseño sin
  // guardar, y con eso el ciclo entero deja de valer la pena.
  // ═══════════════════════════════════════════════════════════════════════════

  const modalImpresora = document.getElementById('et-modal-impresora');
  const estadoImpresora = document.getElementById('et-impresora-estado');

  function avisarImpresora(texto, clase) {
    estadoImpresora.textContent = texto;
    estadoImpresora.className = `small text-${clase}`;
  }

  document.getElementById('et-abrir-impresora').addEventListener('click', () => {
    avisarImpresora('', 'muted');
    new bootstrap.Modal(modalImpresora).show();
  });

  /* Guarda los ajustes del cabezal. Devuelve si salió bien, para que
     «Guardar e imprimir» no imprima con valores que no llegaron a guardarse. */
  async function guardarImpresora() {
    const campos = new FormData();
    campos.append('oscuridad', document.getElementById('et-oscuridad').value);
    campos.append('velocidad', document.getElementById('et-velocidad').value);
    campos.append('desplazamiento_x', document.getElementById('et-desp-x').value);
    campos.append('desplazamiento_y', document.getElementById('et-desp-y').value);
    campos.append('tipo_papel', document.getElementById('et-tipo-papel').value);
    // Un checkbox destildado no viaja: el servidor lee la ausencia como «no».
    if (document.getElementById('et-usa-ribbon').checked) {
      campos.append('usa_ribbon', 'on');
    }

    let datos;
    try {
      const respuesta = await fetch(app.dataset.urlImpresora, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
        body: campos,
      });
      datos = await respuesta.json();
    } catch (error) {
      avisarImpresora('No se pudo hablar con el servidor.', 'danger');
      return false;
    }

    avisarImpresora(datos.ok ? 'Ajustes guardados.' : datos.error,
                    datos.ok ? 'success' : 'danger');
    return !!datos.ok;
  }

  document.getElementById('et-guardar-impresora')
    .addEventListener('click', guardarImpresora);

  document.getElementById('et-probar-impresora').addEventListener('click', async (evento) => {
    const boton = evento.currentTarget;
    boton.disabled = true;
    avisarImpresora('Guardando e imprimiendo…', 'muted');
    // El modal queda abierto a propósito: el usuario mira la etiqueta que sale
    // y corrige el número ahí mismo, sin volver a abrir nada.
    if (await guardarImpresora()) await imprimirLienzo();
    boton.disabled = false;
  });

  document.getElementById('et-calibrar-impresora').addEventListener('click', async (evento) => {
    const boton = evento.currentTarget;
    boton.disabled = true;
    avisarImpresora('Calibrando…', 'muted');

    const salida = await window.PuenteImpresion.calibrar(app.dataset.urlCalibrar);
    avisarImpresora(salida.mensaje, salida.ok ? 'success' : 'danger');

    boton.disabled = false;
  });

  window.addEventListener('beforeunload', (evento) => {
    if (!estado.sucio) return;
    evento.preventDefault();
    evento.returnValue = '';
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // Arranque
  // ═══════════════════════════════════════════════════════════════════════════

  /* El editor ocupa lo que queda de pantalla. Se mide en vez de calcularse con
   * `calc(100vh - algo)` porque encima puede haber un aviso de caja cerrada o
   * un mensaje del sistema, y con una altura fija la barra de estado terminaba
   * abajo del pliegue. */
  function ajustarAlto() {
    // Un editor a pantalla completa no lleva encabezado vacío ni pie de página.
    const cabecera = document.querySelector('.page-header');
    if (cabecera && !cabecera.textContent.trim()) cabecera.style.display = 'none';
    const pie = document.querySelector('.page-wrapper > .footer');
    if (pie) pie.style.display = 'none';

    const arriba = app.getBoundingClientRect().top + window.scrollY;
    app.style.height = Math.max(520, window.innerHeight - arriba - 12) + 'px';
  }

  aplicarMedidas(estado.ancho, estado.alto, { silencioso: true });
  historial.pila = [instantanea()];
  historial.indice = 0;
  estado.sucio = false;
  refrescarHistorial();
  ajustarAlto();
  ajustarZoom();
  repintarTodo();

  window.addEventListener('resize', () => { ajustarAlto(); dibujar(); });
})();
