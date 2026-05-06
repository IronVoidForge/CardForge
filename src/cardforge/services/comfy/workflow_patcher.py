from __future__ import annotations

from copy import deepcopy
from typing import Any


class WorkflowPatchError(ValueError):
    """Raised when a ComfyUI workflow patch point is invalid."""


class WorkflowPatcher:
    """Small, deterministic ComfyUI API workflow patcher.

    Patch points are declarative `{node_id, path}` objects.  Keeping this tiny
    makes Comfy workflows easy for humans and LLMs to inspect and test.
    """

    def patch(self, workflow_payload: dict[str, Any], patch_points: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
        patched = deepcopy(workflow_payload)
        for field_name, value in values.items():
            if value is None or field_name not in patch_points:
                continue
            patch_point = patch_points[field_name]
            node_id = str(patch_point.get("node_id", "")).strip()
            path = patch_point.get("path", [])
            if not node_id or not isinstance(path, list) or not path:
                raise WorkflowPatchError(f"Patch point {field_name!r} must declare node_id and non-empty path.")
            if node_id not in patched or not isinstance(patched[node_id], dict):
                raise WorkflowPatchError(f"Workflow is missing node {node_id!r} for patch point {field_name!r}.")
            self._set_nested(patched[node_id], [str(part) for part in path], value, field_name=field_name)
        return patched

    def validate_patch_points(self, workflow_payload: dict[str, Any], patch_points: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field_name, patch_point in patch_points.items():
            try:
                self.patch(workflow_payload, {field_name: patch_point}, {field_name: "__validation__"})
            except WorkflowPatchError as exc:
                errors.append(str(exc))
        return errors

    def _set_nested(self, payload: dict[str, Any], path: list[str], value: Any, *, field_name: str) -> None:
        current: Any = payload
        for key in path[:-1]:
            if not isinstance(current, dict) or key not in current:
                raise WorkflowPatchError(f"Patch path for {field_name!r} is missing segment {key!r}.")
            current = current[key]
        final_key = path[-1]
        if not isinstance(current, dict) or final_key not in current:
            raise WorkflowPatchError(f"Patch path for {field_name!r} is missing final segment {final_key!r}.")
        current[final_key] = value
