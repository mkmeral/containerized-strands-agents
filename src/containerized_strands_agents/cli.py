#!/usr/bin/env python3
"""CLI commands for containerized-strands-agents snapshot management."""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NoReturn

from .agent import create_agent, run_agent

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def validate_data_dir(data_dir: Path) -> None:
    """Validate that a directory contains agent data structure.
    
    Args:
        data_dir: Path to the directory to validate
        
    Raises:
        ValueError: If the directory doesn't appear to be a valid agent data directory
    """
    # Check if directory exists
    if not data_dir.exists():
        raise ValueError(f"Directory does not exist: {data_dir}")
    
    if not data_dir.is_dir():
        raise ValueError(f"Path is not a directory: {data_dir}")
    
    # Check for expected structure (.agent directory)
    agent_meta_dir = data_dir / ".agent"
    if not agent_meta_dir.exists():
        raise ValueError(
            f"Directory does not appear to be an agent data directory.\n"
            f"Expected .agent/ subdirectory not found in: {data_dir}"
        )


def snapshot_command(data_dir: str, output: str) -> None:
    """Create a snapshot (zip archive) of an agent data directory.
    
    Args:
        data_dir: Path to the agent data directory to snapshot
        output: Path to the output zip file
    """
    try:
        # Resolve and validate paths
        data_dir_path = Path(data_dir).expanduser().resolve()
        output_path = Path(output).expanduser().resolve()
        
        # Validate data directory
        validate_data_dir(data_dir_path)
        
        # Create parent directory for output if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if output file already exists
        if output_path.exists():
            response = input(f"Output file {output_path} already exists. Overwrite? (y/N): ")
            if response.lower() != 'y':
                print("Snapshot cancelled.")
                return
        
        # Create zip archive
        print(f"Creating snapshot of {data_dir_path}...")
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Walk through the data directory and add all files
            for file_path in data_dir_path.rglob('*'):
                if file_path.is_file():
                    # Store relative path in the zip
                    arcname = file_path.relative_to(data_dir_path)
                    zipf.write(file_path, arcname)
                    
        print(f"✓ Snapshot created successfully: {output_path}")
        print(f"  Size: {output_path.stat().st_size / (1024*1024):.2f} MB")
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error creating snapshot: {e}", file=sys.stderr)
        sys.exit(1)


def restore_command(snapshot: str, data_dir: str) -> None:
    """Restore an agent from a snapshot (zip archive).
    
    Args:
        snapshot: Path to the snapshot zip file
        data_dir: Path to the target directory to restore the agent
    """
    try:
        # Resolve paths
        snapshot_path = Path(snapshot).expanduser().resolve()
        data_dir_path = Path(data_dir).expanduser().resolve()
        
        # Validate snapshot file exists
        if not snapshot_path.exists():
            raise ValueError(f"Snapshot file does not exist: {snapshot_path}")
        
        if not snapshot_path.is_file():
            raise ValueError(f"Snapshot path is not a file: {snapshot_path}")
        
        # Check if target directory exists and is not empty
        if data_dir_path.exists():
            if not data_dir_path.is_dir():
                raise ValueError(f"Target path exists but is not a directory: {data_dir_path}")
            
            # Check if directory is not empty
            if any(data_dir_path.iterdir()):
                response = input(
                    f"Target directory {data_dir_path} is not empty. "
                    f"Contents will be merged/overwritten. Continue? (y/N): "
                )
                if response.lower() != 'y':
                    print("Restore cancelled.")
                    return
        
        # Create target directory
        data_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Extract zip archive
        print(f"Restoring snapshot from {snapshot_path}...")
        with zipfile.ZipFile(snapshot_path, 'r') as zipf:
            # Validate it's a proper agent snapshot
            file_list = zipf.namelist()
            has_agent_dir = any('.agent' in name for name in file_list)
            
            if not has_agent_dir:
                raise ValueError(
                    f"Snapshot does not appear to be a valid agent snapshot.\n"
                    f"Expected .agent/ directory not found in archive."
                )
            
            # Extract all files
            zipf.extractall(data_dir_path)
        
        print(f"✓ Snapshot restored successfully to: {data_dir_path}")
        print(f"  Files extracted: {len(file_list)}")
        print(f"\nAgent is ready to run. Use the agent manager to start it.")
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error restoring snapshot: {e}", file=sys.stderr)
        sys.exit(1)


def run_command(data_dir: str, message: str, system_prompt: str = None) -> None:
    """Run an agent with a message and print the response.
    
    Args:
        data_dir: Path to the agent data directory
        message: Message to send to the agent
        system_prompt: Optional custom system prompt
    """
    try:
        # Resolve path
        data_dir_path = Path(data_dir).expanduser().resolve()
        
        # Create data directory if it doesn't exist
        data_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Set bypass tool consent for CLI operation
        os.environ["BYPASS_TOOL_CONSENT"] = "true"
        
        # Create agent
        print(f"Initializing agent from {data_dir_path}...", file=sys.stderr)
        agent = create_agent(
            data_dir=data_dir_path,
            system_prompt=system_prompt,
        )
        
        # Run agent with message
        print(f"Running agent...", file=sys.stderr)
        response = run_agent(agent, message)
        
        # Print response to stdout
        print(response)
        
    except Exception as e:
        print(f"Error running agent: {e}", file=sys.stderr)
        sys.exit(1)


def pull_command(
    repo: str,
    artifact: str = None,
    run_id: str = None,
    data_dir: str = None,
    token: str = None,
) -> None:
    """Pull agent state from GitHub Actions artifact.
    
    Args:
        repo: Repository in owner/repo format
        artifact: Artifact name to download (optional if run_id provided)
        run_id: Run ID to download latest artifact from (optional if artifact provided)
        data_dir: Target directory to extract to
        token: GitHub token (uses GITHUB_TOKEN env var if not provided)
    """
    try:
        # Validate inputs
        if not artifact and not run_id:
            raise ValueError("Either --artifact or --run-id must be provided")
        
        # Get GitHub token
        gh_token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        
        # Check if gh CLI is available
        gh_available = shutil.which("gh") is not None
        
        if not gh_available and not gh_token:
            raise ValueError(
                "GitHub CLI (gh) not found and no GITHUB_TOKEN set.\n"
                "Either install gh CLI (https://cli.github.com/) or set GITHUB_TOKEN environment variable."
            )
        
        # Resolve output path
        data_dir_path = Path(data_dir).expanduser().resolve() if data_dir else Path.cwd() / "agent-data"
        
        # Check if target exists
        if data_dir_path.exists() and any(data_dir_path.iterdir()):
            response = input(
                f"Target directory {data_dir_path} is not empty. "
                f"Contents will be merged/overwritten. Continue? (y/N): "
            )
            if response.lower() != 'y':
                print("Pull cancelled.")
                return
        
        data_dir_path.mkdir(parents=True, exist_ok=True)
        
        if gh_available:
            # Use gh CLI (simpler, handles auth automatically)
            _pull_with_gh_cli(repo, artifact, run_id, data_dir_path)
        else:
            # Use GitHub API directly
            _pull_with_api(repo, artifact, run_id, data_dir_path, gh_token)
        
        print(f"✓ Agent state pulled successfully to: {data_dir_path}")
        
        # Validate the pulled data
        if (data_dir_path / ".agent").exists():
            print(f"  Agent data structure verified.")
        else:
            print(f"  Warning: .agent/ directory not found - may not be a valid agent snapshot")
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error pulling from GitHub: {e}", file=sys.stderr)
        sys.exit(1)


def _pull_with_gh_cli(repo: str, artifact: str, run_id: str, data_dir: Path) -> None:
    """Pull artifact using GitHub CLI."""
    if artifact:
        # Download specific artifact by name
        print(f"Downloading artifact '{artifact}' from {repo}...")
        cmd = ["gh", "run", "download", "-R", repo, "-n", artifact, "-D", str(data_dir)]
    else:
        # Download from specific run
        print(f"Downloading artifacts from run {run_id} in {repo}...")
        cmd = ["gh", "run", "download", "-R", repo, run_id, "-D", str(data_dir)]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"gh CLI failed: {error_msg}")


def _pull_with_api(repo: str, artifact: str, run_id: str, data_dir: Path, token: str) -> None:
    """Pull artifact using GitHub API directly."""
    import urllib.request
    import urllib.error
    import json
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    # If run_id provided, get artifacts from that run
    if run_id:
        print(f"Fetching artifacts from run {run_id}...")
        url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts"
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to fetch artifacts: {e.code} {e.reason}")
        
        artifacts = data.get("artifacts", [])
        if not artifacts:
            raise ValueError(f"No artifacts found for run {run_id}")
        
        # Use the first artifact or find by name
        if artifact:
            matching = [a for a in artifacts if a["name"] == artifact]
            if not matching:
                available = [a["name"] for a in artifacts]
                raise ValueError(f"Artifact '{artifact}' not found. Available: {available}")
            artifact_info = matching[0]
        else:
            artifact_info = artifacts[0]
            print(f"Using artifact: {artifact_info['name']}")
        
        artifact_id = artifact_info["id"]
    else:
        # Search for artifact by name across all runs
        print(f"Searching for artifact '{artifact}'...")
        url = f"https://api.github.com/repos/{repo}/actions/artifacts?name={artifact}"
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to search artifacts: {e.code} {e.reason}")
        
        artifacts = data.get("artifacts", [])
        if not artifacts:
            raise ValueError(f"Artifact '{artifact}' not found in {repo}")
        
        # Use the most recent one
        artifact_info = artifacts[0]
        artifact_id = artifact_info["id"]
    
    # Download the artifact
    print(f"Downloading artifact (ID: {artifact_id})...")
    download_url = f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    req = urllib.request.Request(download_url, headers=headers)
    
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        try:
            with urllib.request.urlopen(req) as response:
                tmp_file.write(response.read())
            tmp_path = tmp_file.name
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to download artifact: {e.code} {e.reason}")
    
    # Extract the artifact
    try:
        print(f"Extracting to {data_dir}...")
        with zipfile.ZipFile(tmp_path, 'r') as zipf:
            zipf.extractall(data_dir)
    finally:
        os.unlink(tmp_path)


def main() -> NoReturn:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='containerized-strands-agents',
        description='CLI for managing containerized Strands agent snapshots'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Snapshot command
    snapshot_parser = subparsers.add_parser(
        'snapshot',
        help='Create a snapshot (zip archive) of an agent data directory'
    )
    snapshot_parser.add_argument(
        '--data-dir',
        required=True,
        help='Path to the agent data directory to snapshot'
    )
    snapshot_parser.add_argument(
        '--output',
        required=True,
        help='Path to the output zip file (e.g., snapshot.zip)'
    )
    
    # Restore command
    restore_parser = subparsers.add_parser(
        'restore',
        help='Restore an agent from a snapshot (zip archive)'
    )
    restore_parser.add_argument(
        '--snapshot',
        required=True,
        help='Path to the snapshot zip file'
    )
    restore_parser.add_argument(
        '--data-dir',
        required=True,
        help='Path to the target directory to restore the agent'
    )
    
    # Run command
    run_parser = subparsers.add_parser(
        'run',
        help='Run an agent with a message'
    )
    run_parser.add_argument(
        '--data-dir',
        required=True,
        help='Path to the agent data directory'
    )
    run_parser.add_argument(
        '--message',
        required=True,
        help='Message to send to the agent'
    )
    run_parser.add_argument(
        '--system-prompt',
        help='Optional custom system prompt'
    )
    
    # Pull command
    pull_parser = subparsers.add_parser(
        'pull',
        help='Pull agent state from GitHub Actions artifact'
    )
    pull_parser.add_argument(
        '--repo',
        required=True,
        help='Repository in owner/repo format'
    )
    pull_parser.add_argument(
        '--artifact',
        help='Artifact name to download'
    )
    pull_parser.add_argument(
        '--run-id',
        help='Run ID to download artifacts from'
    )
    pull_parser.add_argument(
        '--data-dir',
        help='Target directory to extract to (default: ./agent-data)'
    )
    pull_parser.add_argument(
        '--token',
        help='GitHub token (uses GITHUB_TOKEN env var if not provided)'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if args.command == 'snapshot':
        snapshot_command(args.data_dir, args.output)
    elif args.command == 'restore':
        restore_command(args.snapshot, args.data_dir)
    elif args.command == 'run':
        run_command(args.data_dir, args.message, args.system_prompt)
    elif args.command == 'pull':
        pull_command(
            repo=args.repo,
            artifact=args.artifact,
            run_id=args.run_id,
            data_dir=args.data_dir,
            token=args.token,
        )
    else:
        parser.print_help()
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
