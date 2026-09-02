"""Diseñador de etiquetas: pantalla, guardado, vista previa e impresión.

Va en su propio módulo y no en `views.py` porque aquél ya pasa las 9.500 líneas.
Las URLs lo importan igual que a cualquier otra vista.

Las tres salidas que ofrece la pantalla, y por qué son tres:

  · PDF       — funciona siempre, desde el hosting. Es el camino por defecto.
  · ZPL (ver) — el texto que se le manda a la SAT, para revisarlo o guardarlo.
  · Imprimir  — envío directo a la impresora. Sólo desde la PC del taller: el
                hosting es Linux y no tiene el puerto USB de la térmica.
"""

import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import etiquetas, etiquetas_pdf, etiquetas_zpl, simbolos
from .models import (
    ConfiguracionImpresora, PlantillaEtiqueta, PrendaInventario, PrendaItem,
)


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _cuerpo(request):
    """El JSON del request, o {} si vino vacío o roto."""
    try:
        return json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _medidas(datos, plantilla=None):
    """Ancho y alto en puntos, del payload o de la plantilla, con tope sano."""
    ancho = datos.get('ancho') or (plantilla.ancho_puntos if plantilla else None)
    alto = datos.get('alto') or (plantilla.alto_puntos if plantilla else None)
    try:
        ancho = int(ancho or etiquetas.ANCHO_DEFECTO)
        alto = int(alto or etiquetas.ALTO_DEFECTO)
    except (TypeError, ValueError):
        ancho, alto = etiquetas.ANCHO_DEFECTO, etiquetas.ALTO_DEFECTO
    # 8 puntos es 1 mm; 4000 es medio metro. Fuera de ahí es un error de tipeo,
    # y un lienzo gigante cuelga el navegador antes de que se note.
    return max(8, min(4000, ancho)), max(8, min(4000, alto))


def _datos_pedidos(datos):
    """Los datos con los que renderizar: los de una unidad real, o de muestra.

    El diseñador manda `item_id` cuando el usuario eligió una prenda concreta en
    el selector. Sin eso se usan datos ficticios: el punto es ver cómo queda un
    texto de largo verosímil, no dejar la etiqueta vacía mientras se diseña.
    """
    item_id = datos.get('item_id')
    if item_id:
        item = (PrendaItem.objects.select_related('prenda', 'ubicacion')
                .filter(pk=item_id).first())
        if item:
            return etiquetas.datos_de_item(item)
    return etiquetas.datos_muestra(datos.get('datos'))


def _copias(datos):
    try:
        return max(1, min(50, int(datos.get('copias') or 1)))
    except (TypeError, ValueError):
        return 1


# ─────────────────────────────────────────────────────────────────────────────
# Recursos del lienzo
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def simbolo_png(request, clave):
    """Sirve un símbolo de cuidado como PNG, para el lienzo del diseñador.

    Es el mismo dibujo que después va al ^GF de la impresora y al PDF: si la
    vista previa se generara aparte, podrían divergir y el operario se enteraría
    con la etiqueta ya pegada.
    """
    try:
        tam = int(request.GET.get('tam', 64))
    except (TypeError, ValueError):
        tam = 64

    try:
        datos = simbolos.png(clave, max(8, min(400, tam)))
    except simbolos.SimboloDesconocido:
        raise Http404(f"No existe el símbolo «{clave}»")

    respuesta = HttpResponse(datos, content_type='image/png')
    # Un símbolo dado a un tamaño dado siempre se dibuja igual: se puede cachear
    # sin miedo, y el lienzo pide muchos por segundo mientras se arrastra.
    respuesta['Cache-Control'] = 'public, max-age=86400'
    return respuesta


@login_required
def buscar_items(request):
    """Busca unidades físicas de inventario para el selector del diseñador.

    Se buscan PrendaItem y no PrendaInventario porque la etiqueta va pegada a
    una prenda concreta: el `codigo_item` (PRN-010-ITM-01) es lo que distingue
    dos ternos idénticos, que es justamente para lo que sirve etiquetarlos.

    Devuelve además el stock del SKU al que pertenece cada unidad. Es la
    pregunta que se hace el que va a etiquetar —«¿cuántas de éstas tengo?»— y
    sin el dato hay que salir del diseñador a buscarlo a Inventario.
    """
    texto = (request.GET.get('q') or '').strip()
    tipo = (request.GET.get('tipo') or '').strip()

    items = (PrendaItem.objects
             .exclude(estado='baja')
             .select_related('prenda', 'ubicacion'))
    if texto:
        items = items.filter(
            Q(codigo_item__icontains=texto)
            | Q(prenda__nombre__icontains=texto)
            | Q(prenda__codigo__icontains=texto)
            | Q(prenda__talla__icontains=texto)
            | Q(prenda__color__icontains=texto)
        )
    if tipo in dict(PrendaItem.TIPO_CHOICES):
        items = items.filter(tipo=tipo)

    items = list(items.order_by('codigo_item')[:40])

    # El stock se resuelve en UNA consulta agregada aparte y no anotando el
    # queryset de arriba: anotarlo obligaría a un join de la tabla contra sí
    # misma con `distinct`, que para 40 filas sale más caro que esto.
    conteos = {
        fila['prenda_id']: fila
        for fila in (PrendaItem.objects
                     .filter(prenda_id__in={it.prenda_id for it in items})
                     .exclude(estado='baja')
                     .values('prenda_id')
                     .annotate(total=Count('id'),
                               disponibles=Count('id', filter=Q(estado='disponible'))))
    }

    return JsonResponse({
        'ok': True,
        'items': [
            {
                'id': it.pk,
                'codigo': it.codigo_item,
                'nombre': it.prenda.nombre,
                'detalle': ' · '.join(filter(None, [
                    f"T {it.prenda.talla}" if it.prenda.talla else None,
                    it.prenda.color or None,
                    it.get_condicion_display(),
                ])),
                'tipo': it.tipo,
                'tipo_nombre': it.get_tipo_display(),
                'estado': it.estado,
                'estado_nombre': it.get_estado_display(),
                # Stock del SKU, no de esta unidad: una unidad siempre es una.
                'stock_disponible': conteos.get(it.prenda_id, {}).get('disponibles', 0),
                'stock_total': conteos.get(it.prenda_id, {}).get('total', 0),
                'datos': etiquetas.datos_de_item(it),
            }
            for it in items
        ],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Plantillas
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def lista_plantillas(request):
    plantillas = PlantillaEtiqueta.objects.all()
    return render(request, 'misastreria/etiquetas/lista.html', {
        'page_obj': plantillas,
        'total': plantillas.count(),
        'impresora': etiquetas_zpl.IMPRESORA,
        'tamanos': etiquetas.tamanos_para_selector(),
        'tamano_defecto': etiquetas.TAMANO_DEFECTO,
    })


@login_required
def disenador(request, id=None):
    """La pantalla del diseñador.

    Sin id busca la plantilla predeterminada y redirige a ella: es lo que el
    usuario espera al volver, encontrar su diseño y no una etiqueta en blanco.

    Con `?nueva=1` no redirige. El asistente puede pedir un lienzo vacío o copiar
    la predeterminada, además de elegir tamaño y orientación antes de entrar.
    """
    if id is None and not request.GET.get('nueva'):
        predeterminada = PlantillaEtiqueta.predeterminada()
        if predeterminada:
            return redirect('editar_plantilla', id=predeterminada.pk)

    if id:
        plantilla = get_object_or_404(PlantillaEtiqueta, pk=id)
        elementos = plantilla.elementos or []
        ancho, alto = plantilla.ancho_puntos, plantilla.alto_puntos
    else:
        plantilla = None
        base = PlantillaEtiqueta.predeterminada()
        origen = (request.GET.get('origen') or 'predeterminada').strip()
        if origen == 'vacia':
            elementos = []
            ancho, alto = etiquetas.ANCHO_DEFECTO, etiquetas.ALTO_DEFECTO
        elif origen == 'textil':
            elementos = etiquetas.elementos_textil_vertical()
            ancho = etiquetas.mm_a_puntos(50)
            alto = etiquetas.mm_a_puntos(100)
        elif base is not None:
            elementos = base.elementos or []
            ancho, alto = base.ancho_puntos, base.alto_puntos
        else:
            # Primer arranque: todavía no hay ninguna plantilla cargada.
            elementos = etiquetas.elementos_por_defecto()
            ancho, alto = etiquetas.ANCHO_DEFECTO, etiquetas.ALTO_DEFECTO

        # El lienzo ES el papel: pedir «horizontal» no reinterpreta nada,
        # describe un rollo distinto: el que hay que cargar en la impresora. Se
        # intercambian las medidas y listo — no queda ninguna bandera que
        # recordar ni ningún giro que aplicar al imprimir.
        clave_tamano = (request.GET.get('tamano') or '').strip()
        pedida = (request.GET.get('orientacion') or '').strip()
        if clave_tamano in etiquetas.TAMANOS_MM:
            ancho_mm, alto_mm = etiquetas.TAMANOS_MM[clave_tamano]
            nuevo_ancho = etiquetas.mm_a_puntos(ancho_mm)
            nuevo_alto = etiquetas.mm_a_puntos(alto_mm)
        else:
            nuevo_ancho, nuevo_alto = ancho, alto

        quiere_apaisado = {'horizontal': True, 'vertical': False}.get(pedida)
        if (quiere_apaisado is not None
                and quiere_apaisado != (nuevo_ancho >= nuevo_alto)):
            nuevo_ancho, nuevo_alto = nuevo_alto, nuevo_ancho

        if elementos and (nuevo_ancho != ancho or nuevo_alto != alto):
            factor = min(nuevo_ancho / ancho, nuevo_alto / alto)
            offset_x = (nuevo_ancho - ancho * factor) / 2
            offset_y = (nuevo_alto - alto * factor) / 2
            elementos = etiquetas.escalar(elementos, factor)
            for elemento in elementos:
                elemento['x'] = int(round(elemento.get('x', 0) + offset_x))
                elemento['y'] = int(round(elemento.get('y', 0) + offset_y))
        ancho, alto = nuevo_ancho, nuevo_alto

    # Se pasan como objetos y no como cadenas: |json_script se encarga de
    # serializarlos y escaparlos, y el JS los lee con un solo JSON.parse.
    return render(request, 'misastreria/etiquetas/disenador.html', {
        'plantilla': plantilla,
        'elementos': elementos,
        'campos': etiquetas.CAMPOS,
        'simbolos': simbolos.catalogo_para_json(),
        'muestra': etiquetas.datos_muestra(),
        'tamanos': etiquetas.tamanos_para_selector(),
        'ancho': ancho,
        'alto': alto,
        'impresora': etiquetas_zpl.IMPRESORA,
        'config': ConfiguracionImpresora.cargar(),
    })


@login_required
@require_POST
def guardar_plantilla(request, id=None):
    """Crea o actualiza una plantilla. Responde JSON para el diseñador."""
    datos = _cuerpo(request)

    nombre = (datos.get('nombre') or '').strip()
    if not nombre:
        return JsonResponse({'ok': False, 'error': "Poné un nombre a la plantilla."},
                            status=400)

    elementos = datos.get('elementos')
    if not isinstance(elementos, list):
        return JsonResponse({'ok': False, 'error': "Elementos inválidos."}, status=400)

    plantilla = get_object_or_404(PlantillaEtiqueta, pk=id) if id else PlantillaEtiqueta()

    # El nombre es único: avisamos con un mensaje entendible en vez de dejar que
    # reviente la restricción de la base con un 500.
    choque = PlantillaEtiqueta.objects.filter(nombre=nombre)
    if plantilla.pk:
        choque = choque.exclude(pk=plantilla.pk)
    if choque.exists():
        return JsonResponse(
            {'ok': False, 'error': f"Ya existe una plantilla llamada «{nombre}»."},
            status=400,
        )

    ancho, alto = _medidas(datos, plantilla if plantilla.pk else None)

    plantilla.nombre = nombre
    # Sólo se pisa si vino en el payload: un cliente que no mande el campo no
    # debe borrar la descripción que ya tenía la plantilla.
    if 'descripcion' in datos:
        plantilla.descripcion = (datos.get('descripcion') or '').strip()[:200]
    plantilla.ancho_puntos = ancho
    plantilla.alto_puntos = alto
    plantilla.elementos = elementos
    plantilla.es_predeterminada = bool(datos.get('predeterminada'))
    plantilla.save()

    return JsonResponse({
        'ok': True,
        'id': plantilla.pk,
        'url': f"/etiquetas/disenador/{plantilla.pk}/",
        'mensaje': f"Plantilla «{plantilla.nombre}» guardada.",
    })


@login_required
def eliminar_plantilla(request, id):
    plantilla = get_object_or_404(PlantillaEtiqueta, pk=id)

    if request.method == 'POST':
        # Sin plantillas no hay etiquetas: el inventario, las reparaciones y las
        # confecciones renderizan todas contra la predeterminada.
        if PlantillaEtiqueta.objects.count() <= 1:
            messages.error(
                request,
                "No se puede eliminar la única plantilla: el sistema se quedaría "
                "sin diseño para imprimir etiquetas."
            )
            return redirect('lista_plantillas')

        nombre = plantilla.nombre
        era_predeterminada = plantilla.es_predeterminada
        plantilla.delete()

        # Si se borró la predeterminada, otra tiene que ocupar el lugar o las
        # etiquetas del sistema dejan de salir.
        if era_predeterminada:
            reemplazo = PlantillaEtiqueta.objects.first()
            if reemplazo:
                reemplazo.es_predeterminada = True
                reemplazo.save()
                messages.info(
                    request,
                    f"«{reemplazo.nombre}» pasó a ser la plantilla predeterminada."
                )

        messages.success(request, f"Plantilla «{nombre}» eliminada.")
        return redirect('lista_plantillas')

    return render(request, 'misastreria/etiquetas/eliminar.html', {
        'plantilla': plantilla,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Salidas
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_POST
def previsualizar_pdf(request):
    """El PDF de lo que hay en el lienzo. Es la vista previa fiel.

    El lienzo del navegador dibuja aproximado —usa las fuentes del sistema, no
    las del PDF— así que esto es lo que manda: si acá entra, en el papel entra.
    """
    datos = _cuerpo(request)
    ancho, alto = _medidas(datos)
    valores = _datos_pedidos(datos)
    try:
        etiquetas.validar_elementos(datos.get('elementos') or [], valores, ancho)
    except etiquetas.DatoNoImprimible as exc:
        return HttpResponse(str(exc), content_type='text/plain; charset=utf-8', status=400)
    pdf = etiquetas_pdf.render(
        datos.get('elementos') or [],
        ancho=ancho, alto=alto,
        lote=[valores],
    )
    respuesta = HttpResponse(pdf, content_type='application/pdf')
    respuesta['Content-Disposition'] = 'inline; filename="vista_previa.pdf"'
    return respuesta


@login_required
@require_POST
def previsualizar_zpl(request):
    """El ZPL de lo que hay en el lienzo, como texto. No imprime nada."""
    datos = _cuerpo(request)
    ancho, alto = _medidas(datos)
    valores = _datos_pedidos(datos)
    try:
        etiquetas.validar_elementos(datos.get('elementos') or [], valores, ancho)
    except etiquetas.DatoNoImprimible as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    zpl = etiquetas_zpl.render(
        datos.get('elementos') or [],
        ancho=ancho, alto=alto,
        datos=valores,
        copias=_copias(datos),
        config=ConfiguracionImpresora.cargar(),
    )
    return JsonResponse({'ok': True, 'zpl': zpl})


@login_required
@require_POST
def descargar_zpl(request):
    """Descarga el ZPL como archivo .zpl.

    Es el puente práctico entre el hosting y el taller: el servidor no puede
    hablarle a la impresora, pero sí generar el archivo, y en la PC del taller
    un `copy /b etiqueta.zpl \\\\localhost\\SAT` lo manda al puerto.
    """
    datos = _cuerpo(request)
    ancho, alto = _medidas(datos)
    valores = _datos_pedidos(datos)
    try:
        etiquetas.validar_elementos(datos.get('elementos') or [], valores, ancho)
    except etiquetas.DatoNoImprimible as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)
    zpl = etiquetas_zpl.render(
        datos.get('elementos') or [],
        ancho=ancho, alto=alto,
        datos=valores,
        copias=_copias(datos),
        config=ConfiguracionImpresora.cargar(),
    )
    respuesta = HttpResponse(zpl, content_type='text/plain; charset=utf-8')
    respuesta['Content-Disposition'] = 'attachment; filename="etiqueta.zpl"'
    return respuesta


@login_required
@require_POST
def imprimir(request):
    """Manda a la SAT lo que hay en el lienzo. Acá sí sale papel.

    Sólo funciona si Django corre en la PC que tiene la impresora conectada. En
    el hosting devuelve 503 con la explicación, no un 500 sin contexto.
    """
    datos = _cuerpo(request)
    ancho, alto = _medidas(datos)
    valores = _datos_pedidos(datos)

    # Se comprueba que los códigos sean imprimibles ANTES de mandarlos: una
    # etiqueta ilegible se descubre cuando la pistola no la lee, y para entonces
    # ya está pegada a la prenda.
    try:
        etiquetas.validar_elementos(datos.get('elementos') or [], valores, ancho)
    except etiquetas.DatoNoImprimible as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

    zpl = etiquetas_zpl.render(
        datos.get('elementos') or [],
        ancho=ancho, alto=alto, datos=valores, copias=_copias(datos),
        config=ConfiguracionImpresora.cargar(),
    )

    try:
        estado, _en_cola = etiquetas_zpl.estado_impresora()
        etiquetas_zpl.enviar(zpl)
    except etiquetas_zpl.ImpresoraNoDisponible as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=503)
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f"No se pudo imprimir: {exc}"},
                            status=500)

    copias = _copias(datos)
    aviso = '' if estado == 0 else f" (la impresora reporta estado {estado})"
    return JsonResponse({
        'ok': True,
        'mensaje': f"{copias} etiqueta(s) enviada(s) a {etiquetas_zpl.IMPRESORA}{aviso}.",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Etiquetas del sistema
#
# Estas son las rutas que ya existían. Antes dibujaban un diseño fijo escrito en
# reportlab; ahora renderizan la plantilla marcada como predeterminada, así que
# lo que el usuario arma en el diseñador es lo que sale por todos lados.
# ─────────────────────────────────────────────────────────────────────────────

class SinPlantilla(Exception):
    """No hay ninguna plantilla cargada con la que renderizar."""


def _plantilla_activa():
    plantilla = PlantillaEtiqueta.predeterminada()
    if plantilla is None:
        raise SinPlantilla()
    return plantilla


def _pdf(lote, nombre_archivo, plantilla=None):
    """Genera el PDF de un lote.

    Sin `plantilla` usa la predeterminada, que es lo correcto para las
    etiquetas reales del sistema: se imprimen con el diseño activo, no con uno
    elegido a mano. Se pasa explícita solo para previsualizar UNA plantilla
    concreta desde el listado.
    """
    if plantilla is None:
        plantilla = _plantilla_activa()
    pdf = etiquetas_pdf.render(
        plantilla.elementos,
        ancho=plantilla.ancho_puntos,
        alto=plantilla.alto_puntos,
        lote=lote,
    )
    respuesta = HttpResponse(pdf, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="{nombre_archivo}"'
    return respuesta


def _sin_plantilla(request):
    messages.error(
        request,
        "No hay ninguna plantilla de etiqueta cargada. Creá una en el diseñador."
    )
    return redirect('lista_plantillas')


@login_required
def etiqueta_item_pdf(request, id):
    """Etiqueta de UNA unidad física de inventario (PrendaItem)."""
    item = get_object_or_404(
        PrendaItem.objects.select_related('prenda', 'ubicacion'), id=id
    )
    try:
        return _pdf([etiquetas.datos_de_item(item)], f"etiqueta_{item.codigo_item}.pdf")
    except SinPlantilla:
        return _sin_plantilla(request)


@login_required
def etiquetas_prenda_pdf(request, id):
    """Etiquetas de TODAS las unidades activas de un SKU, una por página.

    Es el caso de dar de alta inventario nuevo: se imprimen las diez de una vez
    y cada una lleva su propio código de unidad.
    """
    prenda = get_object_or_404(PrendaInventario, id=id)
    items = list(
        prenda.items.exclude(estado='baja')
                    .select_related('prenda', 'ubicacion')
                    .order_by('codigo_item')
    )
    if not items:
        messages.error(request, "No hay unidades activas para generar etiquetas.")
        return redirect('detalle_prenda', id=prenda.id)

    try:
        return _pdf([etiquetas.datos_de_item(it) for it in items],
                    f"etiquetas_{prenda.codigo}.pdf")
    except SinPlantilla:
        return _sin_plantilla(request)


@login_required
def etiqueta_reparacion_pdf(request, id):
    from .models import Reparacion
    reparacion = get_object_or_404(Reparacion.objects.select_related('cliente'), id=id)
    try:
        return _pdf([etiquetas.datos_de_servicio(reparacion, 'REPARACIÓN')],
                    f"etiqueta_{reparacion.codigo}.pdf")
    except SinPlantilla:
        return _sin_plantilla(request)


@login_required
def etiqueta_confeccion_pdf(request, id):
    from .models import Confeccion
    confeccion = get_object_or_404(Confeccion.objects.select_related('cliente'), id=id)
    try:
        return _pdf([etiquetas.datos_de_servicio(confeccion, 'CONFECCIÓN')],
                    f"etiqueta_{confeccion.codigo}.pdf")
    except SinPlantilla:
        return _sin_plantilla(request)


@login_required
def etiqueta_demo_pdf(request, id=None):
    """Etiqueta de muestra con datos ficticios.

    Con `id` previsualiza ESA plantilla — es el botón "Ver muestra" de cada
    fila del listado, donde lo que se quiere ver es el diseño de esa fila.
    Sin `id` usa la predeterminada, que es lo que necesita la pantalla de
    calibración: ahí se compara el diseño activo contra el rollo físico.
    """
    plantilla = None
    if id is not None:
        plantilla = get_object_or_404(PlantillaEtiqueta, pk=id)
    try:
        return _pdf([etiquetas.datos_muestra()], "etiqueta_muestra.pdf", plantilla)
    except SinPlantilla:
        return _sin_plantilla(request)


@login_required
def calibrar(request):
    """Página de calibración: comparar el diseño contra el rollo físico.

    Sigue existiendo porque medir el rollo es un problema aparte de diseñar la
    etiqueta: el usuario imprime la muestra, la superpone al sticker y, si no
    calza, cambia el tamaño desde acá sin tener que entrar al diseñador.
    """
    plantilla = PlantillaEtiqueta.predeterminada()
    return render(request, 'misastreria/etiquetas/calibrar.html', {
        'plantilla': plantilla,
        'config': ConfiguracionImpresora.cargar(),
    })


@login_required
def zpl_calibracion(request):
    """El comando de calibración, para que el puente se lo mande a la impresora.

    Va por acá y no escrito en el JavaScript para que el conocimiento de ZPL
    siga viviendo en un solo lugar del código.
    """
    return JsonResponse({'ok': True, 'zpl': etiquetas_zpl.ZPL_CALIBRAR})


@login_required
@require_POST
def fijar_impresora(request):
    """Guarda oscuridad, velocidad, encuadre y tipo de papel del cabezal.

    Se llama desde dos lados: la pantalla suelta de impresora, que postea un
    formulario normal y espera un redirect, y el modal del diseñador, que
    postea por fetch. El modal NO puede recargar la página: se llevaría puesto
    el diseño que el usuario todavía no guardó. Por eso, cuando el pedido viene
    por AJAX, se contesta JSON y la pantalla se queda donde está.
    """
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def fallar(mensaje):
        if ajax:
            return JsonResponse({'ok': False, 'error': mensaje}, status=400)
        messages.error(request, mensaje)
        return redirect('etiquetas_calibrar')

    config = ConfiguracionImpresora.cargar()

    try:
        config.oscuridad = int(request.POST.get('oscuridad') or 0)
        config.velocidad = int(request.POST.get('velocidad') or 4)
        config.desplazamiento_x = Decimal(request.POST.get('desplazamiento_x') or '0')
        config.desplazamiento_y = Decimal(request.POST.get('desplazamiento_y') or '0')
    except (TypeError, ValueError, InvalidOperation):
        return fallar("Los ajustes tienen que ser números.")

    config.usa_ribbon = bool(request.POST.get('usa_ribbon'))
    config.tipo_papel = (request.POST.get('tipo_papel') or '').strip()

    try:
        config.full_clean()
    except ValidationError as exc:
        return fallar(' '.join(
            f"{campo}: {' '.join(errores)}"
            for campo, errores in exc.message_dict.items()
        ))

    config.save()
    mensaje = f"Impresora ajustada: {config}. Imprimí una muestra para ver cómo quedó."

    if ajax:
        return JsonResponse({'ok': True, 'mensaje': mensaje})

    messages.success(request, mensaje)
    return redirect('etiquetas_calibrar')
