from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict


class WorkflowTemplateError(ValueError):
    """Raised when workflow template placeholders cannot be applied."""


Placeholders = Dict[str, Any]


def load_workflow(path: Path) -> Dict[str, Any]:
    """Load a workflow JSON file from disk."""
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")

    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def render_workflow(
    workflow_template: Dict[str, Any],
    *,
    positive_prompt: str,
    negative_prompt: str,
    seed: int,
    width: int,
    height: int,
) -> Dict[str, Any]:
    """Apply user inputs to a workflow template.

    The template may include placeholders (exact string match) that will be replaced:
    - "{{positive_prompt}}"
    - "{{negative_prompt}}"
    - "{{seed}}"
    - "{{width}}"
    - "{{height}}"
    """

    replacements: Placeholders = {
        "{{positive_prompt}}": positive_prompt,
        "{{negative_prompt}}": negative_prompt,
        "{{seed}}": seed,
        "{{width}}": width,
        "{{height}}": height,
    }

    rendered = copy.deepcopy(workflow_template)
    rendered, replaced_any = _replace_placeholders(rendered, replacements)
    if not replaced_any:
        raise WorkflowTemplateError(
            "Workflow template did not contain any placeholders to replace. "
            "Ensure it includes values like {{positive_prompt}} or {{seed}}."
        )
    return rendered


def _replace_placeholders(node: Any, replacements: Placeholders) -> tuple[Any, bool]:
    """Recursively replace placeholders; returns (new_node, replaced?)."""

    if isinstance(node, dict):
        new_dict: Dict[str, Any] = {}
        replaced = False
        for key, value in node.items():
            new_value, changed = _replace_placeholders(value, replacements)
            new_dict[key] = new_value
            replaced = replaced or changed
        return new_dict, replaced

    if isinstance(node, list):
        new_list = []
        replaced = False
        for value in node:
            new_value, changed = _replace_placeholders(value, replacements)
            new_list.append(new_value)
            replaced = replaced or changed
        return new_list, replaced

    if isinstance(node, str):
        if node in replacements:
            return replacements[node], True

        new_value = node
        for placeholder, actual in replacements.items():
            new_value = new_value.replace(placeholder, str(actual))
        return new_value, new_value != node

    return node, False
