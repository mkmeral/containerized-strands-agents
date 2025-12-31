#!/usr/bin/env python3
"""CLI commands for containerized-strands-agents snapshot management."""

import argparse
import sys
import zipfile
from pathlib import Path
from typing import NoReturn


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
    
    # Parse arguments
    args = parser.parse_args()
    
    # Execute command
    if args.command == 'snapshot':
        snapshot_command(args.data_dir, args.output)
    elif args.command == 'restore':
        restore_command(args.snapshot, args.data_dir)
    else:
        parser.print_help()
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
