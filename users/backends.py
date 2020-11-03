from threading import Thread

from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

"""
Sometimes we don't control the code which calls send_email so we have no choice but to subclass the default email backend
and ensure the email is sent via a new thread.  This is important so we don't delay the response to the user.
"""

def send_emails(email_messages):
    conn = get_connection(backend='anymail.backends.mailgun.EmailBackend')
    conn.send_messages(email_messages)

class CustomEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        t = Thread(target=send_emails, args=[email_messages])
        t.start()
        return len(email_messages)
