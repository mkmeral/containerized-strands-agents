"""GitHub repository management tool for Strands Agents.

This module provides comprehensive GitHub repository operations including issues,
pull requests, comments, and repository management. Supports full GitHub API
integration with rich console output and error handling.

Key Features:
1. List and manage issues and pull requests
2. Add comments to issues and PRs
3. Create, update, and manage issues
4. Create, update, and manage pull requests
5. Get detailed information for specific issues/PRs
6. Manage PR reviews and review comments
7. Get issue and PR comment threads
8. Rich console output with formatted tables
9. Automatic fallback to GITHUB_REPOSITORY environment variable
"""

import os
import traceback
from datetime import datetime
from functools import wraps
from typing import Any

import requests
from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from strands import tool
from strands_tools.utils import console_util

console = console_util.create()

GITHUB_TOKEN_VAR = "CONTAINERIZED_AGENTS_GITHUB_TOKEN"

def log_inputs(func):
    """Decorator to log function inputs in a blue panel."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__.replace('_', ' ').title()
        params = []
        for k, v in kwargs.items():
            if isinstance(v, str) and len(v) > 50:
                params.append(f"{k}='{v[:50]}...'")
            else:
                params.append(f"{k}='{v}'")
        console.print(Panel(", ".join(params), title=f"[bold blue]{func_name}", border_style="blue"))
        return func(*args, **kwargs)
    return wrapper


def _github_request(
    method: str, endpoint: str, repo: str | None = None, data: dict | None = None, params: dict | None = None
) -> dict[str, Any] | str:
    """Make a GitHub API request with common error handling."""
    if repo is None:
        repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return "Error: GITHUB_REPOSITORY environment variable not found"

    token = os.environ.get(GITHUB_TOKEN_VAR)
    if not token:
        return f"Error: {GITHUB_TOKEN_VAR} environment variable not found"

    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, params=params, timeout=30)
        else:
            response = requests.request(method, url, headers=headers, json=data, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return f"Error: {e!s}"


@tool
@log_inputs
def create_issue(title: str, body: str = "", repo: str | None = None) -> str:
    """Creates a new issue in the specified repository."""
    result = _github_request("POST", "issues", repo, {"title": title, "body": body})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Issue created: #{result['number']} - {result['html_url']}"
    console.print(Panel(escape(message), title="[bold green]Success", border_style="green"))
    return message


@tool
@log_inputs
def get_issue(issue_number: int, repo: str | None = None) -> str:
    """Gets details of a specific issue."""
    result = _github_request("GET", f"issues/{issue_number}", repo)
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    details = (
        f"#{result['number']} - {result['title']}\n"
        f"State: {result['state']}\n"
        f"Author: {result['user']['login']}\n"
        f"URL: {result['html_url']}\n\n{result['body']}"
    )
    console.print(Panel(escape(details), title=f"[bold green]Issue #{result['number']}", border_style="blue"))
    return details


@tool
@log_inputs
def update_issue(
    issue_number: int,
    title: str | None = None,
    body: str | None = None,
    state: str | None = None,
    repo: str | None = None,
) -> str:
    """Updates an issue's title, body, or state."""
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if state is not None:
        data["state"] = state

    if not data:
        error_msg = "Error: At least one field (title, body, or state) must be provided"
        console.print(Panel(escape(error_msg), title="[bold red]Error", border_style="red"))
        return error_msg

    result = _github_request("PATCH", f"issues/{issue_number}", repo, data)
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Issue updated: #{result['number']} - {result['html_url']}"
    console.print(Panel(escape(message), title="[bold green]Success", border_style="green"))
    return message


@tool
@log_inputs
def list_issues(state: str = "open", repo: str | None = None) -> str:
    """Lists issues from the specified GitHub repository."""
    result = _github_request("GET", "issues", repo, params={"state": state})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result

    issues = [issue for issue in result if "pull_request" not in issue]
    if not issues:
        message = f"No {state} issues found in {repo or os.environ.get('GITHUB_REPOSITORY')}"
        console.print(Panel(escape(message), title="[bold yellow]Info", border_style="yellow"))
        return message

    table = Table(title=f"Issues ({state})", box=box.DOUBLE)
    table.add_column("Issue #", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Author", style="green")
    table.add_column("URL", style="blue")

    for issue in issues:
        table.add_row(f"#{issue['number']}", issue["title"], issue["user"]["login"], issue["html_url"])

    console.print(table)

    output = f"Issues ({state}) in {repo or os.environ.get('GITHUB_REPOSITORY')}:\n"
    for issue in issues:
        output += f"#{issue['number']} - {issue['title']} by {issue['user']['login']} - {issue['html_url']}\n"
    return output


@tool
@log_inputs
def get_issue_comments(issue_number: int, repo: str | None = None, since: str | None = None) -> str:
    """Gets all comments for a specific issue."""
    params = {"since": since} if since else None
    result = _github_request("GET", f"issues/{issue_number}/comments", repo, params=params)
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result

    if not result:
        message = f"No comments found for issue #{issue_number}" + (f" updated after {since}" if since else "")
        console.print(Panel(escape(message), title="[bold yellow]Info", border_style="yellow"))
        return message

    output = f"Comments for issue #{issue_number}:\n"
    for comment in result:
        output += f"{comment['user']['login']} - updated: {comment['updated_at']}\n{comment['body']}\n\n"
    
    console.print(Panel(escape(output), title=f"[bold green]Issue #{issue_number} Comments", border_style="blue"))
    return output


@tool
@log_inputs
def add_issue_comment(issue_number: int, comment_text: str, repo: str | None = None) -> str:
    """Adds a comment to an issue or pull request."""
    result = _github_request("POST", f"issues/{issue_number}/comments", repo, {"body": comment_text})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Comment added successfully: {result['html_url']} (created: {result['created_at']})"
    console.print(Panel(escape(message), title="[bold green]Success", border_style="green"))
    return message


@tool
@log_inputs
def create_pull_request(title: str, head: str, base: str, body: str = "", repo: str | None = None) -> str:
    """Creates a new pull request."""
    result = _github_request("POST", "pulls", repo, {"title": title, "head": head, "base": base, "body": body})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Pull request created: #{result['number']} - {result['html_url']}"
    console.print(Panel(escape(message), title="[bold green]Success", border_style="green"))
    return message


@tool
@log_inputs
def get_pull_request(pr_number: int, repo: str | None = None) -> str:
    """Gets details of a specific pull request."""
    result = _github_request("GET", f"pulls/{pr_number}", repo)
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    details = (
        f"#{result['number']} - {result['title']}\n"
        f"State: {result['state']}\n"
        f"Author: {result['user']['login']}\n"
        f"Head: {result['head']['ref']} -> Base: {result['base']['ref']}\n"
        f"URL: {result['html_url']}\n\n{result['body']}"
    )
    console.print(Panel(escape(details), title=f"[bold green]PR #{result['number']}", border_style="blue"))
    return details


@tool
@log_inputs
def update_pull_request(
    pr_number: int,
    title: str | None = None,
    body: str | None = None,
    base: str | None = None,
    repo: str | None = None,
) -> str:
    """Updates a pull request's title, body, or base branch."""
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if base is not None:
        data["base"] = base

    if not data:
        error_msg = "Error: At least one field (title, body, or base) must be provided"
        console.print(Panel(escape(error_msg), title="[bold red]Error", border_style="red"))
        return error_msg

    result = _github_request("PATCH", f"pulls/{pr_number}", repo, data)
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Pull request updated: #{result['number']} - {result['html_url']}"
    console.print(Panel(escape(message), title="[bold green]Success", border_style="green"))
    return message


@tool
@log_inputs
def list_pull_requests(state: str = "open", repo: str | None = None) -> str:
    """Lists pull requests from the specified GitHub repository."""
    result = _github_request("GET", "pulls", repo, params={"state": state})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result

    if not result:
        message = f"No {state} pull requests found in {repo or os.environ.get('GITHUB_REPOSITORY')}"
        console.print(Panel(escape(message), title="[bold yellow]Info", border_style="yellow"))
        return message

    table = Table(title=f"Pull Requests ({state})", box=box.DOUBLE)
    table.add_column("PR #", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Author", style="green")
    table.add_column("URL", style="blue")

    for pr in result:
        table.add_row(f"#{pr['number']}", pr["title"], pr["user"]["login"], pr["html_url"])

    console.print(table)

    output = f"Pull Requests ({state}) in {repo or os.environ.get('GITHUB_REPOSITORY')}:\n"
    for pr in result:
        output += f"#{pr['number']} - {pr['title']} by {pr['user']['login']} - {pr['html_url']}\n"
    return output


@tool
@log_inputs
def get_pr_review_and_comments(pr_number: int, show_resolved: bool = False, repo: str | None = None, since: str | None = None) -> str:
    """Gets all review threads and comments for a PR."""
    if repo is None:
        repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return "Error: GITHUB_REPOSITORY environment variable not found"

    token = os.environ.get(GITHUB_TOKEN_VAR)
    if not token:
        return f"Error: {GITHUB_TOKEN_VAR} environment variable not found"

    owner, repo_name = repo.split("/")
    
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes {
              isResolved
              comments(first: 100) {
                nodes {
                  id
                  fullDatabaseId
                  author { login }
                  body
                  updatedAt
                  path
                  line
                  startLine
                  diffHunk
                  replyTo { id }
                  pullRequestReview { 
                    id 
                    body
                    author { login }
                    updatedAt
                  }
                }
              }
            }
          }
          comments(first: 100) {
            nodes {
              author { login }
              body
              updatedAt
            }
          }
        }
      }
    }
    """
    
    variables = {"owner": owner, "name": repo_name, "number": pr_number}
    
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "variables": variables},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            return f"GraphQL Error: {data['errors']}"
            
        pr_data = data["data"]["repository"]["pullRequest"]
        
        if since:
            cutoff = datetime.fromisoformat(since.replace('Z', '+00:00'))
            filtered_threads = []
            for thread in pr_data["reviewThreads"]["nodes"]:
                has_newer_comment = any(datetime.fromisoformat(c['updatedAt'].replace('Z', '+00:00')) > cutoff 
                                      for c in thread["comments"]["nodes"])
                if has_newer_comment:
                    filtered_threads.append(thread)
            pr_data["reviewThreads"]["nodes"] = filtered_threads
            pr_data["comments"]["nodes"] = [c for c in pr_data["comments"]["nodes"] 
                                          if datetime.fromisoformat(c['updatedAt'].replace('Z', '+00:00')) > cutoff]
        
        output = f"Review threads and comments for PR #{pr_number}:\n\n"
        
        review_threads = {}
        for thread in pr_data["reviewThreads"]["nodes"]:
            if not show_resolved and thread["isResolved"]:
                continue
            if thread["comments"]["nodes"]:
                first_comment = thread["comments"]["nodes"][0]
                review_id = first_comment.get("pullRequestReview", {}).get("id", "N/A")
                if review_id not in review_threads:
                    review_threads[review_id] = {"review_data": first_comment.get("pullRequestReview", {}), "threads": []}
                review_threads[review_id]["threads"].append(thread)
        
        for review_id, review_info in review_threads.items():
            review_data = review_info['review_data']
            output += f"Review [Review ID: {review_id}]\n"
            if review_data.get('author'):
                output += f"   Review by {review_data['author']['login']} (updated: {review_data['updatedAt']})\n"
            if review_data.get('body'):
                output += f"   Review Comment:\n      {review_data['body']}\n"
            output += "\n"
            
            for thread in review_info["threads"]:
                first_comment = thread["comments"]["nodes"][0]
                line_info = f":{first_comment['line']}" if first_comment.get('line') else " (Comment on file)"
                status = "RESOLVED" if thread["isResolved"] else "OPEN"
                output += f"   Thread ({status}): {first_comment['path']}{line_info}\n"
                
                comments = thread["comments"]["nodes"]
                root_comments = [c for c in comments if not c.get('replyTo')]
                
                for root_comment in root_comments:
                    output += f"      {root_comment['author']['login']} (updated: {root_comment['updatedAt']}) [Comment ID: {root_comment['fullDatabaseId']}]:\n"
                    output += f"         {root_comment['body']}\n"
                    replies = [c for c in comments if c.get('replyTo') and c['replyTo'].get('id') == root_comment['id']]
                    for reply in replies:
                        output += f"         -> {reply['author']['login']} (updated: {reply['updatedAt']}):\n"
                        output += f"           {reply['body']}\n"
                output += "\n"
            output += "\n"
        
        if pr_data["comments"]["nodes"]:
            for comment in pr_data["comments"]["nodes"]:
                output += f"Comment by {comment['author']['login']} (updated: {comment['updatedAt']})\n"
                output += f"   {comment['body']}\n\n"
        
        console.print(Panel(escape(output), title=f"[bold green]PR #{pr_number} Review Data", border_style="blue"))
        return output
        
    except Exception as e:
        error_msg = f"Error: {e!s}\n\nStack trace:\n{traceback.format_exc()}"
        console.print(Panel(escape(error_msg), title="[bold red]Error", border_style="red"))
        return error_msg


@tool
@log_inputs
def reply_to_review_comment(pr_number: int, comment_id: int, reply_text: str, repo: str | None = None) -> str:
    """Replies to a pull request review comment."""
    result = _github_request("POST", f"pulls/{pr_number}/comments/{comment_id}/replies", repo, {"body": reply_text})
    if isinstance(result, str):
        console.print(Panel(escape(result), title="[bold red]Error", border_style="red"))
        return result
    message = f"Reply added to review comment: {result['html_url']}"
    console.print(Panel(escape(message), title="[bold green]Reply Added", border_style="green"))
    return message