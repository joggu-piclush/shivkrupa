"""
Capital letters on every word, in one place.

The app capitalises as you type ("sharma builders" -> "Sharma Builders"). The server applies the same rule to
whatever it is sent, so an entry is saved capitalised even if it comes from an old open page or any other client.

The rule only ever RAISES the first letter (a-z) of each word and never lowers anything, so "ABC", "MH 31" and
"UPI" stay as they are. Digits, symbols, other scripts and spacing are left alone.
"""
import re

_WORD_START = re.compile(r"(^|\s)([a-z])")


def capitalize_words(text):
    """'sharma  builders' -> 'Sharma  Builders'. None and '' come back unchanged."""
    if not text:
        return text
    return _WORD_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def tidy(model, *fields):
    """A copy of a request body with the named text fields capitalised. Only fields that were actually sent are
    touched, so a field left out of an edit is still left out (an older entry's hidden values are not wiped)."""
    update = {f: capitalize_words(getattr(model, f)) for f in fields if f in model.model_fields_set}
    return model.model_copy(update=update) if update else model
