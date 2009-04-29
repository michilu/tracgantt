from ez_setup import use_setuptools
use_setuptools()

from setuptools import setup, find_packages

setup (
        name = "TracGantt",
        version = "0.3.2a",
        packages = ['tracgantt'],
        package_data={'tracgantt': ['templates/*.cs', 'htdocs/*.css']},

        install_requires = ['trac>=0.11'],
        entry_points = {'trac.plugins': ['tracgantt = tracgantt']},

        author = "Will Barton",
        author_email = "wbb4@opendarwin.org",
        description = "This is a Gantt-Chart creation plugin for Trac.",
        url = "http://willbarton.com/code/tracgantt/",
        )
