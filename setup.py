#!/usr/bin/env python
import os

from setuptools import setup, find_packages


def get_version():
    return "0.1.1"


def get_long_description():
    with open("README.rst", "r") as f:
        return f.read()


setup(
    name="readable-content",
    version=get_version(),
    author="Nabin Khadka",
    author_email="nbnkhadka14@gmail.com",
    license="MIT license",
    long_description=get_long_description(),
    description="Collect actual content of any article, blog, news, etc.",
    url="https://github.com/nabinkhadka/readable-content",
    packages=find_packages(),
    install_requires=["beautifulsoup4", "lxml",],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
