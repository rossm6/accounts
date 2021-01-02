from django.test import TestCase
from users.forms import SignUpForm
from mock import mock


class SignUpFormTests(TestCase):

    @mock.patch('users.forms.get_user_model')
    @mock.patch('users.forms.settings')
    def test_second_user_not_superuser(self, mocked_settings, mocked_get_user_model):
        mocked_settings.configure_mock(**{"NEW_USERS_ARE_SUPERUSERS": False})
        attrs = {
            'objects.first.return_value': True
        }
        user_model = mock.Mock(**attrs)
        mocked_get_user_model.return_value = user_model
        f = SignUpForm(
            data={
                'username': "dave",
                'password1': "Test123!",
                'password2': "Test123!"
            }
        )
        u = f.save()
        self.assertFalse(u.is_superuser)
        self.assertFalse(u.is_staff)

    @mock.patch('users.forms.settings')
    def test_first_user_not_superuser(self, mocked_settings):
        mocked_settings.configure_mock(
            **{
                "NEW_USERS_ARE_SUPERUSERS": False,
                "FIRST_USER_IS_SUPERUSER": False
            }
        )
        f = SignUpForm(
            data={
                'username': "dave",
                'password1': "Test123!",
                'password2': "Test123!"
            }
        )
        u = f.save()
        self.assertFalse(u.is_superuser)
        self.assertFalse(u.is_staff)

    @mock.patch('users.forms.settings')
    def test_second_user_is_superuser(self, mocked_settings):
        mocked_settings.configure_mock(
            **{
                "NEW_USERS_ARE_SUPERUSERS": True,
            }
        )
        f = SignUpForm(
            data={
                'username': "dave",
                'password1': "Test123!",
                'password2': "Test123!"
            }
        )
        u = f.save()
        self.assertTrue(u.is_superuser)
        self.assertFalse(u.is_staff)

    @mock.patch('users.forms.get_user_model')
    @mock.patch('users.forms.settings')
    def test_first_user_is_superuser(self, mocked_settings, mocked_get_user_model):
        mocked_settings.configure_mock(
            **{
                "NEW_USERS_ARE_SUPERUSERS": False, # irrelevant
                "FIRST_USER_IS_SUPERUSER": True
            }
        )
        attrs = {
            'objects.first.return_value': False
        }
        user_model = mock.Mock(**attrs)
        mocked_get_user_model.return_value = user_model
        f = SignUpForm(
            data={
                'username': "dave",
                'password1': "Test123!",
                'password2': "Test123!"
            }
        )
        u = f.save()
        self.assertTrue(u.is_superuser)
        self.assertFalse(u.is_staff)