"""
Django settings for proj project.

Generated by 'django-admin startproject' using Django 3.0.5.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import dj_database_url
import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '=d#m@3-878v0(s)pq6+ar52amg8+d(j&t_xl4y57eb@racaqqa'

ENVIRONMENT = os.environ.get('ENVIRONMENT', default='local')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = int(os.environ.get('DEBUG', default=1))

ALLOWED_HOSTS = ['.herokuapp.com', 'localhost', '127.0.0.1']

INTERNAL_IPS = [
    '127.0.0.1',
]

# Application definition

INSTALLED_APPS = [
    # native
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.forms',
    'django.contrib.postgres',

    # third party
    'crispy_forms',
    # 'debug_toolbar',
    # custom widgets will slow down page loads massively
    'django_extensions',
    'drf_yasg',
    'mptt',
    'simple_history',
    'tempus_dominus',

    # ours
    'accountancy',
    'cashbook.apps.CashbookConfig',
    'contacts.apps.ContactsConfig',
    'dashboard',
    'nominals.apps.NominalsConfig',
    'purchases.apps.PurchasesConfig',
    'sales.apps.SalesConfig',
    'controls.apps.ControlsConfig',
    'users.apps.UsersConfig',
    'vat.apps.VatConfig'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # 'debug_toolbar.middleware.DebugToolbarMiddleware',
    # debug toolbar causes custom widgets to load really slowly !!!
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accountancy.middleware.RestrictAdminToStaffMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
]

ROOT_URLCONF = 'proj.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, "templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

CRISPY_ALLOWED_TEMPLATE_PACKS = (
    'bootstrap',
    'uni_form',
    'bootstrap3',
    'bootstrap4',
    'accounts'
)

CRISPY_TEMPLATE_PACK = 'accounts'

WSGI_APPLICATION = 'proj.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'dspace',  # maps to the POSTGRES POSTGRES_DB ENV
        'USER': 'dspace',  # maps to the POSTGRES POSTGRES_USER ENV
        'PASSWORD': 'dspace',  # maps to the POSTGRES POSTGRES_PASSWORD ENV
        'HOST': '127.0.0.1',  # maps to the POSTGRES DB SERVICE NAME IN DOCKER
        'PORT': 5432,
        'ATOMIC_REQUESTS': True
    }
}

db_from_env = dj_database_url.config(conn_max_age=500)
# db_from_env is empty without heroku config vars
# so database default setting does not update
DATABASES['default'].update(db_from_env)

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = False
# GMT is the default time zone.  Format is YYYY-MM-DD
# User should be able to select their timezone
# With this set django will out of the box format it correctly

USE_TZ = True

DATE_INPUT_FORMATS = ['%d-%m-%Y']
DATE_FORMAT = 'd-m-Y'

LOGIN_URL = '/users/signin'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/users/signin'

# EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"
EMAIL_BACKEND = "users.backends.CustomEmailBackend"
DEFAULT_FROM_EMAIL = "you@example.com"
# the email address that error messages come from, such as those sent to ADMINS and MANAGERS
SERVER_EMAIL = "your-server@example.com"

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static'), ]

DEFAULT_VAT_NOMINAL = "Vat"
DEFAULT_SYSTEM_SUSPENSE = "System Suspense Account"

# This dictionary is used for NL and CB and VT tran enquiries
# so the user can click on a transaction and view it
# Also for permissions
ACCOUNTANCY_MODULES = {
    "PL": "purchases",
    "NL": "nominals",
    "SL": "sales",
    'CB': 'cashbook',
    'VL': 'vat'
}

NEW_USERS_ARE_SUPERUSERS = int(os.environ.get('NEW_USERS_ARE_SUPERUSERS', default=0))
FIRST_USER_IS_SUPERUSER = int(os.environ.get('FIRST_USER_IS_SUPERUSER', default=1))

# production
if ENVIRONMENT == 'production' and DEBUG == 0:
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True # include a header which bans the browsing from guessing the file type i.e. rely on the content type in the server response for file type
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')