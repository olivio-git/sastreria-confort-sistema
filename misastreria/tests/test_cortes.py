"""
test_cortes.py — feature de "número de corte" (lote de tela).

Un corte es independiente del modelo de prenda: agrupa unidades (PrendaItem)
cortadas de un mismo rollo, sin importar a qué SKU pertenezcan. Se cubre:
  - numeración auto-incremental C-### y unicidad
  - normalización de la sigla
  - __str__
  - alta en lote (agregar_items_prenda) con corte existente / nuevo / ninguno
  - el formulario arranca en "sin corte" (antes sugería el último usado)
  - una sigla con forma de número de corte se rechaza
  - "Editar unidad" puede crear un corte nuevo
  - buscador de cortes para el selector
  - datos de etiqueta (corte / corte_sigla), vacíos cuando no hay corte
  - filtro de inventario por corte
  - PROTECT al borrar un corte con unidades asociadas
"""
from unittest import mock

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from misastreria import etiquetas
from misastreria.models import Corte, PrendaItem
from misastreria.tests.factories import make_corte, make_prenda, make_prenda_item, make_user


class NumeracionTests(TestCase):

    def test_primer_corte_es_c001(self):
        corte = make_corte()
        self.assertEqual(corte.numero, 'C-001')

    def test_numeros_son_correlativos(self):
        uno = make_corte()
        dos = make_corte()
        tres = make_corte()
        self.assertEqual([uno.numero, dos.numero, tres.numero], ['C-001', 'C-002', 'C-003'])

    def test_libera_el_numero_del_ultimo_borrado_sin_colisionar(self):
        # Al borrar el corte de mayor número, ese número queda libre y el
        # siguiente alta puede reutilizarlo sin chocar contra el `unique`
        # (la fila anterior ya no existe). Es lo que evita el criterio por
        # MÁXIMO numérico en vez de por el último `id`.
        make_corte()          # C-001
        dos = make_corte()    # C-002
        dos.delete()
        tres = make_corte()
        self.assertEqual(tres.numero, 'C-002')

    def test_calcula_por_maximo_numerico_y_no_por_ultimo_id(self):
        # Si se crea un corte con un número manual fuera de secuencia, el
        # criterio por máximo sigue dando el correlativo correcto — al
        # revés de `order_by('-id').first()`, que fallaría si el último
        # creado no fuera el de mayor número.
        make_corte()                              # C-001
        Corte.objects.create(numero='C-050')       # numero manual, fuera de secuencia
        siguiente = make_corte()
        self.assertEqual(siguiente.numero, 'C-051')

    def test_numero_explicito_no_se_pisa(self):
        corte = Corte.objects.create(numero='C-900')
        self.assertEqual(corte.numero, 'C-900')

    def test_numero_es_unico(self):
        make_corte()
        with self.assertRaises(Exception):
            Corte.objects.create(numero='C-001')


class SiglaYStrTests(TestCase):

    def test_sigla_se_normaliza_mayusculas_y_sin_espacios(self):
        corte = make_corte(sigla='  azul-lana  ')
        self.assertEqual(corte.sigla, 'AZUL-LANA')

    def test_str_con_sigla(self):
        corte = make_corte(sigla='azul-lana')
        self.assertEqual(str(corte), f'{corte.numero} · AZUL-LANA')

    def test_str_sin_sigla(self):
        corte = make_corte()
        self.assertEqual(str(corte), corte.numero)


class MasRecienteUsadoTests(TestCase):

    def test_sin_cortes_ni_items_devuelve_none(self):
        self.assertIsNone(Corte.mas_reciente_usado())

    def test_sin_items_con_corte_devuelve_el_corte_mas_nuevo(self):
        make_corte()
        mas_nuevo = make_corte()
        self.assertEqual(Corte.mas_reciente_usado(), mas_nuevo)

    def test_devuelve_el_corte_de_la_unidad_mas_nueva(self):
        prenda = make_prenda()
        corte_viejo = make_corte()
        corte_nuevo = make_corte()
        make_prenda_item(prenda=prenda, corte=corte_viejo)
        ultimo_item = make_prenda_item(prenda=prenda, corte=corte_nuevo)
        self.assertEqual(Corte.mas_reciente_usado(), corte_nuevo)
        # y no cambia si después se crea un corte que ninguna unidad usa aún
        make_corte()
        self.assertEqual(Corte.mas_reciente_usado(), corte_nuevo)
        self.assertIsNotNone(ultimo_item.corte)


class AgregarItemsPrendaTests(TestCase):

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)
        self.prenda = make_prenda()

    def _post(self, follow=False, **data):
        payload = dict(cantidad=2, tipo='alquiler', condicion='nueva')
        payload.update(data)
        return self.client.post(
            reverse('agregar_items_prenda', args=[self.prenda.id]), payload, follow=follow,
        )

    def test_modo_ninguno_no_asigna_corte(self):
        resp = self._post(corte_modo='ninguno')
        self.assertEqual(resp.status_code, 302)
        items = PrendaItem.objects.filter(prenda=self.prenda)
        self.assertEqual(items.count(), 2)
        self.assertTrue(all(i.corte_id is None for i in items))

    def test_modo_existente_asigna_el_corte_elegido(self):
        corte = make_corte()
        resp = self._post(corte_modo='existente', corte=corte.id)
        self.assertEqual(resp.status_code, 302)
        items = PrendaItem.objects.filter(prenda=self.prenda)
        self.assertEqual(items.count(), 2)
        self.assertTrue(all(i.corte_id == corte.id for i in items))

    def test_mensaje_de_exito_menciona_el_corte(self):
        corte = make_corte()
        resp = self._post(corte_modo='existente', corte=corte.id, follow=True)
        self.assertContains(resp, corte.numero)

    def test_modo_nuevo_crea_el_siguiente_corte_y_lo_asigna_a_todos(self):
        antes = Corte.objects.count()
        resp = self._post(
            corte_modo='nuevo', nuevo_corte_sigla='azul-lana', nuevo_corte_tela='Casimir azul',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Corte.objects.count(), antes + 1)
        nuevo = Corte.objects.order_by('-creado').first()
        self.assertEqual(nuevo.sigla, 'AZUL-LANA')
        self.assertEqual(nuevo.tela, 'Casimir azul')
        items = PrendaItem.objects.filter(prenda=self.prenda)
        self.assertEqual(items.count(), 2)
        self.assertTrue(all(i.corte_id == nuevo.id for i in items))

    def test_todas_las_unidades_del_lote_comparten_el_mismo_corte(self):
        resp = self._post(cantidad=5, corte_modo='nuevo')
        self.assertEqual(resp.status_code, 302)
        items = list(PrendaItem.objects.filter(prenda=self.prenda))
        self.assertEqual(len(items), 5)
        cortes_usados = {i.corte_id for i in items}
        self.assertEqual(len(cortes_usados), 1)

    def test_corte_invalido_en_modo_existente_deja_sin_corte(self):
        resp = self._post(corte_modo='existente', corte='9999')
        self.assertEqual(resp.status_code, 302)
        items = PrendaItem.objects.filter(prenda=self.prenda)
        self.assertTrue(all(i.corte_id is None for i in items))

    def test_el_formulario_arranca_sin_corte(self):
        """Antes venía preseleccionado el último corte usado.

        Así terminaron 13 prendas —corbatas, camisas, sacos, zapatos— en el
        mismo corte: nadie lo eligió, lo heredaron. Con «sin corte» por
        defecto, no mirar deja el campo vacío, que es el error barato.
        """
        make_prenda_item(prenda=make_prenda(nombre='Pantalón'), corte=make_corte())
        html = self.client.get(
            reverse('detalle_prenda', args=[self.prenda.id])).content.decode()
        self.assertIn('id="agr_corte_picker"', html)
        bloque = html[html.index('id="agr_corte_picker"'):]
        bloque = bloque[:bloque.index('data-corte-abrir')]
        self.assertIn('name="corte_modo" value="ninguno"', bloque)
        self.assertIn('name="corte" value=""', bloque)

    def test_sigla_con_forma_de_numero_no_crea_nada(self):
        resp = self._post(corte_modo='nuevo', nuevo_corte_sigla='C-002', follow=True)
        self.assertContains(resp, 'parece un número de corte')
        self.assertFalse(Corte.objects.exists(), 'no tenía que crear el corte')
        self.assertFalse(PrendaItem.objects.filter(prenda=self.prenda).exists(),
                         'no tenía que crear las unidades')


class EditarCorteDeUnidadTests(TestCase):

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)
        self.item = make_prenda_item()

    def test_asigna_corte_a_una_unidad_existente(self):
        corte = make_corte()
        resp = self.client.post(reverse('editar_prenda_item', args=[self.item.id]), {
            'condicion': 'nueva', 'tipo': 'alquiler', 'corte': corte.id,
        })
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.corte_id, corte.id)

    def test_quitar_corte_dejando_el_select_vacio(self):
        corte = make_corte()
        self.item.corte = corte
        self.item.save(update_fields=['corte'])
        resp = self.client.post(reverse('editar_prenda_item', args=[self.item.id]), {
            'condicion': 'nueva', 'tipo': 'alquiler', 'corte': '',
        })
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.corte_id)


class EtiquetaDatosCorteTests(TestCase):

    def test_item_con_corte_expone_numero_y_sigla(self):
        corte = make_corte(sigla='azul-lana')
        item = make_prenda_item(corte=corte)
        datos = etiquetas.datos_de_item(item)
        self.assertEqual(datos['corte'], corte.numero)
        self.assertEqual(datos['corte_sigla'], 'AZUL-LANA')

    def test_item_sin_corte_expone_vacio(self):
        item = make_prenda_item()
        datos = etiquetas.datos_de_item(item)
        self.assertEqual(datos['corte'], '')
        self.assertEqual(datos['corte_sigla'], '')

    def test_prenda_y_servicio_no_traen_corte(self):
        prenda = make_prenda()
        datos = etiquetas.datos_de_prenda(prenda)
        self.assertEqual(datos['corte'], '')
        self.assertEqual(datos['corte_sigla'], '')

    def test_campos_catalogo_incluye_corte(self):
        self.assertIn('corte', etiquetas.CAMPOS)
        self.assertIn('corte_sigla', etiquetas.CAMPOS)

    def test_sustitucion_de_marcador_corte_en_texto(self):
        corte = make_corte(sigla='azul-lana')
        item = make_prenda_item(corte=corte)
        datos = etiquetas.datos_de_item(item)
        texto = etiquetas.sustituir('Corte {corte} ({corte_sigla})', datos)
        self.assertEqual(texto, f'Corte {corte.numero} (AZUL-LANA)')


class FiltroInventarioPorCorteTests(TestCase):

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)

    def test_filtra_prendas_que_tienen_al_menos_una_unidad_del_corte(self):
        corte_a = make_corte()
        corte_b = make_corte()
        prenda_a = make_prenda(nombre='Terno A')
        prenda_b = make_prenda(nombre='Terno B')
        make_prenda_item(prenda=prenda_a, corte=corte_a)
        make_prenda_item(prenda=prenda_b, corte=corte_b)

        resp = self.client.get(reverse('lista_prendas'), {'corte': corte_a.id})
        self.assertEqual(resp.status_code, 200)
        codigos = [p.codigo for p in resp.context['page_obj']]
        self.assertIn(prenda_a.codigo, codigos)
        self.assertNotIn(prenda_b.codigo, codigos)

    def test_sin_filtro_muestra_todo(self):
        make_prenda(nombre='Sin corte')
        resp = self.client.get(reverse('lista_prendas'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['corte'], '')


class ProtectAlBorrarTests(TestCase):

    def test_no_se_puede_borrar_un_corte_con_unidades(self):
        corte = make_corte()
        make_prenda_item(corte=corte)
        with self.assertRaises(ProtectedError):
            corte.delete()

    def test_se_puede_borrar_un_corte_sin_unidades(self):
        corte = make_corte()
        corte.delete()
        self.assertFalse(Corte.objects.filter(pk=corte.pk).exists())


class ConteosConFiltroPorItemsTests(TestCase):
    """Los filtros por corte/tipo no deben multiplicar los conteos anotados
    (stock_total, etc.) al agregar un segundo JOIN a PrendaItem."""

    def setUp(self):
        self.usuario = make_user()
        self.client.force_login(self.usuario)

    def _prenda_en_lista(self, resp, prenda):
        return next(p for p in resp.context['page_obj'] if p.id == prenda.id)

    def test_filtro_por_corte_no_multiplica_el_stock(self):
        corte = make_corte()
        prenda = make_prenda(nombre='Terno lote')
        for _ in range(10):
            make_prenda_item(prenda=prenda, corte=corte)

        resp = self.client.get(reverse('lista_prendas'), {'corte': corte.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total'], 1)
        p = self._prenda_en_lista(resp, prenda)
        self.assertEqual(p.stock_total, 10)
        self.assertEqual(p._stock_disponible, 10)
        self.assertEqual(p.items_alquiler, 10)
        self.assertEqual(p.items_venta, 0)

    def test_filtro_por_corte_cuenta_tambien_unidades_de_otros_cortes(self):
        corte_a = make_corte()
        corte_b = make_corte()
        prenda = make_prenda(nombre='Terno mixto')
        for _ in range(3):
            make_prenda_item(prenda=prenda, corte=corte_a)
        for _ in range(2):
            make_prenda_item(prenda=prenda, corte=corte_b)

        resp = self.client.get(reverse('lista_prendas'), {'corte': corte_a.id})
        p = self._prenda_en_lista(resp, prenda)
        self.assertEqual(p.stock_total, 5)

    def test_filtro_por_tipo_no_multiplica_el_stock(self):
        prenda = make_prenda(nombre='Terno tipos')
        for _ in range(4):
            make_prenda_item(prenda=prenda, tipo='alquiler')
        for _ in range(3):
            make_prenda_item(prenda=prenda, tipo='venta')

        resp = self.client.get(reverse('lista_prendas'), {'tipo': 'venta'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total'], 1)
        p = self._prenda_en_lista(resp, prenda)
        self.assertEqual(p.stock_total, 7)
        self.assertEqual(p.items_alquiler, 4)
        self.assertEqual(p.items_venta, 3)

    def test_filtro_por_tipo_excluye_prendas_sin_ese_tipo(self):
        solo_alquiler = make_prenda(nombre='Solo alquiler')
        make_prenda_item(prenda=solo_alquiler, tipo='alquiler')
        resp = self.client.get(reverse('lista_prendas'), {'tipo': 'venta'})
        ids = [p.id for p in resp.context['page_obj']]
        self.assertNotIn(solo_alquiler.id, ids)

    def test_corte_no_numerico_se_ignora(self):
        make_prenda(nombre='Cualquiera')
        resp = self.client.get(reverse('lista_prendas'), {'corte': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['corte'], '')


class ColisionDeNumeroTests(TestCase):
    """Dos altas concurrentes pueden calcular el mismo C-NNN; save() reintenta."""

    def test_reintenta_con_el_siguiente_numero_si_colisiona(self):
        make_corte()  # C-001
        # Simula la carrera: el primer cálculo devuelve un número ya tomado.
        original = Corte.siguiente_numero.__func__
        llamadas = []

        def fake(cls):
            llamadas.append(1)
            return 'C-001' if len(llamadas) == 1 else original(cls)

        with mock.patch.object(Corte, 'siguiente_numero', classmethod(fake)):
            corte = Corte.objects.create(sigla='x')
        self.assertEqual(corte.numero, 'C-002')
        self.assertEqual(len(llamadas), 2)

    def test_reintento_deja_usable_la_transaccion_externa(self):
        make_corte()  # C-001
        original = Corte.siguiente_numero.__func__
        llamadas = []

        def fake(cls):
            llamadas.append(1)
            return 'C-001' if len(llamadas) == 1 else original(cls)

        with transaction.atomic():
            with mock.patch.object(Corte, 'siguiente_numero', classmethod(fake)):
                corte = Corte.objects.create()
            make_prenda_item(corte=corte)
        self.assertEqual(corte.numero, 'C-002')
        self.assertEqual(PrendaItem.objects.filter(corte=corte).count(), 1)

    def test_agota_reintentos_y_propaga_el_error(self):
        make_corte()  # C-001
        with mock.patch.object(Corte, 'siguiente_numero', classmethod(lambda cls: 'C-001')):
            with self.assertRaises(IntegrityError):
                Corte.objects.create()


class RecorteDeLongitudTests(TestCase):
    """MySQL strict tira DataError si se excede max_length: save() recorta."""

    def test_sigla_y_tela_largas_se_recortan(self):
        corte = Corte.objects.create(sigla='  ' + 'a' * 30 + '  ', tela='t' * 250)
        corte.refresh_from_db()
        self.assertEqual(corte.sigla, 'A' * 12)
        self.assertEqual(corte.tela, 't' * 100)

    def test_recorta_despues_de_upper(self):
        # 'ß'.upper() == 'SS': recortar antes de upper() dejaría 13+ chars.
        corte = Corte.objects.create(sigla='ß' * 12)
        self.assertEqual(corte.sigla, 'S' * 12)

    def test_alta_desde_agregar_items_con_valores_largos(self):
        usuario = make_user()
        self.client.force_login(usuario)
        prenda = make_prenda()
        resp = self.client.post(
            reverse('agregar_items_prenda', args=[prenda.id]),
            dict(cantidad=1, tipo='alquiler', condicion='nueva', corte_modo='nuevo',
                 nuevo_corte_sigla='x' * 40, nuevo_corte_tela='y' * 300),
        )
        self.assertEqual(resp.status_code, 302)
        corte = PrendaItem.objects.get(prenda=prenda).corte
        self.assertEqual(corte.sigla, 'X' * 12)
        self.assertEqual(corte.tela, 'y' * 100)


class SiglaConFormaDeNumeroTests(TestCase):
    """«C-001 · C-002»: la secretaria escribió el número en la casilla de la sigla."""

    def test_detecta_las_variantes(self):
        for sigla in ('C-002', 'c-002', 'C002', 'c2', 'C 2', ' C-10 '):
            with self.subTest(sigla=sigla):
                self.assertTrue(Corte.sigla_parece_numero(sigla))

    def test_deja_pasar_siglas_normales(self):
        for sigla in ('', 'AZUL-LANA', 'SG12', 'CASIMIR', 'C-AZUL', '12', 'CUELLO2'):
            with self.subTest(sigla=sigla):
                self.assertFalse(Corte.sigla_parece_numero(sigla))

    def test_clean_la_rechaza(self):
        from django.core.exceptions import ValidationError
        corte = Corte(sigla='C-002')
        with self.assertRaises(ValidationError):
            corte.full_clean(exclude=['numero'])


class EditarUnidadCreaCorteTests(TestCase):
    """Desde «Editar unidad» ahora se puede crear un corte, no sólo elegirlo."""

    def setUp(self):
        self.client.force_login(make_user())
        self.item = make_prenda_item()

    def _post(self, **data):
        payload = {'condicion': 'nueva', 'tipo': 'alquiler'}
        payload.update(data)
        return self.client.post(
            reverse('editar_prenda_item', args=[self.item.id]), payload, follow=True)

    def test_crea_el_siguiente_corte_y_lo_asigna(self):
        make_corte()  # C-001 ya existe
        self._post(corte_modo='nuevo', nuevo_corte_sigla='azul-lana',
                   nuevo_corte_tela='Casimir azul')
        self.item.refresh_from_db()
        self.assertEqual(self.item.corte.numero, 'C-002')
        self.assertEqual(self.item.corte.sigla, 'AZUL-LANA')
        self.assertEqual(self.item.corte.tela, 'Casimir azul')

    def test_sigla_con_forma_de_numero_no_guarda_nada(self):
        self.item.notas = 'antes'
        self.item.save(update_fields=['notas'])
        resp = self._post(corte_modo='nuevo', nuevo_corte_sigla='C-002', notas='después')
        self.assertContains(resp, 'parece un número de corte')
        self.item.refresh_from_db()
        self.assertIsNone(self.item.corte_id)
        self.assertEqual(self.item.notas, 'antes', 'no tenía que guardar la edición')
        self.assertFalse(Corte.objects.exists())

    def test_modo_existente(self):
        corte = make_corte()
        self._post(corte_modo='existente', corte=corte.id)
        self.item.refresh_from_db()
        self.assertEqual(self.item.corte_id, corte.id)

    def test_modo_ninguno_quita_el_corte(self):
        self.item.corte = make_corte()
        self.item.save(update_fields=['corte'])
        self._post(corte_modo='ninguno', corte='')
        self.item.refresh_from_db()
        self.assertIsNone(self.item.corte_id)


class BuscarCortesTests(TestCase):

    def setUp(self):
        self.client.force_login(make_user())

    def _get(self, q=''):
        return self.client.get(reverse('buscar_cortes'), {'q': q}).json()

    def test_devuelve_los_mas_nuevos_primero_con_sus_unidades(self):
        viejo = make_corte(sigla='AZUL')
        nuevo = make_corte(sigla='BEIGE')
        make_prenda_item(corte=nuevo)
        make_prenda_item(corte=nuevo)
        data = self._get()
        self.assertEqual([c['numero'] for c in data['resultados']],
                         [nuevo.numero, viejo.numero])
        self.assertEqual(data['resultados'][0]['unidades'], 2)
        self.assertEqual(data['resultados'][1]['unidades'], 0)

    def test_busca_por_numero_sigla_y_tela(self):
        make_corte(sigla='AZUL', tela='Casimir')
        make_corte(sigla='BEIGE', tela='Lino')
        self.assertEqual(len(self._get('azul')['resultados']), 1)
        self.assertEqual(len(self._get('lino')['resultados']), 1)
        self.assertEqual(len(self._get('C-00')['resultados']), 2)

    def test_informa_el_numero_del_proximo_corte(self):
        make_corte()
        make_corte()
        self.assertEqual(self._get()['siguiente'], 'C-003')

    def test_avisa_cuando_hay_mas_de_los_que_muestra(self):
        for _ in range(31):
            make_corte()
        data = self._get()
        self.assertEqual(len(data['resultados']), 30)
        self.assertTrue(data['hay_mas'])

    def test_pide_login(self):
        self.client.logout()
        resp = self.client.get(reverse('buscar_cortes'))
        self.assertEqual(resp.status_code, 302)
