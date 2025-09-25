"""
Functions module for AI Builder Version 2
Contains all utility functions and core functionality
"""

import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from agents import Runner
from models import (
    TokenManager, ProjectContext,
    manager_agent, codegen_agent, continuation_agent,
    error_files_finder_agent, error_resolver_agent,
    modifier_files_finder_agent, modifier_agent
)

# Global instances
token_manager = TokenManager()
project_context = ProjectContext()

# -------------------
# Utility Functions
# -------------------

def extract_text_from_event(event):
    """Extract clean text content from streaming events"""
    try:
        if hasattr(event, "data") and hasattr(event.data, "delta"):
            return event.data.delta
    except Exception:
        pass

    if isinstance(event, dict):
        if "delta" in event and isinstance(event["delta"], str):
            return event["delta"]
        if "text" in event and isinstance(event["text"], str):
            return event["text"]

    if isinstance(event, str):
        return event

    for attr in ("delta", "text", "content"):
        if hasattr(event, attr):
            val = getattr(event, attr)
            if isinstance(val, str):
                return val

    return ""


def extract_text_from_result_object(result_obj):
    """Extract text from result objects"""
    try:
        if hasattr(result_obj, "final_output"):
            return result_obj.final_output
        if hasattr(result_obj, "output"):
            return result_obj.output
        return str(result_obj)
    except Exception:
        return str(result_obj) if result_obj else ""


def is_json_complete(text):
    """Check if JSON is complete and valid"""
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def extract_partial_json(text):
    """Extract partial JSON and identify what's missing"""
    try:
        # Try to parse as-is
        return json.loads(text), True
    except json.JSONDecodeError:
        # Try to close incomplete JSON
        text = text.strip()
        if text.endswith(','):
            text = text[:-1]
        
        # Count braces and brackets
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        
        # Try to close them
        for _ in range(open_brackets):
            text += ']'
        for _ in range(open_braces):
            text += '}'
            
        try:
            return json.loads(text), False
        except json.JSONDecodeError:
            return None, False


def clean_ai_output(output):
    """Clean AI output by removing markdown formatting"""
    cleaned = output.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "").strip()
    return cleaned


def get_file_type(file_path):
    """Get file type from extension"""
    extension = file_path.split('.')[-1].lower()
    type_map = {
        'jsx': 'react_component',
        'js': 'javascript',
        'css': 'stylesheet',
        'json': 'configuration',
        'html': 'markup',
        'md': 'markdown'
    }
    return type_map.get(extension, 'unknown')


def create_structure_only(project_data):
    """Create structure-only version without full file contents (COST OPTIMIZATION)"""
    if not isinstance(project_data, dict):
        return project_data
    
    structure = {
        "project_name": project_data.get("project_name", "unknown"),
        "framework": project_data.get("framework", "React"),
        "files": {}
    }
    
    if "files" in project_data and isinstance(project_data["files"], dict):
        for file_path, content in project_data["files"].items():
            file_type = get_file_type(file_path)
            file_size = len(str(content))
            preview = str(content)[:100] if content else ""
            
            structure["files"][file_path] = {
                "type": file_type,
                "size": file_size,
                "preview": preview
            }
    
    return structure


# -------------------
# COST-OPTIMIZED Error Resolution Function
# -------------------

async def handle_error_resolution(user_input, code):
    """Cost-optimized error resolution - send only structure to AI agents"""
    print("\n🐛 STARTING ERROR RESOLUTION WORKFLOW (COST-OPTIMIZED)")
    print("=" * 50)
    
    # Step 1: Parse and separate structure from content
    try:
        if isinstance(code, str):
            full_project = json.loads(code)
            print("✅ Successfully parsed JSON string")
        elif isinstance(code, dict):
            full_project = code
            print("✅ Using provided dictionary")
        else:
            full_project = {}
            print("⚠️  Unknown code format, using empty structure")
        
        # Store full files content in project context (for later retrieval)
        if "files" in full_project and isinstance(full_project["files"], dict):
            project_context.set_original_files(full_project["files"])
            print("✅ Stored full file contents in project context")
        
        # Create structure-only version for AI agents (COST OPTIMIZATION)
        project_structure = create_structure_only(full_project)
        print(project_structure)
        error_description = user_input
            
    except (json.JSONDecodeError, TypeError) as e:
        print(f"❌ JSON parsing error: {e}")
        # Create fallback
        full_project = {
            "project_name": "error-project",
            "framework": "React",
            "files": {}
        }
        project_structure = full_project

    print(f"📋 Error Description: {error_description}")
    print(f"📁 Full Project Files: {len(full_project.get('files', {}))}")
    print(f"💰 Structure-only sent to AI (cost optimization)")

    # Step 2: Find affected files (send only structure to save tokens)
    print("\n🔍 STEP 1: Identifying affected files...")
    
    finder_input = {
        "error_description": error_description,
        "project_structure": project_structure  # Only structure, not full content!
    }
    
    finder_result = await run_agent_with_token_limit(
        error_files_finder_agent, 
        json.dumps(finder_input), 
        500
    )
    
    try:
        print(finder_result.final_output)
        # Parse finder result
        finder_output_text = clean_ai_output(finder_result.final_output)
        finder_output = json.loads(finder_output_text)
        affected_files = finder_output.get("affected_files", [])
        error_type = finder_output.get("error_type", "unknown")
        analysis = finder_output.get("analysis", "No analysis provided")
        
        print(f"📄 Affected Files: {affected_files}")
        print(f"🏷️  Error Type: {error_type}")
        print(f"📝 Analysis: {analysis}")
        
        # Store error files in project context
        # project_context.set_error_files(affected_files)
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing finder result: {e}")
        print(f"Raw finder output: {finder_result.final_output}")
        affected_files = ["src/components/MessageBubble.jsx"]
        error_type = "runtime_error"
    
    # Step 3: Get ONLY affected file contents from project context
    print("\n📄 STEP 2: Extracting affected file contents...")

    affected_files_content = {}
    for file_name in affected_files:
        if file_name in full_project["files"]:
            affected_files_content[file_name] = full_project["files"][file_name]
            print(f"📄 Extracted: {file_name}")
        else:
            print(f"⚠️ File not found: {file_name}")
    

    # Step 4: Send only affected files to resolver (COST OPTIMIZATION)
    print("\n🔧 STEP 3: Resolving errors...")
    
    resolver_input = {
        "error_description": error_description,
        "file_name": affected_files,
        "affected_files": affected_files_content,  # Only affected files, not all files!
        "error_type": error_type,
    }
    
    resolver_result = await run_agent_with_token_limit(
        error_resolver_agent,
        json.dumps(resolver_input),
        2000
    )
    
    try:
        resolver_output_text = clean_ai_output(resolver_result.final_output)
        # Parse the cleaned JSON string to dictionary
        resolver_output = json.loads(resolver_output_text)
        fixed_files = resolver_output  # Now it's a dict
        
        print(f"✅ Fixed Files: {list(fixed_files.keys())}")
        
        for file_path, fixed_content in fixed_files.items():
            full_project["files"][file_path] = fixed_content
            print(f"📝 Updated: {file_path}")

        
        return full_project
        
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing resolver result: {e}")
        print(f"Raw resolver output: {resolver_result.final_output}")
        return resolver_result.final_output


# -------------------
# Enhanced Streaming Function
# -------------------

async def stream_codegen_with_continuation(agent, user_input, max_tokens=7000):
    """Stream code generation with automatic continuation if tokens run out"""
    print("🚀 Generating code with continuation support...")
    print("-" * 60)
    
    full_output = ""
    generation_complete = False
    
    try:
        stream_result = Runner.run_streamed(agent, input=user_input)
        
        if hasattr(stream_result, "stream_events"):
            async for event in stream_result.stream_events():
                text_piece = extract_text_from_event(event)
                if text_piece:
                    print(text_piece, end="", flush=True)
                    full_output += text_piece
        
        print("\n" + "-" * 60)
        
        # Check if JSON is complete
        partial_json, is_complete = extract_partial_json(full_output)
        
        if not is_complete and partial_json:
            print("🔄 Partial generation detected - continuation needed")
            token_manager.set_continuation_needed(full_output)
            project_context.set_partial_generation("partial_project", full_output)
            
            # Continue generation
            continuation_input = {
                "original_request": user_input,
                "partial_content": full_output,
                "partial_json": partial_json,
                "instruction": "Continue completing the remaining files in the project structure"
            }
            
            print("🔄 Starting continuation generation...")
            continuation_output = await stream_codegen_async(continuation_agent, json.dumps(continuation_input))
            
            # Merge the outputs
            try:
                continuation_json, cont_complete = extract_partial_json(continuation_output)
                if continuation_json and "files" in continuation_json:
                    # Merge files from both generations
                    if partial_json and "files" in partial_json:
                        partial_json["files"].update(continuation_json["files"])
                    full_output = json.dumps(partial_json, indent=2)
                    generation_complete = True
            except Exception as e:
                print(f"❌ Error merging continuation: {e}")
        else:
            generation_complete = is_complete
            
        print(f"✅ Code generation {'completed' if generation_complete else 'partially completed'}!")
        return full_output
        
    except Exception as e:
        print(f"\n❌ Streaming error: {type(e).__name__}: {str(e)}")
        return f"Error: {str(e)}"


async def stream_codegen_async(agent, user_input):
    """Basic async streaming function"""
    print("🚀 Generating code (streaming async)...")
    print("-" * 60)
    try:
        stream_result = Runner.run_streamed(agent, input=user_input)
        full_output = ""

        if hasattr(stream_result, "stream_events"):
            async for event in stream_result.stream_events():
                text_piece = extract_text_from_event(event)
                if text_piece:
                    print(text_piece, end="", flush=True)
                    full_output += text_piece

        print("\n" + "-" * 60)
        print("✅ Code generation completed!")
        return full_output

    except Exception as e:
        print(f"\n❌ Streaming error: {type(e).__name__}: {str(e)}")
        return f"Error: {str(e)}"


# -------------------
# Enhanced runner with token management
# -------------------

async def run_agent_with_token_limit(agent, input_data, estimated_response_tokens=1000):
    """Run agent with token management"""
    input_tokens = token_manager.count_tokens(input_data)
    token_manager.check_and_wait(estimated_response_tokens)

    print(f"🚀 Running {agent.name} agent...")
    print("-" * 60)
    
    try:
        stream_result = Runner.run_streamed(agent, input=input_data)
        full_output = ""

        if hasattr(stream_result, "stream_events"):
            async for event in stream_result.stream_events():
                text_piece = extract_text_from_event(event)
                if text_piece:
                    print(text_piece, end="", flush=True)
                    full_output += text_piece

        print("\n" + "-" * 60)
        
        output_tokens = token_manager.count_tokens(full_output)
        total_tokens = input_tokens + output_tokens
        token_manager.add_tokens(total_tokens)

        class ResultWrapper:
            def __init__(self, raw, text):
                self.raw = raw
                self.final_output = text
        
        result = ResultWrapper(stream_result, full_output)
        return result
    except Exception as e:
        print(f"\n❌ Streaming error: {type(e).__name__}: {str(e)}")
        return f"Error: {str(e)}"
