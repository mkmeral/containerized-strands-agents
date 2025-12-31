# CLI Run Command Refactor Summary

**Branch:** `feature/cli-run`  
**Commit:** `6fa8082`

## Objective

Refactor to share agent logic between Docker runner and CLI, and add a `run` command to the CLI for direct agent execution.

## Changes Made

### 1. Created `src/containerized_strands_agents/agent.py`

New module containing shared agent logic:

- **`create_agent(data_dir, system_prompt=None, tools_dir=None, agent_id="agent")`**
  - Creates a configured Strands Agent with flexible paths
  - Handles system prompt loading (from file or default)
  - Sets up session manager and conversation manager
  - Loads all standard tools (file operations, shell, Python REPL, GitHub tools)
  - Optionally loads dynamic tools from specified directory
  
- **`run_agent(agent, message)`**
  - Runs agent with a message
  - Returns response as string
  
- **`load_system_prompt(data_dir, custom_system_prompt=None)`**
  - Loads system prompt with flexible paths
  - Detects Docker vs local environment
  - Supports custom prompts via file or parameter
  
- **`load_dynamic_tools(agent, tools_dir=None)`**
  - Dynamically loads tools from specified directory

### 2. Updated `docker/agent_runner.py`

**Removed:**
- ~150 lines of duplicated agent creation logic
- `load_system_prompt()` function
- `load_dynamic_tools()` function
- Complex `Agent()` initialization code

**Added:**
- Import from `containerized_strands_agents.agent`
- Simplified `get_agent()` using `create_agent()`
- Updated `_process_request()` to use `run_agent()`

**Kept:**
- FastAPI server setup
- Idle timeout timer
- Request queue handling
- Git configuration
- All API endpoints

### 3. Updated `docker/Dockerfile`

Added:
```dockerfile
COPY src/containerized_strands_agents /app/containerized_strands_agents
```

This makes the shared module available in the container at `/app/containerized_strands_agents`.

### 4. Added `run` Command to CLI

**Usage:**
```bash
# Basic usage
containerized-strands-agents run --data-dir ./my-agent --message "do the thing"

# With custom system prompt
containerized-strands-agents run \
  --data-dir ./my-agent \
  --message "hello" \
  --system-prompt "You are a helpful assistant"
```

**Features:**
- Creates agent data directory if it doesn't exist
- Uses shared agent creation logic
- Prints response to stdout
- Logs progress messages to stderr
- Supports optional custom system prompt
- Sets BYPASS_TOOL_CONSENT for non-interactive operation

## Statistics

- **Lines added:** 305
- **Lines removed:** 169
- **Net change:** +136 lines (but with significantly less duplication)
- **Files changed:** 4

## Benefits

✅ **No code duplication** - Agent creation logic is shared between CLI and Docker runner  
✅ **Easier maintenance** - Changes to agent setup only need to be made once  
✅ **Flexible paths** - Works with both Docker (`/data`) and local directories  
✅ **CLI functionality** - Can now run agents directly without Docker  
✅ **Consistent behavior** - Same agent configuration in both contexts  

## Testing

To test the changes:

1. **Test CLI run command:**
   ```bash
   containerized-strands-agents run \
     --data-dir ./test-agent \
     --message "Print the working directory"
   ```

2. **Test Docker build:**
   ```bash
   cd docker
   docker build -t test-agent .
   ```

3. **Test agent_runner in container:**
   ```bash
   docker run -p 8080:8080 test-agent
   curl http://localhost:8080/health
   ```

## Migration Notes

No breaking changes - the refactor maintains backward compatibility:
- Docker container behavior is unchanged
- FastAPI endpoints remain the same
- Session management works identically
- Tool loading is unchanged

## Next Steps

1. Test the CLI `run` command with various agents
2. Verify Docker builds successfully
3. Ensure agent_runner works correctly in container
4. Consider adding more CLI commands using the shared logic
