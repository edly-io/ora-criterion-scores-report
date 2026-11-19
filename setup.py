"""Packaging for the ORA Criterion Scores Report Open edX plugin."""

from setuptools import find_packages, setup

setup(
    name="ora-criterion-scores-report",
    version="0.3.0",
    description="Open edX plugin: course-wide ORA scores table with dates for course staff.",
    long_description=open("README.rst", encoding="utf-8").read(),
    long_description_content_type="text/x-rst",
    license="AGPL-3.0",
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    package_data={
        "ora_criterion_scores": ["static/*.js", "static/*.css"],
    },
    python_requires=">=3.8",
    install_requires=[
        "Django",
        "openedx-filters",
    ],
    extras_require={
        "test": ["pytest", "django", "openedx-filters", "edx-opaque-keys"],
    },
    zip_safe=False,
    entry_points={
        "lms.djangoapp": [
            "ora_criterion_scores = ora_criterion_scores.apps:OraCriterionScoresConfig",
        ],
    },
    classifiers=[
        "Framework :: Django",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python :: 3",
    ],
)
