"""Financial recommendation module.

Keep this package initializer lightweight.

The finance models import recommendation constants during Django app loading.
Importing the generator here would pull in health-check services and finance
models again, which causes a circular import while Django initializes models.
Import generator functions directly from apps.finance.recommendations.generator.
"""
