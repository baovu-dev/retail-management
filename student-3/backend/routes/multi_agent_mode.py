import os
import uuid

import requests
from flask import Blueprint, render_template, request


multi_agent_bp = Blueprint(
    "multi_agent_mode",
    __name__,
)

MULTI_AGENT_SERVICE_URL = os.getenv(
    "MULTI_AGENT_SERVICE_URL",
    "http://localhost:8300",
)

FEATURE = "student-3"

try:
    MULTI_AGENT_SERVICE_TIMEOUT_SECONDS = int(
        os.getenv(
            "MULTI_AGENT_SERVICE_TIMEOUT_SECONDS",
            "120",
        )
    )
except ValueError:
    MULTI_AGENT_SERVICE_TIMEOUT_SECONDS = 120


def multi_agent_mode_is_enabled(req) -> bool:
    enabled = (
        os.getenv(
            "MULTI_AGENT_ENABLED",
            "true",
        )
        .strip()
        .lower()
        in ("1", "true", "yes", "on")
    )

    if not enabled:
        return False

    mode_header = (
        req.headers.get(
            "X-Multi-Agent-Mode",
            "on",
        )
        .strip()
        .lower()
    )

    return mode_header in (
        "1",
        "true",
        "yes",
        "on",
    )


def multi_agent_disabled_response():
    return {
        "status": "error",
        "error": "Multi-Agent mode is disabled.",
    }, 403


def is_valid_workflow_id(
    workflow_id: str,
) -> bool:

    try:
        uuid.UUID(workflow_id)
        return True

    except ValueError:
        return False


@multi_agent_bp.get("/multi-agent")
def multi_agent_page():
    return render_template(
        "multi_agent.html"
    )


@multi_agent_bp.post(
    "/multi-agent/workflow"
)
def multi_agent_workflow():

    if not multi_agent_mode_is_enabled(
        request
    ):
        return multi_agent_disabled_response()

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    user_request = (
        data.get(
            "user_request"
        )
        or ""
    ).strip()

    if not user_request:
        return {
            "status": "error",
            "error":
                "user_request is required",
        }, 400

    try:
        response = requests.post(
            f"{MULTI_AGENT_SERVICE_URL}/workflow",
            json={
                "user_request":
                    user_request,
                "feature":
                    FEATURE,
            },
            timeout=(
                MULTI_AGENT_SERVICE_TIMEOUT_SECONDS
            ),
        )

        return (
            response.json(),
            response.status_code,
        )

    except requests.RequestException as exc:
        return {
            "status": "error",
            "error":
                "Multi-Agent server "
                f"unreachable: {exc}",
        }, 503


@multi_agent_bp.post(
    "/multi-agent/workflow/"
    "<workflow_id>/decision"
)
def multi_agent_decision(
    workflow_id,
):

    if not multi_agent_mode_is_enabled(
        request
    ):
        return multi_agent_disabled_response()

    if not is_valid_workflow_id(
        workflow_id
    ):
        return {
            "status": "error",
            "error":
                "invalid workflow id",
        }, 400

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    payload = {
        key: data.get(key)
        for key in (
            "decision",
            "reviewer",
            "comment",
            "corrected_output",
        )
    }

    try:
        response = requests.post(
            f"{MULTI_AGENT_SERVICE_URL}"
            f"/workflow/{workflow_id}"
            "/decision",
            json=payload,
            timeout=10,
        )

        return (
            response.json(),
            response.status_code,
        )

    except requests.RequestException as exc:
        return {
            "status": "error",
            "error":
                "Multi-Agent server "
                f"unreachable: {exc}",
        }, 503


@multi_agent_bp.get(
    "/multi-agent/workflow/status"
)
def multi_agent_workflow_status():

    if not multi_agent_mode_is_enabled(
        request
    ):
        return multi_agent_disabled_response()

    try:
        response = requests.get(
            f"{MULTI_AGENT_SERVICE_URL}"
            "/workflow/status",
            timeout=10,
        )

        return (
            response.json(),
            response.status_code,
        )

    except requests.RequestException as exc:
        return {
            "status": "error",
            "error":
                "Multi-Agent server "
                f"unreachable: {exc}",
        }, 503