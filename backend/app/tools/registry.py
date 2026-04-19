from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AuditResultStatus, ChatSession, RoleName, User
from app.services.appointment_service import appointment_payload, check_available_slots, create_appointment, format_slot_label
from app.services.audit_service import log_action
from app.services.user_service import user_profile_payload


def tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "fetch_user_profile",
                "description": "Fetch the current authenticated user's profile and role information.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "validate_user_role",
                "description": "Validate whether the authenticated user can perform an action for a target user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "required_role": {"type": "string"},
                        "action": {"type": "string"},
                        "target_user_id": {"type": "integer"},
                    },
                    "required": ["required_role", "action", "target_user_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_available_slots",
                "description": "List the next available appointment slots for a department.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "department": {"type": "string"},
                        "preferred_date": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["department"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_appointment",
                "description": "Create an appointment using a selected slot and collected customer information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "slot_id": {"type": "integer"},
                        "purpose": {"type": "string"},
                        "contact_phone": {"type": "string"},
                        "notes": {"type": "string"},
                        "language": {"type": "string"},
                        "target_user_id": {"type": "integer"},
                    },
                    "required": ["slot_id", "purpose", "contact_phone", "language"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_application",
                "description": "Mock future workflow hook for application submission. Returns a not-enabled response in the MVP.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                    "required": ["template"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def execute_tool(
    db: Session,
    *,
    name: str,
    arguments: str,
    current_user: User,
    session: ChatSession,
) -> dict:
    payload = json.loads(arguments or "{}")
    try:
        if name == "fetch_user_profile":
            result = user_profile_payload(current_user)
        elif name == "validate_user_role":
            target_user_id = payload["target_user_id"]
            allowed = current_user.role.name in {RoleName.ADMIN, RoleName.OPERATOR}
            if current_user.role.name == RoleName.CUSTOMER and target_user_id == current_user.id:
                allowed = True
            result = {
                "allowed": allowed,
                "required_role": payload["required_role"],
                "action": payload["action"],
                "target_user_id": target_user_id,
            }
        elif name == "check_available_slots":
            slots = check_available_slots(
                db,
                department=payload.get("department"),
                preferred_date=payload.get("preferred_date"),
                limit=payload.get("limit", 3),
            )
            result = {
                "slots": [
                    {
                        "id": slot.id,
                        "department": slot.department,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                        "location": slot.location,
                        "label": format_slot_label(slot),
                    }
                    for slot in slots
                ]
            }
        elif name == "create_appointment":
            appointment = create_appointment(
                db,
                acting_user=current_user,
                slot_id=payload["slot_id"],
                purpose=payload["purpose"],
                contact_phone=payload["contact_phone"],
                notes=payload.get("notes"),
                language=payload["language"],
                target_user_id=payload.get("target_user_id"),
            )
            result = appointment_payload(appointment)
        elif name == "save_application":
            result = {"enabled": False, "message": "Application submission flow is planned for a later iteration."}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")

        log_action(
            db,
            user_id=current_user.id,
            session_id=session.id,
            action_type="agent.tool_executed",
            explanation=f"Tool {name} executed",
            tool_name=name,
            result_status=AuditResultStatus.SUCCESS,
            details=payload,
        )
        return result
    except HTTPException:
        log_action(
            db,
            user_id=current_user.id,
            session_id=session.id,
            action_type="agent.tool_executed",
            explanation=f"Tool {name} denied or failed",
            tool_name=name,
            result_status=AuditResultStatus.FAILURE,
            success=False,
            details=payload,
        )
        raise
