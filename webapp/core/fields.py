import logging
from django import forms
from django.db import models

logger = logging.getLogger(__name__)


class TruncatingFormCharField(forms.CharField):
    """Form field that silently truncates values longer than ``max_length``.

    Truncation happens in ``to_python`` so that subsequent validators
    (max length, choice validation, etc.) see the already-truncated value
    and never raise a validation error for being too long.
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value and self.max_length and len(value) > self.max_length:
            value = value[: self.max_length]
        return value


class TruncatingCharField(models.CharField):
    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value and self.max_length and len(value) > self.max_length:
            logger.warning(
                f"Value for {self.name} truncated to {self.max_length} characters."
            )
            return value[: self.max_length]
        return value

    def formfield(self, **kwargs):
        # Use a form field class that truncates instead of rejecting overlong input.
        kwargs.setdefault('form_class', TruncatingFormCharField)
        return super().formfield(**kwargs)
