from setuptools import setup, find_packages

setup(
    name="nmtc-mapper",
    version="0.3.0",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.4.0",
        "numpy>=1.21.0",
        "requests>=2.27.0",
        "aiohttp>=3.8.0",
        "tqdm>=4.64.0",
        "openpyxl>=3.0.0",
    ],
)
