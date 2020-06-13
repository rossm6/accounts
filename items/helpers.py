import string

from .models import Item

alphabet = list(string.ascii_lowercase)

def create_alpha_numbers(n):
    """

    Convert numbers to those as used by spreadsheet columns i.e.

        0 => a
        25 => z
        26 => aa
        701 => zz
        702 => aaa

    """
    f = 26
    s = ""
    i = 0
    while n >= 0:
        m = n // pow(26, i)
        m = int(m % f)
        s += alphabet[m]
        n = n - pow(26, i + 1)
        i += 1
    return s[::-1]


def create_items(n):
    items = []
    for i in range(n):
        tmp = create_alpha_numbers(i)
        items.append(
            Item(
                code=tmp,
                description=tmp + tmp
            )
        )
    return Item.objects.bulk_create(items)