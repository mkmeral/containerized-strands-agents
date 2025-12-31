    # Remote Agent Runtime & Snapshot Design
     
    ## Overview
     
    Run containerized Strands agents anywhere (local Docker, GitHub Actions, Bedrock AgentCore) with portable state that can be transferred between environments.
     
    ## Goals
     
    1. **Run agents anywhere**: Same agent code works on local Docker, GHA, AgentCore
    2. **Portable state**: Zip the workspace folder, move it, continue where you left off
     
    ## Core Idea
     
    Each agent gets a data directory. Everything lives inside it - including the agent runner code. This directory IS the container's working directory, so agent file operations happen at the root.
     
    ```
    {agent_data_dir}/                # Mounted as /data/workspace (container WORKDIR)
    ├── .agent/
    │   ├── runner/                  # Agent runner code (copied from package)
    │   │   ├── agent_runner.py
    │   │   ├── github_tools.py
    │   │   └── requirements.txt
    │   ├── session/                 # Conversation history
    │   ├── system_prompt.txt        # Custom prompt (optional)
    │   └── tools/                   # Custom tools (optional)
    └── ...                          # Agent's files at root (repos, code, etc.)
    ```
     
    **Snapshot = zip the agent data directory. Restore = unzip it. Run it anywhere.**
     
    ## Input/Output by Runtime
     
    ### Local Docker
     
    **Input**: MCP tools (`send_message`) or CLI
    ```bash
    containerized-strands-agents run --data-dir ./my-agent --message "do the thing"
    ```
     
    **Output**: 
    - Real-time: `get_messages` MCP tool or poll `/history` endpoint
    - Files: Agent writes to data dir root, visible immediately on host
     
    **Snapshot to local**: Already local - just zip it
     
    ---
     
    ### GitHub Actions
     
    **Input**: `workflow_dispatch` with message parameter
    ```yaml
    on:
      workflow_dispatch:
        inputs:
          message:
            description: 'Task for the agent'
            required: true
    ```
     
    **Output**:
    - Real-time: Watch GHA logs (agent stdout)
    - Final: Download artifact containing workspace
     
    **Snapshot to local**:
    ```bash
    # Option 1: GH CLI
    gh run download <run-id> -n agent-data
     
    # Option 2: API
    curl -L -H "Authorization: Bearer $GITHUB_TOKEN" \
      "https://api.github.com/repos/owner/repo/actions/artifacts/<id>/zip" \
      -o agent-data.zip
    ```
     
    ---
     
    ### AgentCore
     
    **Input**: `InvokeAgentRuntime` API or AgentCore CLI
    ```bash
    agentcore invoke --agent-arn <arn> --session-id <id> --input '{"prompt": "do the thing"}'
    ```
     
    **Output**:
    - Real-time: Streaming response from invoke call
    - Session state: Lives in AgentCore microVM for up to 8 hours
     
    **Snapshot to local**:
    AgentCore doesn't persist files beyond session. Options:
    1. Have agent push to S3 before session ends
    2. Have agent push to git repo
    3. Use AgentCore Memory for conversation state (not files)
     
    ```python
    # In agent's system prompt or as final step:
    # "Before finishing, zip your data and upload to s3://bucket/snapshots/"
    ```
     
    ---
     
    ## Runtimes
     
    ### Local Docker (current)
    - Container mounts agent data dir to `/data/workspace` (also WORKDIR)
    - FastAPI server handles messages
    - Session persisted via FileSessionManager to `.agent/session/`
     
    ### AgentCore
    Thin wrapper using `BedrockAgentCoreApp`:
     
    ```python
    from bedrock_agentcore.runtime import BedrockAgentCoreApp
    from strands import Agent
     
    app = BedrockAgentCoreApp()
    agent = Agent(...)  # Same setup as local
     
    @app.entrypoint
    async def invoke(payload, context):
        async for event in agent.stream_async(payload.get("prompt", "")):
            yield event
     
    if __name__ == "__main__":
        app.run()
    ```
     
    ### GitHub Actions
    Run the agent inside GHA, use artifacts for state:
     
    ```yaml
    name: Run Agent
    on:
      workflow_dispatch:
        inputs:
          message:
            description: 'Task for the agent'
            required: true
          snapshot_artifact:
            description: 'Artifact name to restore from (optional)'
            required: false
     
    jobs:
      run-agent:
        runs-on: ubuntu-latest
        steps:
          - name: Download previous state
            if: inputs.snapshot_artifact
            uses: actions/download-artifact@v4
            with:
              name: ${{ inputs.snapshot_artifact }}
              path: agent-data/
            continue-on-error: true
          
          - name: Setup agent (if new)
            if: ${{ !inputs.snapshot_artifact }}
            run: |
              mkdir -p agent-data/.agent
              # Copy runner code, etc.
          
          - name: Install dependencies
            run: pip install -r agent-data/.agent/runner/requirements.txt
          
          - name: Run agent
            env:
              AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
              AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
            run: |
              cd agent-data
              python .agent/runner/agent_runner.py --message "${{ inputs.message }}"
          
          - name: Upload snapshot
            uses: actions/upload-artifact@v4
            with:
              name: agent-data-${{ github.run_id }}
              path: agent-data/
              retention-days: 30
    ```
     
    ## Snapshots
     
    **Create**: `zip -r snapshot.zip {agent_data_dir}/`
     
    **Restore**: `unzip snapshot.zip -d {new_location}/`
     
    **What's included**:
    - `.agent/runner/` - Agent code (self-contained, runnable)
    - `.agent/session/` - Conversation history
    - `.agent/tools/` - Custom tools
    - Everything else at root - Agent's work files (repos, code, etc.)
     
    **CLI helpers**:
    ```bash
    # Create snapshot
    containerized-strands-agents snapshot --data-dir ./my-agent --output snapshot.zip
     
    # Restore snapshot  
    containerized-strands-agents restore --snapshot snapshot.zip --data-dir ./new-agent
     
    # Pull from GHA
    containerized-strands-agents pull --repo owner/repo --run-id 12345 --output ./my-agent
    ```
     
    ## Summary: Getting Output
     
    | Runtime | Real-time Output | Final Output | Get Snapshot |
    |---------|-----------------|--------------|--------------|
    | Local Docker | `get_messages` / API | Files on disk | `zip {data_dir}/` |
    | GitHub Actions | GHA logs | Download artifact | `gh run download` |
    | AgentCore | Streaming response | Agent must push to S3/git | Pull from S3/git |
 
## Implementation Status

| Item | Status |
|------|--------|
| Restructure to `.agent/` layout | ✅ Done |
| CLI commands for snapshot/restore | ✅ Done |
| Hardcoded agent ID for portable snapshots | ✅ Done |
| CLI command for GHA pull | ✅ Done |
| GHA workflow template | ✅ Done |
| AgentCore handler file | ❌ Not started |
 
## Alternatives Not Chosen
 
| Approach | Why Not |
    |----------|---------|
    | Separate runner from workspace | Snapshot not self-contained |
    | Custom snapshot format | Overengineered - just zip |
    | Real-time streaming from GHA | Complex, GHA not designed for it |


## Future Enhancements (from research-agent analysis)

### Resume CLI Flag
```bash
# Continue from snapshot with new query
containerized-strands-agents run --resume ./my-agent "continue the task"
```

### Auto-generated resume.py
When creating a snapshot, generate `.agent/resume.py`:
```python
#!/usr/bin/env python3
"""Run: python resume.py "your query" """
import subprocess, sys
subprocess.run(["python", ".agent/runner/agent_runner.py", "--message", " ".join(sys.argv[1:])])
```
Makes snapshots "double-click runnable" without knowing CLI.

### Runtime Metadata
Add `.agent/metadata.json` with environment info for debugging cross-environment issues:
```json
{
  "created_at": "2024-01-15T10:30:00Z",
  "python_version": "3.11.5",
  "platform": "darwin-arm64",
  "hostname": "dev-machine",
  "original_cwd": "/Users/dev/agents/my-agent"
}
```

### Multi-transport MCP (later)
Support stdio, SSE, and HTTP MCP transports from `mcp.json` for agents connecting to remote servers.
