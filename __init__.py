"""
AI Builder Project Version 2 Package
A structured AI-powered code generation system with agents in models
"""

__version__ = "2.0.0"
__author__ = "AI Builder Team"

# Import main components for easy access
from .models import (
    TokenManager, ProjectContext,
    manager_agent, codegen_agent, continuation_agent,
    error_files_finder_agent, error_resolver_agent,
    modifier_files_finder_agent, modifier_agent
)
from .prompts import (
    manager_prompt, codegen_prompt, continuation_prompt,
    error_files_finder_prompt, error_resolving_prompt,
    modifier_files_finder_prompt, code_modifier_prompt
)
from .functions import (
    generate_code_with_continuation, handle_error_resolution,
    clean_ai_output, extract_text_from_result_object
)

__all__ = [
    'TokenManager', 'ProjectContext',
    'manager_agent', 'codegen_agent', 'continuation_agent',
    'error_files_finder_agent', 'error_resolver_agent',
    'modifier_files_finder_agent', 'modifier_agent',
    'manager_prompt', 'codegen_prompt', 'continuation_prompt',
    'error_files_finder_prompt', 'error_resolving_prompt',
    'modifier_files_finder_prompt', 'code_modifier_prompt',
    'generate_code_with_continuation', 'handle_error_resolution',
    'clean_ai_output', 'extract_text_from_result_object'
]
