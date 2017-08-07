from __future__ import unicode_literals

from mopidy_infiniplay import __version__
from setuptools import find_packages, setup

setup(
    name='Mopidy-InfiniPlay',
    version=__version__,
    url='https://github.com/djeebus/mopidy-infiniplay',
    license='Apache License, Version 2.0',
    author='Joe Lombrozo',
    author_email='joe@djeebus.net',
    description='Mopidy extension for keeping the music going',
    long_description=open('README.rst').read(),
    packages=find_packages(),
    zip_safe=True,
    install_requires=[
        'Mopidy >= 2.0',
        'Pykka >= 1.2',
    ],
    entry_points={
        'mopidy.ext': [
            'infiniplay = mopidy_infiniplay:Extension',
        ],
    },
    classifiers=[
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2',
        'Topic :: Multimedia :: Sound/Audio :: Players',
    ],
)
