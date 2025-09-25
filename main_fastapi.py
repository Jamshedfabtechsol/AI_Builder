"""
FastAPI Main module for AI Builder Version 2
Contains FastAPI endpoints for different AI agent tasks
"""

import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from agents import set_tracing_disabled

# Import from our modules
from models import (
    TokenManager, ProjectContext,
    manager_agent, planner_agent, codegen_agent, continuation_agent,
    error_files_finder_agent, error_resolver_agent,
    modifier_files_finder_agent, modifier_agent
)
from functions import (
    handle_error_resolution,
    clean_ai_output, extract_text_from_result_object,
    stream_codegen_with_continuation, run_agent_with_token_limit
)

# -------------------
# Load environment variables
# -------------------
_ = load_dotenv(find_dotenv())
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

if not CLAUDE_API_KEY:
    raise ValueError("CLAUDE_API_KEY environment variable is required")

# Disable tracing for cleaner output
set_tracing_disabled(True)

# -------------------
# Initialize FastAPI app
# -------------------
app = FastAPI(
    title="AI Builder Version 2",
    description="AI-powered code generation and project management API",
    version="2.0.0"
)

# -------------------
# Pydantic Models
# -------------------
class UserRequest(BaseModel):
    user_input: str
    project_context: dict = None

class ManagerRequest(BaseModel):
    user_input: str

class ManagerResponse(BaseModel):
    task: str
    confidence: float = 1.0

# -------------------
# Global instances
# -------------------
token_manager = TokenManager()
project_context = ProjectContext()

# -------------------
# Helper Functions
# -------------------
async def get_manager_decision(user_input: str) -> str:
    """Get manager agent decision for task routing"""
    try:
        manager_result = await run_agent_with_token_limit(manager_agent, user_input, 100)
        task_type = manager_result.final_output.strip()
        
        # Parse manager decision
        try:
            manager_decision = json.loads(task_type)
            task = manager_decision.get("task", "")
        except:
            if "code_generation" in task_type:
                task = "code_generation"
            elif "error_resolution" in task_type:
                task = "error_resolution"
            elif "code_change" in task_type:
                task = "code_change"
            elif "code_continuation" in task_type:
                task = "code_continuation"
            else:
                task = "code_generation"
        
        return task
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manager decision failed: {str(e)}")

# -------------------
# API Endpoints
# -------------------

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "AI Builder Version 2 API",
        "version": "2.0.0",
        "endpoints": {
            "manager": "/manager - Route user requests to appropriate agents",
            "code_generation": "/code_generation - Generate new projects with planning",
            "error_resolution": "/error_resolution - Fix bugs and errors",
            "code_change": "/code_change - Modify existing code",
            "code_continuation": "/code_continuation - Complete partial code"
        }
    }

@app.post("/manager_endpoint")
async def manager_endpoint(request: ManagerRequest):
    """Manager Agent - Routes user requests to appropriate tasks"""
    try:
        task = await get_manager_decision(request.user_input)
        return ManagerResponse(task=task, confidence=1.0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/code_generation")
async def code_generation_endpoint(request: UserRequest):
    """Code Generation with Planning - Creates new projects with comprehensive planning"""
    try:
        # Initialize empty project structure
        code = {
            "project_name": "",
            "framework": "React",
            "files": {}
        }
        
        # First create a plan
        plan_output = await run_agent_with_token_limit(planner_agent, request.user_input, 1000)
        plan_data = clean_ai_output(plan_output.final_output)
        
        # Generate code based on the plan
        codegen_input = f"Based on this project plan, generate the complete React project:\n\n{plan_data}\n\nUser Request: {request.user_input}"
        
        # Stream the code generation
        async def generate():
            async for chunk in stream_codegen_with_continuation(codegen_agent, codegen_input):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/error_resolution")
async def error_resolution_endpoint(request: UserRequest):
    """Error Resolution - Fixes bugs and errors in existing code"""
    try:
        if not request.project_context:
            raise HTTPException(status_code=400, detail="project_context is required for error resolution")
        
        # Use the provided project context
        project_context.set_project_data(request.project_context)
        
        # Handle error resolution
        result = await handle_error_resolution(request.user_input)
        
        return {"result": result, "status": "completed"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/code_change")
async def code_change_endpoint(request: UserRequest):
    """Code Change - Modifies existing code based on user requirements"""
    try:
        if not request.project_context:
            raise HTTPException(status_code=400, detail="project_context is required for code changes")
        
        # Use the provided project context
        project_context.set_project_data(request.project_context)
        
        # Stream the code modification
        async def modify():
            async for chunk in stream_codegen_with_continuation(modifier_agent, request.user_input):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(
            modify(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/code_continuation")
async def code_continuation_endpoint(request: UserRequest):
    """Code Continuation - Completes partially generated code"""
    try:
        if not request.project_context:
            raise HTTPException(status_code=400, detail="project_context is required for code continuation")
        
        # Use the provided project context
        project_context.set_project_data(request.project_context)
        
        # Stream the code continuation
        async def continue_code():
            async for chunk in stream_codegen_with_continuation(continuation_agent, request.user_input):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        
        return StreamingResponse(
            continue_code(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------
# Health Check
# -------------------
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# -------------------
# Run the application
# -------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
