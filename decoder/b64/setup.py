from setuptools import setup, find_packages

setup(
    name="b64",
    version="0.2",
    author="Marcus LaFerrera (@mlaferrera)",
    url="https://github.com/PUNCH-Cyber/stoq-plugins-public",
    license="Apache License 2.0",
    description="Decode base64 encoded content",
    packages=find_packages(),
    include_package_data=True,
)
