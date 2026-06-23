# Shim retained for `pip install -e .` and legacy tooling only.
# All package metadata — including the authoritative version — lives in
# pyproject.toml ([project]). Do not re-add a version or dependency pin here.
from setuptools import setup

setup()
