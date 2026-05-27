from .settings import *

# ── Servidor de testing: sastreria.oliviodev.com ─────────────────────────────
# Crea la BD en cPanel y reemplaza los valores marcados con TODO.

ALLOWED_HOSTS = ['sastreria.oliviodev.com', 'www.sastreria.oliviodev.com', 'localhost']

CSRF_TRUSTED_ORIGINS = [
    'https://sastreria.oliviodev.com',
    'https://www.sastreria.oliviodev.com',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'olivzdaj_sastreria',
        'USER': 'olivzdaj_sastreria',
        'PASSWORD': 'Olivio_1212',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# El app corre en la raíz del subdominio (sin prefijo /sistema)
FORCE_SCRIPT_NAME = ''
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
