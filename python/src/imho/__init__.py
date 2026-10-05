"""Python client for the imho.run agent API (Steam game recommendations).

>>> from imho import ImhoClient
>>> with ImhoClient() as imho:
...     for pick in imho.games_like("Hollow Knight", n=3)["results"]:
...         print(pick["rank"], pick["name"], "-", pick["why"])
"""

from ._version import __version__
from .client import DEFAULT_BASE_URL, AsyncImhoClient, ImhoClient
from .errors import (
    BadRequestError,
    DisabledError,
    ImhoError,
    NotFoundError,
    RateLimitError,
    ToolError,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "AsyncImhoClient",
    "BadRequestError",
    "DisabledError",
    "ImhoClient",
    "ImhoError",
    "NotFoundError",
    "RateLimitError",
    "ToolError",
    "__version__",
]
