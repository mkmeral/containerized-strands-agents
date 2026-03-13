"""GitHub tool for Strands Agents.

A single unified tool that provides comprehensive GitHub repository operations
including issues, pull requests, comments, reviews, and repository management.

Supported actions:
  Issues: create_issue, get_issue, update_issue, list_issues, get_issue_comments, add_issue_comment
  PRs: create_pull_request, get_pull_request, update_pull_request, list_pull_requests
  Reviews: get_pr_review_and_comments, reply_to_review_comment
"""

import json
import os
import traceback
from datetime import datetime
from typing import Any

import requests
from strands import tool

GITHUB_TOKEN_VAR = "CONTAINERIZED_AGENTS_GITHUB_TOKEN"

ACTIONS = [
    "create_issue",
    "get_issue",
    "update_issue",
    "list_issues",
    "get_issue_comments",
    "add_issue_comment",
    "create_pull_request",
    "get_pull_request",
    "update_pull_request",
    "list_pull_requests",
    "get_pr_review_and_comments",
    "reply_to_review_comment",
]


def _github_request(
    method: str, endpoint: str, repo: str, data: dict | None = None, params: dict | None = None
) -> dict[str, Any] | list | str:
    """Make a GitHub API request."""
    token = os.environ.get(GITHUB_TOKEN_VAR)
    if not token:
        return f"Error: {GITHUB_TOKEN_VAR} environment variable not found"

    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    response = requests.request(method, url, headers=headers, json=data, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _resolve_repo(repo: str | None) -> str | None:
    """Resolve repo from parameter or environment."""
    return repo or os.environ.get("GITHUB_REPOSITORY")


def _create_issue(repo: str, title: str, body: str = "") -> str:
    result = _github_request("POST", "issues", repo, {"title": title, "body": body})
    if isinstance(result, str):
        return result
    return f"Issue created: #{result['number']} - {result['html_url']}"


def _get_issue(repo: str, issue_number: int) -> str:
    result = _github_request("GET", f"issues/{issue_number}", repo)
    if isinstance(result, str):
        return result
    return (
        f"#{result['number']} - {result['title']}\n"
        f"State: {result['state']}\n"
        f"Author: {result['user']['login']}\n"
        f"URL: {result['html_url']}\n\n{result['body']}"
    )


def _update_issue(repo: str, issue_number: int, title: str | None = None, body: str | None = None, state: str | None = None) -> str:
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if state is not None:
        data["state"] = state
    if not data:
        return "Error: At least one field (title, body, or state) must be provided"
    result = _github_request("PATCH", f"issues/{issue_number}", repo, data)
    if isinstance(result, str):
        return result
    return f"Issue updated: #{result['number']} - {result['html_url']}"


def _list_issues(repo: str, state: str = "open") -> str:
    result = _github_request("GET", "issues", repo, params={"state": state})
    if isinstance(result, str):
        return result
    issues = [i for i in result if "pull_request" not in i]
    if not issues:
        return f"No {state} issues found in {repo}"
    output = f"Issues ({state}) in {repo}:\n"
    for issue in issues:
        output += f"#{issue['number']} - {issue['title']} by {issue['user']['login']} - {issue['html_url']}\n"
    return output


def _get_issue_comments(repo: str, issue_number: int, since: str | None = None) -> str:
    params = {"since": since} if since else None
    result = _github_request("GET", f"issues/{issue_number}/comments", repo, params=params)
    if isinstance(result, str):
        return result
    if not result:
        return f"No comments found for issue #{issue_number}" + (f" updated after {since}" if since else "")
    output = f"Comments for issue #{issue_number}:\n"
    for comment in result:
        output += f"{comment['user']['login']} - updated: {comment['updated_at']}\n{comment['body']}\n\n"
    return output


def _add_issue_comment(repo: str, issue_number: int, comment_text: str) -> str:
    result = _github_request("POST", f"issues/{issue_number}/comments", repo, {"body": comment_text})
    if isinstance(result, str):
        return result
    return f"Comment added successfully: {result['html_url']} (created: {result['created_at']})"


def _create_pull_request(repo: str, title: str, head: str, base: str, body: str = "") -> str:
    result = _github_request("POST", "pulls", repo, {"title": title, "head": head, "base": base, "body": body})
    if isinstance(result, str):
        return result
    return f"Pull request created: #{result['number']} - {result['html_url']}"


def _get_pull_request(repo: str, pr_number: int) -> str:
    result = _github_request("GET", f"pulls/{pr_number}", repo)
    if isinstance(result, str):
        return result
    return (
        f"#{result['number']} - {result['title']}\n"
        f"State: {result['state']}\n"
        f"Author: {result['user']['login']}\n"
        f"Head: {result['head']['ref']} -> Base: {result['base']['ref']}\n"
        f"URL: {result['html_url']}\n\n{result['body']}"
    )


def _update_pull_request(repo: str, pr_number: int, title: str | None = None, body: str | None = None, base: str | None = None) -> str:
    data = {}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    if base is not None:
        data["base"] = base
    if not data:
        return "Error: At least one field (title, body, or base) must be provided"
    result = _github_request("PATCH", f"pulls/{pr_number}", repo, data)
    if isinstance(result, str):
        return result
    return f"Pull request updated: #{result['number']} - {result['html_url']}"


def _list_pull_requests(repo: str, state: str = "open") -> str:
    result = _github_request("GET", "pulls", repo, params={"state": state})
    if isinstance(result, str):
        return result
    if not result:
        return f"No {state} pull requests found in {repo}"
    output = f"Pull Requests ({state}) in {repo}:\n"
    for pr in result:
        output += f"#{pr['number']} - {pr['title']} by {pr['user']['login']} - {pr['html_url']}\n"
    return output


def _get_pr_review_and_comments(repo: str, pr_number: int, show_resolved: bool = False, since: str | None = None) -> str:
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

    response = requests.post(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if "errors" in data:
        return f"GraphQL Error: {data['errors']}"

    pr_data = data["data"]["repository"]["pullRequest"]

    if since:
        cutoff = datetime.fromisoformat(since.replace("Z", "+00:00"))
        filtered_threads = []
        for thread in pr_data["reviewThreads"]["nodes"]:
            has_newer = any(
                datetime.fromisoformat(c["updatedAt"].replace("Z", "+00:00")) > cutoff
                for c in thread["comments"]["nodes"]
            )
            if has_newer:
                filtered_threads.append(thread)
        pr_data["reviewThreads"]["nodes"] = filtered_threads
        pr_data["comments"]["nodes"] = [
            c for c in pr_data["comments"]["nodes"]
            if datetime.fromisoformat(c["updatedAt"].replace("Z", "+00:00")) > cutoff
        ]

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
        review_data = review_info["review_data"]
        output += f"Review [Review ID: {review_id}]\n"
        if review_data.get("author"):
            output += f"   Review by {review_data['author']['login']} (updated: {review_data['updatedAt']})\n"
        if review_data.get("body"):
            output += f"   Review Comment:\n      {review_data['body']}\n"
        output += "\n"

        for thread in review_info["threads"]:
            first_comment = thread["comments"]["nodes"][0]
            line_info = f":{first_comment['line']}" if first_comment.get("line") else " (Comment on file)"
            status = "RESOLVED" if thread["isResolved"] else "OPEN"
            output += f"   Thread ({status}): {first_comment['path']}{line_info}\n"

            comments = thread["comments"]["nodes"]
            root_comments = [c for c in comments if not c.get("replyTo")]

            for root_comment in root_comments:
                output += f"      {root_comment['author']['login']} (updated: {root_comment['updatedAt']}) [Comment ID: {root_comment['fullDatabaseId']}]:\n"
                output += f"         {root_comment['body']}\n"
                replies = [c for c in comments if c.get("replyTo") and c["replyTo"].get("id") == root_comment["id"]]
                for reply in replies:
                    output += f"         -> {reply['author']['login']} (updated: {reply['updatedAt']}):\n"
                    output += f"           {reply['body']}\n"
            output += "\n"
        output += "\n"

    if pr_data["comments"]["nodes"]:
        for comment in pr_data["comments"]["nodes"]:
            output += f"Comment by {comment['author']['login']} (updated: {comment['updatedAt']})\n"
            output += f"   {comment['body']}\n\n"

    return output


def _reply_to_review_comment(repo: str, pr_number: int, comment_id: int, reply_text: str) -> str:
    result = _github_request("POST", f"pulls/{pr_number}/comments/{comment_id}/replies", repo, {"body": reply_text})
    if isinstance(result, str):
        return result
    return f"Reply added to review comment: {result['html_url']}"


# Action dispatcher
_ACTION_MAP = {
    "create_issue": _create_issue,
    "get_issue": _get_issue,
    "update_issue": _update_issue,
    "list_issues": _list_issues,
    "get_issue_comments": _get_issue_comments,
    "add_issue_comment": _add_issue_comment,
    "create_pull_request": _create_pull_request,
    "get_pull_request": _get_pull_request,
    "update_pull_request": _update_pull_request,
    "list_pull_requests": _list_pull_requests,
    "get_pr_review_and_comments": _get_pr_review_and_comments,
    "reply_to_review_comment": _reply_to_review_comment,
}


@tool
def use_github(action: str, repo: str | None = None, **kwargs) -> str:
    """Perform GitHub operations on repositories.

    Actions and their parameters:
      create_issue: title (str), body (str, optional)
      get_issue: issue_number (int)
      update_issue: issue_number (int), title (str, optional), body (str, optional), state (str, optional)
      list_issues: state (str, default "open")
      get_issue_comments: issue_number (int), since (str, optional)
      add_issue_comment: issue_number (int), comment_text (str)
      create_pull_request: title (str), head (str), base (str), body (str, optional)
      get_pull_request: pr_number (int)
      update_pull_request: pr_number (int), title (str, optional), body (str, optional), base (str, optional)
      list_pull_requests: state (str, default "open")
      get_pr_review_and_comments: pr_number (int), show_resolved (bool, default False), since (str, optional)
      reply_to_review_comment: pr_number (int), comment_id (int), reply_text (str)

    Args:
        action: The GitHub action to perform. One of: create_issue, get_issue, update_issue,
            list_issues, get_issue_comments, add_issue_comment, create_pull_request,
            get_pull_request, update_pull_request, list_pull_requests,
            get_pr_review_and_comments, reply_to_review_comment
        repo: GitHub repository in "owner/repo" format. Falls back to GITHUB_REPOSITORY env var.
        **kwargs: Action-specific parameters (see above).

    Returns:
        Result string from the GitHub operation.
    """
    resolved_repo = _resolve_repo(repo)
    if not resolved_repo:
        return "Error: repo not provided and GITHUB_REPOSITORY environment variable not set"

    handler = _ACTION_MAP.get(action)
    if not handler:
        return f"Error: Unknown action '{action}'. Valid actions: {', '.join(ACTIONS)}"

    try:
        return handler(resolved_repo, **kwargs)
    except Exception as e:
        return f"Error: {e!s}\n\nStack trace:\n{traceback.format_exc()}"
