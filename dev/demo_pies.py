"""Compatibility shim: the starter set moved into the shipped package so
fresh installs can seed it. Dev scripts keep importing from here."""
from piemenu.starter import BINDS, build_pies  # noqa: F401
