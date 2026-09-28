"""The email `NotificationChannel` (foundation.md §8 S4): dev = console backend, test =
locmem, prod = an Anymail ESP backend selected entirely by environment (`EMAIL_BACKEND`,
`ANYMAIL` in `config/settings/base.py`) — never a hard-coded provider choice here.
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from ham.integrations.channels import NotificationChannel


class DjangoEmailChannel:
    """Sends through Django's configured `EMAIL_BACKEND`.

    Never logs `to` (PRD §68): the address goes straight into Django's mail API and is not
    put into any log message or exception text this class raises. If a send fails, the
    exception message may echo Django/Anymail's own error text — do not add a `logger.*` call
    here without scrubbing it first (`ham.platform.logging.scrub`).
    """

    def send(
        self,
        *,
        to: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
        category: str,
    ) -> None:
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        if html_body:
            message.attach_alternative(html_body, "text/html")
        # Anymail reads a plain `.tags` attribute on any Django EmailMessage when the
        # configured EMAIL_BACKEND is one of its ESP backends (see django-anymail docs,
        # "Anymail additions" — "just use Anymail's added attributes directly on any Django
        # EmailMessage object"). It isn't part of EmailMultiAlternatives's own type stub, and
        # the console (dev) / locmem (test) backends simply ignore attributes they don't
        # recognise, so this is safe (and inert) in every environment but a real ESP backend.
        message.tags = [category]  # type: ignore[attr-defined]
        message.send()


def get_default_channel() -> NotificationChannel:
    return DjangoEmailChannel()
