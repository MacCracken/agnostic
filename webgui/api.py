"""
WebGUI REST API — FastAPI router aggregating route sub-modules.

All business logic lives in the existing manager modules; route modules under
``webgui.routes`` handle HTTP concerns (routing, serialization, auth dependency).

Backward-compatible re-exports kept for existing tests and ``webgui/app.py``.
"""

import os
import sys

from fastapi import APIRouter

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webgui.routes import (
    agents,
    auth,
    dashboard,
    integration,
    mcp,
    persistence,
    reports,
    rpc,
    sessions,
    tasks,
    tenants,
    yeoman_webhooks,
)

# ---------------------------------------------------------------------------
# Aggregate router — mounted in app.py via ``app.include_router(api_router)``
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(dashboard.router)
api_router.include_router(sessions.router)
api_router.include_router(reports.router)
api_router.include_router(agents.router)
api_router.include_router(integration.router)
api_router.include_router(persistence.router)
api_router.include_router(tenants.router)
api_router.include_router(mcp.router)
api_router.include_router(rpc.router)
api_router.include_router(yeoman_webhooks.router)

# ---------------------------------------------------------------------------
# Backward-compatible re-exports (used by tests and app.py)
# ---------------------------------------------------------------------------

from webgui.auth import auth_manager  # noqa: E402, F401
from webgui.routes.dependencies import (  # noqa: E402, F401
    DATABASE_ENABLED,
    MULTI_TENANT_ENABLED,
    _normalize_agent_name,
    _validate_callback_url,
    get_current_user,
    get_db_repo,
    get_tenant_repo,
)
from webgui.routes.reports import _REPORTS_DIR  # noqa: E402, F401
from webgui.routes.tasks import (  # noqa: E402, F401
    TaskStatusResponse,
    TaskSubmitRequest,
)
