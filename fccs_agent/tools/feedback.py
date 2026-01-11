"""Feedback tools for rating tool executions and improving RL learning."""

from typing import Any, Optional

from fccs_agent.config import config
from fccs_agent.services.feedback_service import get_feedback_service


async def submit_feedback(
    execution_id: int,
    rating: int,
    feedback: Optional[str] = None
) -> dict[str, Any]:
    """Submit user feedback for a tool execution to improve RL learning.
    
    This tool allows you to rate a tool execution (1-5 stars) and provide
    optional feedback. This helps the RL system learn which tools work best
    for your use cases and improves future recommendations.
    
    Args:
        execution_id: The ID of the tool execution to rate (from tool result)
        rating: Rating from 1-5 stars (5 = excellent, 1 = poor)
        feedback: Optional text feedback about the execution
    
    Returns:
        dict: Status of feedback submission
    """
    if rating < 1 or rating > 5:
        return {
            "status": "error",
            "error": f"Rating must be between 1 and 5, got {rating}"
        }
    
    feedback_service = get_feedback_service()
    if not feedback_service:
        return {
            "status": "error",
            "error": "Feedback service not available"
        }
    
    try:
        feedback_service.add_user_feedback(
            execution_id=execution_id,
            rating=rating,
            feedback=feedback
        )
        
        return {
            "status": "success",
            "message": f"Feedback submitted: {rating} stars",
            "execution_id": execution_id,
            "rating": rating,
            "feedback": feedback
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to submit feedback: {str(e)}"
        }


async def get_recent_executions(
    tool_name: Optional[str] = None,
    limit: int = 10
) -> dict[str, Any]:
    """Get recent tool executions that can be rated.
    
    Use this to find execution IDs for tools you want to provide feedback on.
    
    Args:
        tool_name: Optional filter by specific tool name
        limit: Maximum number of executions to return (default: 10)
    
    Returns:
        dict: List of recent executions with their IDs and status
    """
    feedback_service = get_feedback_service()
    if not feedback_service:
        return {
            "status": "error",
            "error": "Feedback service not available"
        }
    
    try:
        executions = feedback_service.get_recent_executions(
            tool_name=tool_name,
            limit=limit
        )
        
        return {
            "status": "success",
            "executions": executions,
            "count": len(executions)
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to get executions: {str(e)}"
        }


# Session state for tracking last tool execution
_last_tool_execution: dict[str, int] = {}  # session_id -> execution_id


def set_last_execution(session_id: str, execution_id: int):
    """Track the last tool execution for a session."""
    _last_tool_execution[session_id] = execution_id


async def rate_last_tool(
    rating: str,
    session_id: str = "default"
) -> dict[str, Any]:
    """Quick way to rate the last tool execution.
    
    Use this after any tool execution to provide feedback.
    Call it with 'good' or 'bad' for quick feedback.
    
    Args:
        rating: 'good', 'great', 'ok', 'bad', 'poor' or number 1-5
        session_id: Session ID (optional, defaults to 'default')
    
    Returns:
        dict: Feedback status
    """
    # Convert text ratings to numbers
    rating_map = {
        'good': 4,
        'great': 5,
        'ok': 3,
        'bad': 2,
        'poor': 1,
        '5': 5,
        '4': 4,
        '3': 3,
        '2': 2,
        '1': 1,
    }
    
    rating_value = rating_map.get(rating.lower())
    if rating_value is None:
        return {
            "status": "error",
            "error": f"Invalid rating: {rating}. Use 'good', 'bad', 'ok', 'great', 'poor' or 1-5"
        }
    
    feedback_service = get_feedback_service()
    if not feedback_service:
        return {
            "status": "error",
            "error": "Feedback service not available"
        }
    
    # Try to get the last execution ID for this session
    execution_id = _last_tool_execution.get(session_id)
    
    if not execution_id:
        # Try to get from recent executions
        try:
            executions = feedback_service.get_recent_executions(limit=1)
            if executions:
                execution_id = executions[0].get('id')
        except Exception:
            pass
    
    if not execution_id:
        return {
            "status": "error",
            "error": "No recent tool execution found to rate. Execute a tool first."
        }
    
    try:
        feedback_service.add_user_feedback(
            execution_id=execution_id,
            rating=rating_value,
            feedback=f"Quick rating: {rating}"
        )
        
        return {
            "status": "success",
            "message": f"Rated last tool execution with {rating_value} stars ({rating})",
            "execution_id": execution_id,
            "rating": rating_value
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to submit feedback: {str(e)}"
        }


# Tool definitions for MCP server
TOOL_DEFINITIONS = [
    {
        "name": "submit_feedback",
        "description": "Submit user feedback (rating 1-5 stars) for a tool execution to improve RL learning / Enviar feedback do usuario para melhorar aprendizado RL",
        "inputSchema": {
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "integer",
                    "description": "The ID of the tool execution to rate (found in tool result or from get_recent_executions)",
                },
                "rating": {
                    "type": "integer",
                    "description": "Rating from 1-5 stars (5 = excellent, 4 = good, 3 = average, 2 = poor, 1 = bad)",
                    "minimum": 1,
                    "maximum": 5,
                },
                "feedback": {
                    "type": "string",
                    "description": "Optional text feedback about the execution",
                },
            },
            "required": ["execution_id", "rating"],
        },
    },
    {
        "name": "get_recent_executions",
        "description": "Get recent tool executions that can be rated / Obter execucoes recentes que podem ser avaliadas",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Optional filter by specific tool name",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of executions to return (default: 10)",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "rate_last_tool",
        "description": "Rate the last tool execution with good/bad. Call after asking if the result was helpful.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rating": {
                    "type": "string",
                    "description": "Rating: 'good' (helpful), 'bad' (not helpful), or 1-5",
                    "enum": ["good", "bad", "ok", "great", "poor", "1", "2", "3", "4", "5"],
                },
                "session_id": {
                    "type": "string",
                    "description": "Session ID (optional, defaults to 'default')",
                    "default": "default",
                },
            },
            "required": ["rating"],
        },
    },
]






