"""Limpieza de extras robusta tras el commit (verify ronda 7, S4)."""
import logging
from datetime import date
from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.db import OperationalError, connection
from django.test import TestCase
from django.urls import reverse

from misastreria import views_usuarios
from misastreria.forms import EmpleadoForm
from misastreria.models import Empleado, es_ultimo_administrador_activo

from .factories import (
    make_administrador, make_cajero, make_empleado, make_vendedor,
)


class S4ExtrasRobustosTests(TestCase):
    def test_on_commit_es_robusto_y_registra_el_error(self):
        from misastreria import extras_signals
        v = make_vendedor()
        with mock.patch('django.db.transaction.on_commit') as oc:
            extras_signals._limpiar_al_confirmar([v.pk])
        self.assertTrue(oc.call_args.kwargs.get('robust'))
        callback = oc.call_args.args[0]
        otro = make_vendedor(username='v2')
        with mock.patch.object(extras_signals, 'limpiar_extras_si_sin_rol',
                               side_effect=[RuntimeError('boom'), None]) as lim:
            with self.assertLogs('misastreria.extras_signals', level='ERROR') as cm:
                extras_signals._limpiar_al_confirmar([v.pk, otro.pk])
                with mock.patch('django.db.transaction.on_commit',
                                side_effect=lambda f, **k: f()):
                    extras_signals._limpiar_al_confirmar([v.pk, otro.pk])
        self.assertTrue(any('boom' in line for line in cm.output))
        self.assertEqual(lim.call_count, 2)  # el segundo usuario se procesó igual
