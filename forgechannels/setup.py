from setuptools import setup, find_packages

setup(
    name="forgechannels",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "google-api-python-client",
        "google-auth-oauthlib",
        "google-auth",
        "rich",
        "typer",
        "pandas",
    ],
    entry_points={
        "console_scripts": [
            "forgechannels=cli.main:app",
        ],
    },
)
