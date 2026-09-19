"""Cambiar una prenda del alquiler por otra unidad del mismo modelo.

El sistema adivina qué unidad sale —por desgaste o por antigüedad— pero quien
atiende agarra la que el cliente se probó. Lo físico manda.

Sin este cambio, `veces_alquilado` se acredita a la prenda anotada y no a la
que salió. Ese contador es la ÚNICA fuente de verdad sobre el desgaste: si se
desvía no hay con qué contrastarlo, y alimenta la vida útil y «Prendas próx.
baja». El resultado es retirar prendas nuevas y seguir alquilando las gastadas.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from misastreria.models import Alquiler, AlquilerItem, PrendaItem
from .factories import make_cliente, make_prenda, make_prenda_item, make_user


class CambiarUnidadHermanaTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user())
        self.frac = make_prenda(nombre='Frac', talla='50', color='Negro',
                                precio=Decimal('900.00'),
                                precio_alquiler_base=Decimal('250.00'))
        # la que el sistema anotó, y la que el cliente se probó de verdad
        self.anotada = make_prenda_item(self.frac, tipo='alquiler', estado='reservado')
        self.real = make_prenda_item(self.frac, tipo='alquiler', estado='disponible')
        # una de otro modelo, para probar el rechazo
        self.saco = make_prenda_item(make_prenda(nombre='Saco'), tipo='alquiler')

        self.alquiler = Alquiler.objects.create(
            cliente=make_cliente(), fecha_alquiler=date.today(),
            fecha_devolucion=date.today() + timedelta(days=3), estado='reservado')
        AlquilerItem.objects.create(alquiler=self.alquiler, prenda_item=self.anotada,
                                    precio_unitario=Decimal('250.00'))

    def _url(self):
        return reverse('cambiar_unidad_alquiler', args=[self.alquiler.id])

    def test_propone_el_cambio_sin_aplicarlo(self):
        d = self.client.get(self._url(), {'codigo': self.real.codigo_item}).json()
        self.assertTrue(d['ok'])
        self.assertEqual(d['propuesta']['desde']['prenda_item_id'], self.anotada.id)
        self.assertEqual(d['propuesta']['hacia']['prenda_item_id'], self.real.id)
        # GET no toca nada.
        self.assertEqual(self.alquiler.items.first().prenda_item_id, self.anotada.id)

    def test_el_post_aplica_el_cambio_y_mueve_los_estados(self):
        d = self.client.post(self._url(), {'codigo': self.real.codigo_item,
                                           'desde': self.anotada.id}).json()
        self.assertTrue(d['ok'])
        self.assertEqual(self.alquiler.items.first().prenda_item_id, self.real.id)

        self.anotada.refresh_from_db(); self.real.refresh_from_db()
        # La que entra hereda el estado de la que sale; la que sale se libera.
        self.assertEqual(self.real.estado, 'reservado')
        self.assertEqual(self.anotada.estado, 'disponible')

    def test_el_desgaste_se_acredita_a_la_prenda_que_salio(self):
        """La razón de ser de todo esto."""
        self.client.post(self._url(), {'codigo': self.real.codigo_item,
                                       'desde': self.anotada.id})
        self.client.post(reverse('confirmar_reserva', args=[self.alquiler.id]))
        self.client.post(reverse('devolver_alquiler', args=[self.alquiler.id]))

        self.anotada.refresh_from_db(); self.real.refresh_from_db()
        self.assertEqual(self.real.veces_alquilado, 1, 'la que salió no sumó uso')
        self.assertEqual(self.anotada.veces_alquilado, 0,
                         'le sumó uso a una prenda que nunca salió del local')

    def test_rechaza_una_prenda_de_otro_modelo(self):
        d = self.client.get(self._url(), {'codigo': self.saco.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'otro_modelo')

    def test_rechaza_una_unidad_que_esta_en_otro_lado(self):
        self.real.estado = 'alquilado'
        self.real.save(update_fields=['estado'])
        d = self.client.get(self._url(), {'codigo': self.real.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'ocupada')

    def test_rechaza_una_prenda_que_ya_esta_en_el_alquiler(self):
        d = self.client.get(self._url(), {'codigo': self.anotada.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'ya_esta')

    def test_rechaza_una_prenda_dada_de_baja(self):
        self.real.estado = 'baja'
        self.real.save(update_fields=['estado'])
        d = self.client.get(self._url(), {'codigo': self.real.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'baja')

    def test_codigo_inexistente(self):
        d = self.client.get(self._url(), {'codigo': 'NO-EXISTE-01'}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'no_existe')

    def test_con_dos_unidades_iguales_cambia_la_indicada(self):
        """Si el alquiler lleva dos fracs, `desde` decide cuál se sustituye."""
        otra = make_prenda_item(self.frac, tipo='alquiler', estado='reservado')
        AlquilerItem.objects.create(alquiler=self.alquiler, prenda_item=otra,
                                    precio_unitario=Decimal('250.00'))
        self.client.post(self._url(), {'codigo': self.real.codigo_item, 'desde': otra.id})

        ids = set(self.alquiler.items.values_list('prenda_item_id', flat=True))
        self.assertEqual(ids, {self.anotada.id, self.real.id})

    def test_las_pantallas_de_salida_y_devolucion_habilitan_el_cambio(self):
        # Cada pantalla exige su estado: salida pide 'reservado', devolución
        # 'alquilado' (con 'reservado' redirige a confirmar).
        for url, estado in (('confirmar_reserva', 'reservado'),
                            ('devolver_alquiler', 'alquilado')):
            Alquiler.objects.filter(pk=self.alquiler.pk).update(estado=estado)
            resp = self.client.get(reverse(url, args=[self.alquiler.id]))
            self.assertEqual(resp.status_code, 200, f'{url} no renderizó')
            html = resp.content.decode()
            self.assertIn('urlCambio', html, f'{url} no habilita el cambio')
            self.assertIn('data-item-id', html, f'{url} sin el id de la unidad')


class GuardasDelCambioTests(TestCase):
    """Hallazgos de la revisión: el cambio no puede pisar la prenda equivocada."""

    def setUp(self):
        self.client.force_login(make_user())
        self.frac = make_prenda(nombre='Frac', precio_alquiler_base=Decimal('250.00'))
        self.pantalon = make_prenda(nombre='Pantalón', precio_alquiler_base=Decimal('80.00'))
        self.f1 = make_prenda_item(self.frac, tipo='alquiler', estado='alquilado')
        self.p1 = make_prenda_item(self.pantalon, tipo='alquiler', estado='alquilado')
        self.hermana = make_prenda_item(self.frac, tipo='alquiler', estado='disponible')
        self.alquiler = Alquiler.objects.create(
            cliente=make_cliente(), fecha_alquiler=date.today(),
            fecha_devolucion=date.today() + timedelta(days=3), estado='alquilado')
        for it in (self.p1, self.f1):
            AlquilerItem.objects.create(alquiler=self.alquiler, prenda_item=it,
                                        precio_unitario=Decimal('100.00'))

    def _url(self):
        return reverse('cambiar_unidad_alquiler', args=[self.alquiler.id])

    def test_un_desde_de_otro_modelo_se_rechaza_en_vez_de_adivinar(self):
        """Antes caía en candidatos[0] y sustituía una unidad ya verificada."""
        d = self.client.post(self._url(), {'codigo': self.hermana.codigo_item,
                                           'desde': self.p1.id}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'desde_invalido')
        # y no tocó nada
        self.assertEqual(
            set(self.alquiler.items.values_list('prenda_item_id', flat=True)),
            {self.p1.id, self.f1.id})

    def test_la_propuesta_dice_de_que_modelo_es_la_prenda(self):
        """El navegador necesita el modelo para elegir la fila correcta."""
        d = self.client.get(self._url(), {'codigo': self.hermana.codigo_item}).json()
        self.assertEqual(d['propuesta']['hacia']['prenda_inventario_id'], self.frac.id)

    def test_el_kardex_sigue_a_la_prenda_que_realmente_salio(self):
        from misastreria.models import KardexEvento
        from misastreria import kardex_events
        kardex_events.emit_alquiler(self.f1, self.alquiler, Decimal('100'))
        self.assertTrue(KardexEvento.objects.filter(
            alquiler=self.alquiler, prenda_item=self.f1).exists())

        self.client.post(self._url(), {'codigo': self.hermana.codigo_item,
                                       'desde': self.f1.id})
        # El egreso se mueve: si no, la vieja queda con salida sin retorno y la
        # nueva con retorno sin salida.
        self.assertFalse(KardexEvento.objects.filter(
            alquiler=self.alquiler, prenda_item=self.f1).exists())
        self.assertTrue(KardexEvento.objects.filter(
            alquiler=self.alquiler, prenda_item=self.hermana).exists())

    def test_no_acepta_una_unidad_que_es_parte_de_un_conjunto(self):
        from misastreria.models import Conjunto, ConjuntoSlot
        conj = Conjunto.objects.create(nombre='Terno completo', tipo='alquiler')
        ConjuntoSlot.objects.create(conjunto=conj, prenda_item=self.hermana, orden=0)
        d = self.client.get(self._url(), {'codigo': self.hermana.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'conjunto')

    def test_no_acepta_una_unidad_de_un_modelo_archivado(self):
        self.frac.estado = 'BAJ'
        self.frac.save(update_fields=['estado'])
        d = self.client.get(self._url(), {'codigo': self.hermana.codigo_item}).json()
        self.assertFalse(d['ok'])
        self.assertEqual(d['motivo'], 'sku_baja')
