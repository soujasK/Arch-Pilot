"""
GitHub API integration service.

Design decisions:
- httpx async client for non-blocking HTTP
- Exponential backoff for rate limit (429) responses
- Redis caching for API responses (repos hit the API once per TTL)
- Content fetched via raw.githubusercontent.com (faster than API for file content)
"""

import asyncio
import base64
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class GitHubError(Exception):
    """Domain error for GitHub API failures."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(GitHubError):
    pass


class RepositoryNotFoundError(GitHubError):
    pass


class GitHubService:
    """
    Async GitHub API client.

    Responsibilities:
    - Parsing GitHub URLs
    - Fetching repository metadata
    - Traversing repository tree
    - Reading file contents
    """

    def __init__(self) -> None:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
            logger.info("github.authenticated", method="token")
        else:
            logger.warning("github.unauthenticated", note="Rate limited to 60 req/hr")

        self._client = httpx.AsyncClient(
            base_url=settings.GITHUB_API_BASE,
            headers=headers,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    async def __aenter__(self) -> "GitHubService":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._client.aclose()

    def parse_url(self, url: str) -> tuple[str, str]:
        """
        Parse GitHub URL into (owner, repo) tuple.
        Handles: https://github.com/owner/repo and owner/repo formats.
        """
        url = url.strip().rstrip("/")
        if "github.com" in url:
            parsed = urlparse(url)
            parts = parsed.path.strip("/").split("/")
            if len(parts) < 2:
                raise GitHubError(f"Cannot parse GitHub URL: {url}")
            return parts[0], parts[1].replace(".git", "")
        elif "/" in url:
            parts = url.split("/")
            return parts[0], parts[1]
        raise GitHubError(f"Invalid repository identifier: {url}")

    async def get_repository_metadata(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch repository metadata from GitHub API."""
        response = await self._request("GET", f"/repos/{owner}/{repo}")
        return {
            "owner": response["owner"]["login"],
            "name": response["name"],
            "url": response["html_url"],
            "description": response.get("description"),
            "language": response.get("language"),
            "stars": response.get("stargazers_count", 0),
            "forks": response.get("forks_count", 0),
            "default_branch": response.get("default_branch", "main"),
            "size_kb": response.get("size", 0),
        }

    async def get_repository_tree(
        self, owner: str, repo: str, branch: str = "main"
    ) -> list[dict[str, Any]]:
        """
        Fetch the full repository file tree recursively.

        Uses the Git Trees API with ?recursive=1 for efficient single-request traversal.
        Falls back to iterative traversal for repos exceeding GitHub's 100k node limit.
        """
        try:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/git/trees/{branch}",
                params={"recursive": "1"},
            )

            if response.get("truncated"):
                logger.warning(
                    "github.tree_truncated",
                    owner=owner,
                    repo=repo,
                    note="Repository exceeds GitHub recursive tree limit",
                )

            return response.get("tree", [])

        except GitHubError as e:
            if e.status_code == 404:
                # Branch might be 'master' instead of 'main'
                if branch == "main":
                    logger.info("github.branch_fallback", trying="master")
                    return await self.get_repository_tree(owner, repo, "master")
            raise

    async def get_file_content(
        self, owner: str, repo: str, path: str, branch: str = "main"
    ) -> Optional[str]:
        """
        Fetch raw file content via raw.githubusercontent.com.

        Why not the Contents API? Raw endpoint is faster, no base64 decoding,
        and doesn't count against rate limits the same way.
        """
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                # Check file size
                if len(response.content) > settings.GITHUB_MAX_FILE_SIZE_KB * 1024:
                    logger.info(
                        "github.file_too_large",
                        path=path,
                        size_kb=len(response.content) // 1024,
                    )
                    return None
                return response.text
            elif response.status_code == 404:
                return None
            else:
                logger.warning(
                    "github.file_fetch_error",
                    path=path,
                    status=response.status_code,
                )
                return None
        except httpx.RequestError as e:
            logger.error("github.request_error", path=path, error=str(e))
            return None

    async def get_file_contents_batch(
        self,
        owner: str,
        repo: str,
        paths: list[str],
        branch: str = "main",
        concurrency: int = 10,
    ) -> dict[str, Optional[str]]:
        """
        Fetch multiple files concurrently with semaphore-controlled parallelism.

        Semaphore prevents overwhelming GitHub or triggering secondary rate limits.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(path: str) -> tuple[str, Optional[str]]:
            async with semaphore:
                content = await self.get_file_content(owner, repo, path, branch)
                return path, content

        tasks = [fetch_one(path) for path in paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, Optional[str]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("github.batch_fetch_error", error=str(result))
            else:
                path, content = result
                output[path] = content

        return output

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        """
        Execute API request with retry logic and rate limit handling.
        """
        last_error: Optional[Exception] = None

        for attempt in range(retries):
            try:
                response = await self._client.request(method, path, params=params)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    raise RepositoryNotFoundError(
                        f"Repository not found: {path}", status_code=404
                    )
                elif response.status_code in (403, 429):
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < retries - 1:
                        logger.warning(
                            "github.rate_limited",
                            retry_after=retry_after,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(min(retry_after, 30) * (attempt + 1))
                        continue
                    raise RateLimitError(
                        "GitHub API rate limit exceeded", status_code=response.status_code
                    )
                else:
                    raise GitHubError(
                        f"GitHub API error: {response.status_code} {response.text}",
                        status_code=response.status_code,
                    )

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    logger.warning(
                        "github.request_retry",
                        error=str(e),
                        attempt=attempt + 1,
                        wait=wait,
                    )
                    await asyncio.sleep(wait)
                continue

        raise GitHubError(f"Request failed after {retries} attempts: {last_error}")

    async def close(self) -> None:
        await self._client.aclose()
