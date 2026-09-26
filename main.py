# Generated modular entry point.
from modules.runtime import bootstrap_namespace

_ns = bootstrap_namespace(__name__, __file__)
globals().update(_ns)
