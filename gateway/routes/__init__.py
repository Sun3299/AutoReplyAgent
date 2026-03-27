"""
Gateway Routes Package

Exports v1 and v2 routers.
"""

from gateway.routes.v1 import router as v1_router
from gateway.routes.v2 import router as v2_router

__all__ = ["v1_router", "v2_router"]
