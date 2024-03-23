from setuptools import find_packages, setup

setup(
    name='simplenote_local',
    version='0.2',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'simplenote=simplenote_local.cli:main',
        ],
    },
    install_requires=[
        'simplenote',
        'toml',
        'watchdog',
    ],
)
