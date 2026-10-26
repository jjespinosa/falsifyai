"""Prompt templates for milestone M1."""

from app.prompts.critic import CRITIC_SYSTEM_PROMPT, critic_user_prompt
from app.prompts.parser import PARSER_SYSTEM_PROMPT, parser_user_prompt

__all__ = [
    "CRITIC_SYSTEM_PROMPT",
    "PARSER_SYSTEM_PROMPT",
    "critic_user_prompt",
    "parser_user_prompt",
]
