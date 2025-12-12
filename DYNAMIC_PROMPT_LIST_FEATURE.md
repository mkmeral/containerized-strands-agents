# Dynamic System Prompt List Feature

## Overview

This feature enhances the `send_message` tool by dynamically listing available system prompts in its description. When the MCP server starts, it reads the `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` environment variable to discover system prompt files and includes them in the tool documentation.

## How It Works

1. **On Server Startup**: The server reads the `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` environment variable
2. **File Discovery**: It parses comma-separated file paths from the environment variable
3. **Display Name Extraction**: For each file, it extracts a display name:
   - If the first line starts with `#`, uses that as the name (without the `#`)
   - Otherwise, uses the filename (without extension)
4. **Dynamic Documentation**: Updates the `send_message` tool description to list all available prompts

## Configuration

Set the environment variable before starting the MCP server:

```bash
export CONTAINERIZED_AGENTS_SYSTEM_PROMPTS="/path/to/prompt1.txt,/path/to/prompt2.md,~/prompts/prompt3.txt"
```

### Supported Features

- **Absolute paths**: `/home/user/prompts/code_reviewer.txt`
- **Tilde expansion**: `~/prompts/data_analyst.txt`
- **Relative paths**: `prompts/helper.txt` (relative to server working directory)
- **Mixed file types**: `.txt`, `.md`, or any text file
- **Whitespace tolerance**: Extra spaces and empty entries are ignored

## Example

### System Prompt Files

**File: `/home/user/prompts/code_reviewer.txt`**
```text
# Advanced Code Review Assistant
You are a specialized code review assistant with expertise in security and performance.
[... rest of prompt ...]
```

**File: `/home/user/prompts/data_analyst.txt`**
```text
# Data Analysis Specialist  
You are a data analyst with expertise in statistical analysis and visualization.
[... rest of prompt ...]
```

**File: `/home/user/prompts/simple_helper.txt`**
```text
You are a friendly and helpful assistant.
```

### Environment Variable

```bash
export CONTAINERIZED_AGENTS_SYSTEM_PROMPTS="/home/user/prompts/code_reviewer.txt,/home/user/prompts/data_analyst.txt,/home/user/prompts/simple_helper.txt"
```

### Result in Tool Description

When calling agents see the `send_message` tool, they will see:

```
Send a message to an agent (fire-and-forget). Creates the agent if it doesn't exist.

[... standard documentation ...]

Args:
    [... standard parameters ...]
    system_prompt_file: Path to a file on the host machine containing the system 
                        prompt. If both system_prompt and system_prompt_file are 
                        provided, system_prompt_file takes precedence.
        Available system prompts:
        - Advanced Code Review Assistant: /home/user/prompts/code_reviewer.txt
        - Data Analysis Specialist: /home/user/prompts/data_analyst.txt
        - simple_helper: /home/user/prompts/simple_helper.txt

Returns:
    [... standard return documentation ...]
```

## Error Handling

The feature is designed to be robust and backwards compatible:

- **Missing Environment Variable**: If `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` is not set, the tool works exactly as before
- **Nonexistent Files**: Files that don't exist are skipped with a warning logged
- **Unreadable Files**: Files that can't be read fall back to using the filename as the display name
- **Invalid Paths**: Invalid paths are skipped with warnings
- **Directories**: Directory paths are ignored (only files are processed)

## Benefits

1. **Discoverability**: Calling agents can see what system prompts are available
2. **Self-Documenting**: The tool description updates automatically when prompts are added/removed  
3. **No Code Changes**: Adding new prompts only requires updating the environment variable
4. **Backwards Compatible**: Existing functionality is unchanged when the feature is not configured

## Implementation Details

The feature is implemented in `src/containerized_strands_agents/server.py`:

- `_parse_system_prompts_env()`: Parses the environment variable and extracts prompt information
- `_build_send_message_docstring()`: Builds the dynamic docstring with available prompts
- Dynamic tool registration: The `send_message` tool is registered with the dynamic docstring

## Testing

Run the tests to verify the feature works correctly:

```bash
# Run specific tests for this feature
python -m pytest tests/test_dynamic_system_prompts.py -v

# Run simple standalone test
python test_dynamic_prompts_simple.py
```

## Usage Examples

Once the server is running with configured prompts, calling agents can:

1. **See Available Prompts**: Check the tool description to see what's available
2. **Use by Path**: Reference prompts by their full path in `system_prompt_file`
3. **Copy Paths**: Copy the exact paths from the tool description to avoid typos

Example usage in calling agent:
```python
# Use a specialized code review prompt
await send_message(
    agent_id="my-reviewer",
    message="Please review this code...",
    system_prompt_file="/home/user/prompts/code_reviewer.txt"
)
```

The feature makes it easy for users to discover and use pre-configured system prompts without needing to remember file paths or browse the filesystem.
