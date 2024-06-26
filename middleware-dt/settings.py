from .settings_base import *

SECRET_KEY = '=-er@_tdj*j=1#j=225a*&%7uy=j8xqfju%^!*@r6x!d__k_+n'

ALLOWED_HOSTS = []

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'middlewaredt',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}