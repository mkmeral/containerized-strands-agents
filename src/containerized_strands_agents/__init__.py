"""Containerized Strands Agents - MCP server hosting isolated AI agents in Docker containers."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("containerized-strands-agents")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
