"""Request validation schemas.

These lightweight schemas validate submitted HTML form data before a controller
persists it through the ORM. They are intentionally not database models.
"""
from datetime import datetime


class ValidationError(ValueError):
    pass


def required(form, *fields):
    missing = [field.replace("_", " ").title() for field in fields if not form.get(field, "").strip()]
    if missing:
        raise ValidationError("Please provide: " + ", ".join(missing) + ".")


def number(form, field, label, minimum=0, integer=False):
    try:
        value = int(form.get(field, "")) if integer else float(form.get(field, ""))
    except (TypeError, ValueError):
        raise ValidationError(f"{label} must be a valid number.")
    if value < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    return value


def optional_datetime(form, field, label):
    value = form.get(field, "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{label} must be a valid date and time.")


def valid_email(email):
    return "@" in email and "." in email.rsplit("@", 1)[-1] and len(email) <= 120
