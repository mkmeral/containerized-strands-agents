# System Prompt File Feature

## Overview

The `system_prompt_file` feature allows you to provide system prompts for agents by reading from files on the host machine (where the MCP server runs). This is especially useful for:

- Managing complex system prompts in separate files
- Version controlling your system prompts
- Reusing system prompts across different agents
- Keeping system prompts organized and maintainable

## How It Works

When you provide a `system_prompt_file` parameter to the `send_message` tool, the MCP server reads the file content from the host filesystem and uses it as the system prompt for the agent.

### Precedence Rules

If both `system_prompt` and `system_prompt_file` are provided, **`system_prompt_file` takes precedence**.

```
system_prompt_file > system_prompt > default system prompt
```

## Usage

### Basic Example

```python
# Assuming you have a file at /home/user/prompts/code_reviewer.txt
await send_message(
    agent_id="my-code-reviewer",
    message="Please review this Python function: def add(a, b): return a + b",
    system_prompt_file="/home/user/prompts/code_reviewer.txt"
)
```

### With Tilde Expansion

The feature supports `~` (tilde) expansion for user home directories:

```python
await send_message(
    agent_id="data-analyst",
    message="Analyze this dataset",
    system_prompt_file="~/prompts/data_analyst.txt"
)
```

### Example System Prompt File

**File: `~/prompts/code_reviewer.txt`**
```text
You are a specialized code review assistant with expertise in security and performance.

Your responsibilities:
1. Review code for security vulnerabilities
2. Check for performance issues  
3. Ensure code follows best practices
4. Provide constructive, actionable feedback
5. Suggest specific improvements with examples

Always be thorough but concise in your reviews. Focus on:
- Security: SQL injection, XSS, authentication issues
- Performance: Algorithm complexity, memory usage, database queries
- Maintainability: Code clarity, documentation, error handling
- Standards: Language-specific conventions and best practices

Format your feedback with clear headings and prioritize issues by severity.
```

## API Reference

### send_message Tool

The `send_message` tool now accepts an additional optional parameter:

```python
send_message(
    agent_id: str,
    message: str,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    system_prompt: str | None = None,
    system_prompt_file: str | None = None,  # NEW PARAMETER
) -> dict
```

#### Parameters

- `system_prompt_file` (str, optional): Path to a file on the host machine containing the system prompt
  - Supports absolute paths: `/home/user/prompts/agent.txt`
  - Supports tilde expansion: `~/prompts/agent.txt`
  - Supports relative paths (relative to MCP server working directory)

## Error Handling

The feature includes comprehensive error handling:

### File Not Found
```python
# If the file doesn't exist
{
    "status": "error", 
    "error": "Failed to read system prompt file: System prompt file not found: /path/to/missing/file.txt"
}
```

### Empty Files
```python
# If the file is empty or contains only whitespace
{
    "status": "error",
    "error": "Failed to read system prompt file: System prompt file is empty: /path/to/empty/file.txt"
}
```

### Permission Errors
```python
# If the file can't be read due to permissions
{
    "status": "error", 
    "error": "Failed to read system prompt file: [Errno 13] Permission denied: '/protected/file.txt'"
}
```

### Invalid Path (Directory)
```python
# If the path points to a directory instead of a file
{
    "status": "error",
    "error": "Failed to read system prompt file: Path is not a file: /path/to/directory"
}
```

## Session Behavior

Like the regular `system_prompt` parameter, `system_prompt_file` is only applied when:

1. Creating a new agent, OR
2. An existing agent has no conversation history

If an agent already has messages in its session, the system prompt file will be **ignored** and a warning will be logged.

## File Encoding

- Files are read with UTF-8 encoding
- Unicode content is fully supported
- Multiline content is preserved

## Security Considerations

- The MCP server reads files with the permissions of the user running the server
- File paths are resolved and validated before reading
- Only regular files can be read (not directories, devices, etc.)
- Relative paths are resolved relative to the server's working directory

## Examples

### Organizing System Prompts

Create a dedicated directory for your system prompts:

```
~/agent-prompts/
├── code-reviewer.txt
├── data-analyst.txt
├── technical-writer.txt
└── security-auditor.txt
```

Then use them in your agents:

```python
# Code review agent
await send_message(
    agent_id="code-reviewer",
    message="Review this function...",
    system_prompt_file="~/agent-prompts/code-reviewer.txt"
)

# Data analysis agent  
await send_message(
    agent_id="data-analyst", 
    message="Analyze this CSV data...",
    system_prompt_file="~/agent-prompts/data-analyst.txt"
)
```

### Version Control Integration

Since system prompts are now in files, you can:

1. Version control them with Git
2. Share them across team members
3. Test different prompt versions
4. Document changes with commit messages

```bash
# Track your system prompts in Git
git add ~/agent-prompts/
git commit -m "Add specialized code review system prompt"
```

### Dynamic Prompt Selection

You can programmatically choose different system prompt files:

```python
def get_agent_prompt_file(agent_type: str, specialization: str = None) -> str:
    """Get the appropriate system prompt file for an agent."""
    base_path = "~/agent-prompts"
    
    if specialization:
        return f"{base_path}/{agent_type}-{specialization}.txt"
    else:
        return f"{base_path}/{agent_type}.txt"

# Use specialized prompts
await send_message(
    agent_id="security-reviewer",
    message="Review this authentication code...", 
    system_prompt_file=get_agent_prompt_file("code-reviewer", "security")
)
```

## Testing

The feature includes comprehensive tests covering:

- Successful file reading
- Error handling for various failure modes
- Unicode and multiline content support
- Tilde expansion
- Precedence over text-based system prompts
- Integration with agent lifecycle

Run the tests:

```bash
python -m pytest tests/test_system_prompt_file.py -v
```

## Migration from Text-Based Prompts

If you're currently using the `system_prompt` parameter with large prompts, consider migrating to files:

**Before:**
```python
long_prompt = """You are a specialized assistant...
[many lines of prompt text]
...always be helpful and accurate."""

await send_message(
    agent_id="my-agent",
    message="Hello",
    system_prompt=long_prompt
)
```

**After:**
```python
# Save prompt to ~/prompts/specialized-assistant.txt
await send_message(
    agent_id="my-agent", 
    message="Hello",
    system_prompt_file="~/prompts/specialized-assistant.txt"
)
```

## Implementation Details

The feature is implemented in two main components:

1. **Server (`server.py`)**: Adds the `system_prompt_file` parameter to the `send_message` tool
2. **Agent Manager (`agent_manager.py`)**: Handles file reading and error processing

Key implementation points:

- File reading happens on the host (MCP server side), not in the container
- Path expansion and validation occur before file access
- Proper error propagation ensures clear feedback to clients
- File content is cached in the agent's system prompt storage