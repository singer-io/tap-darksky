#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='tap-darksky',
      version='1.0.1',
      description='Singer.io tap for extracting data from the Darksky API',
      author='jeff.huth@bytecode.io',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_darksky'],
      install_requires=[
          'backoff==1.8.0',
          'requests==2.31.0',
          'singer-python==5.8.1'
      ],
      entry_points='''
          [console_scripts]
          tap-darksky=tap_darksky:main
      ''',
      packages=find_packages(),
      package_data={
          'tap_darksky': [
              'schemas/*.json'
          ]
      })