from fastapi import APIRouter
from app.services import source_registry

router = APIRouter()


@router.get("/sources")
async def list_sources():
    """List all sources with status. Includes active + coming_soon + prepared."""
    sources = source_registry.list_all_sources()
    return [_source_dict(s) for s in sources]


def _source_dict(s: dict) -> dict:
    d = {
        "id":                   s["id"],
        "label":                s["label"],
        "description":          s.get("description", ""),
        "status":               s["status"],
        "icon":                 s.get("icon", ""),
        "supports_presets":     s.get("supports_presets", False),
        "supports_comments":    s.get("supports_comments", False),
        "supports_schedule":    s.get("supports_schedule", False),
    }
    # Include integration info for prepared sources
    if s.get("integration_branch"):
        d["integration_branch"] = s["integration_branch"]
        d["integration_tag"] = s.get("integration_tag", "")
        d["activation_note"] = s.get("activation_note", "")
    return d
