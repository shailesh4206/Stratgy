import asyncio
import random
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

from utils.logger import setup_logger

logger = setup_logger("http")


@dataclass(frozen=True)
class HttpRetryPolicy:
    total_retries: int = 3
    base_backoff_s: float = 0.5
    max_backoff_s: float = 8.0


class HttpClient:
    """Shared aiohttp session + connector with strict resolver policy.

    Production rules (per task):
      - one shared ClientSession
      - one shared TCPConnector with ThreadedResolver
      - no default connector
    """

    def __init__(
        self,
        *,
        request_timeout_s: float = 20.0,
        retry_policy: Optional[HttpRetryPolicy] = None,
        max_connections_per_host: int = 10,
        dns_ttl_cache_s: int = 300,
    ):
        self._lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None

        self._timeout = aiohttp.ClientTimeout(total=request_timeout_s)
        self._retry_policy = retry_policy or HttpRetryPolicy(total_retries=3)

        # REQUIRED connector policy
        self._connector = aiohttp.TCPConnector(
            resolver=aiohttp.ThreadedResolver(),
            ttl_dns_cache=dns_ttl_cache_s,
            limit=max_connections_per_host,
            enable_cleanup_closed=True,
        )

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            raise RuntimeError("HttpClient session not initialized")
        return self._session

    async def ensure_session(self) -> aiohttp.ClientSession:
        async with self._lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=self._timeout,
                    connector=self._connector,
                    headers={
                        "User-Agent": "traderoom-bot/1.0",
                        "Accept": "application/json",
                    },
                )
        return self._session

    async def close(self) -> None:
        async with self._lock:
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._session = None

    def connector_config_summary(self) -> dict[str, Any]:
        return {
            "resolver": "aiohttp.ThreadedResolver()",
            "ttl_dns_cache": getattr(self._connector, "ttl_dns_cache", None),
            "limit": getattr(self._connector, "limit", None),
            "enable_cleanup_closed": getattr(self._connector, "_cleanup_closed", None),
        }

    async def request_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        method: str = "GET",
        timeout: Optional[aiohttp.ClientTimeout] = None,
        headers: Optional[dict[str, str]] = None,
        expected_status: int | tuple[int, ...] = (200,),
        log_ctx: str = "",
    ) -> Optional[Any]:

        """Retries with exponential backoff for JSON endpoints."""
        await self.ensure_session()
        timeout = timeout or self._timeout

        retries = self._retry_policy.total_retries
        last_exc: Exception | None = None

        for attempt in range(retries):
            try:
                session = self.session
                req_timeout = timeout

                async with session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=req_timeout,
                ) as resp:
                    if isinstance(expected_status, tuple):
                        ok = resp.status in expected_status
                    else:
                        ok = resp.status == expected_status

                    if not ok:
                        # Preserve response details for forensic debugging.
                        try:
                            text = await resp.text()
                        except Exception:
                            text = "<failed to read response text>"
                        try:
                            body_json = await resp.json(content_type=None)
                        except Exception:
                            body_json = None

                        logger.warning(
                            "HTTP JSON non-OK status={status} url={url} attempt={att}/{retries} ctx={ctx} body_json={body_json} body_text={body_text}".format(
                                status=resp.status,
                                url=url,
                                att=attempt + 1,
                                retries=retries,
                                ctx=log_ctx,
                                body_json=body_json,
                                body_text=text[:2000],
                            )
                        )
                        return None

                    data = await resp.json(content_type=None)
                    # Support both dict and list responses across Binance endpoints.
                    if isinstance(data, (dict, list)):
                        return data


                    logger.warning(
                        f"HTTP JSON unexpected type url={url} attempt={attempt+1}/{retries} ctx={log_ctx} type={type(data)}"
                    )
                    return None



            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                backoff = min(
                    self._retry_policy.max_backoff_s,
                    self._retry_policy.base_backoff_s * (2**attempt) + random.random() * 0.25,
                )
                logger.warning(
                    f"HTTP JSON attempt {attempt+1}/{retries} failed: {e}. backoff={backoff:.2f}s url={url} {log_ctx}"
                )
                await asyncio.sleep(backoff)
            except Exception as e:
                last_exc = e
                logger.error(f"HTTP JSON fatal error url={url} {log_ctx}: {e}")
                return None

        if last_exc is not None:
            logger.error(f"HTTP JSON exhausted retries url={url} {log_ctx}: {last_exc}")
        return None

