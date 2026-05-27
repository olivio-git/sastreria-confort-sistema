import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sastreria.settings_testing')
django.setup()

from django.contrib.auth.models import User

username = 'admin'
password = 'Admin_1212'
email = 'admin@oliviodev.com'

if User.objects.filter(username=username).exists():
    u = User.objects.get(username=username)
    u.set_password(password)
    u.is_superuser = True
    u.is_staff = True
    u.save()
    print(f'Password actualizado para {username}')
else:
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f'Superusuario {username} creado')
