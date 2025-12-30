from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Callable
from urllib.parse import urlencode

import httpx
import websockets


@dataclass
class ImageResult:
    file_name: str
    subfolder: str
    mime_type: str
    data: bytes


@dataclass
class GenerationResult:
    prompt_id: str
    images: List[ImageResult]
    history: Dict[str, Any]


class ComfyUIClient:
    """Minimal async client for ComfyUI REST + WebSocket APIs."""

    def __init__(
        self,
        api_base: str,
        ws_url: str,
        timeout: float = 60.0,
        *,
        log_level: str = "INFO",
    ):
        self.api_base = api_base.rstrip("/")
        self.ws_url = ws_url.rstrip("/")
        self.timeout = timeout
        self.log_level = log_level.upper()

    async def generate(
        self,
        workflow: Dict[str, Any],
        client_id: str,
        on_prompt_id: Callable[[str], None] | None = None,
    ) -> GenerationResult:
        async with httpx.AsyncClient(
            base_url=self.api_base, http2=True, timeout=self.timeout
        ) as http_client:
            prompt_id = await self._queue_prompt(http_client, workflow, client_id)
            if on_prompt_id:
                on_prompt_id(prompt_id)
            history = await self._wait_for_history(http_client, prompt_id, client_id)
            errors = history.get("errors") or history.get("error")
            if errors:
                raise RuntimeError(f"ComfyUI returned errors: {errors}")
            images = await self._download_images(http_client, history)
            return GenerationResult(prompt_id=prompt_id, images=images, history=history)

    async def fetch_existing(self, prompt_id: str, *, fast: bool = False) -> GenerationResult:
        """Fetch history and images for an already-submitted prompt_id.

        If fast=True, perform a single history fetch and fail fast when images are not ready.
        """

        async with httpx.AsyncClient(
            base_url=self.api_base, http2=True, timeout=self.timeout
        ) as http_client:
            if fast:
                history = await self._fetch_history(http_client, prompt_id)
                outputs = history.get("outputs", {})
                has_images = any(node.get("images") for node in outputs.values())
                if not has_images:
                    raise RuntimeError("ComfyUI history not ready (no images yet)")
            else:
                history = await self._fetch_history_with_retry(http_client, prompt_id)

            errors = history.get("errors") or history.get("error")
            if errors:
                raise RuntimeError(f"ComfyUI returned errors: {errors}")
            images = await self._download_images(http_client, history)
            return GenerationResult(prompt_id=prompt_id, images=images, history=history)

    async def _queue_prompt(
        self, http_client: httpx.AsyncClient, workflow: Dict[str, Any], client_id: str
    ) -> str:
        response = await http_client.post(
            "/prompt", json={"prompt": workflow, "client_id": client_id}
        )
        if self._is_trace:
            self._log("TRACE", f"HTTP POST /prompt -> {response.status_code} {response.text[:300]}")
        if response.status_code >= 400:
            # Include response body for easier debugging in Streamlit UI.
            detail = response.text[:1000]
            raise RuntimeError(
                f"ComfyUI /prompt error {response.status_code}: {detail}"
            )

        data = response.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI response did not include prompt_id")
        return prompt_id

    async def _wait_for_history(
        self, http_client: httpx.AsyncClient, prompt_id: str, client_id: str
    ) -> Dict[str, Any]:
        async def _listen_for_execution() -> str | None:
            ws_url = self._build_ws_url(client_id)
            if self._is_trace:
                self._log("TRACE", f"WS connect {ws_url}")
            try:
                async with websockets.connect(ws_url, open_timeout=10) as websocket:
                    async for message in websocket:
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            # Ignore non-JSON messages (e.g., pings or malformed frames)
                            continue
                        if self._is_trace:
                            self._log("TRACE", f"WS message: {str(payload)[:300]}")
                        event_type = payload.get("type")
                        event_data = payload.get("data", {})
                        if event_type == "executed" and event_data.get("prompt_id") == prompt_id:
                            return "executed"
                        if event_type == "progress_state":
                            nodes = event_data.get("nodes") or {}
                            if nodes and all(
                                node.get("state") == "finished" for node in nodes.values()
                            ):
                                return "progress_state_finished"
            except Exception as exc:  # noqa: BLE001
                if self._is_trace:
                    self._log("TRACE", f"WS listener error: {exc}")
            return None

        history_task = asyncio.create_task(
            self._fetch_history_with_retry(http_client, prompt_id)
        )
        ws_task = asyncio.create_task(_listen_for_execution())

        done, _ = await asyncio.wait(
            {history_task, ws_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if history_task in done:
            ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ws_task
            return history_task.result()

        try:
            return await asyncio.wait_for(history_task, timeout=self.timeout)
        finally:
            ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ws_task

    async def _fetch_history_with_retry(
        self, http_client: httpx.AsyncClient, prompt_id: str
    ) -> Dict[str, Any]:
        """Fetch history until outputs are available or timeout.

        In concurrent runs, the websocket event may arrive before /history is populated.
        This loop keeps polling until outputs contain images or timeout is reached.
        """

        deadline = time.monotonic() + self.timeout
        attempt = 0
        while True:
            attempt += 1
            try:
                history = await self._fetch_history(http_client, prompt_id)
                outputs = history.get("outputs", {})
                has_images = any(node.get("images") for node in outputs.values())
                if has_images:
                    return history
            except RuntimeError:
                # history missing; keep retrying until deadline
                pass

            if time.monotonic() >= deadline:
                raise RuntimeError("ComfyUI history did not populate in time")

            await asyncio.sleep(min(0.5 * attempt, 2.0))

    async def _fetch_history(
        self, http_client: httpx.AsyncClient, prompt_id: str
    ) -> Dict[str, Any]:
        response = await http_client.get(f"/history/{prompt_id}")
        if self._is_trace:
            self._log("TRACE", f"HTTP GET /history/{prompt_id} -> {response.status_code} {response.text[:300]}")
        response.raise_for_status()
        data = response.json()

        # ComfyUI sometimes nests the entry under "history", other times returns a flat object keyed by prompt_id.
        history_container = data.get("history") if isinstance(data, dict) else None
        if isinstance(history_container, dict) and prompt_id in history_container:
            history = history_container[prompt_id]
        elif isinstance(data, dict) and prompt_id in data:
            history = data[prompt_id]
        else:
            raise RuntimeError("ComfyUI history was empty for the prompt")
        return history

    async def _download_images(
        self, http_client: httpx.AsyncClient, history: Dict[str, Any]
    ) -> List[ImageResult]:
        images: List[ImageResult] = []
        outputs = history.get("outputs", {})
        for node in outputs.values():
            for image_meta in node.get("images", []):
                file_name = image_meta.get("filename")
                subfolder = image_meta.get("subfolder", "")
                if not file_name:
                    continue
                url = self._build_image_url(file_name, subfolder)
                response = await http_client.get(url)
                if self._is_trace:
                    self._log(
                        "TRACE",
                        f"HTTP GET {url} -> {response.status_code} bytes={len(response.content)}",
                    )
                response.raise_for_status()
                images.append(
                    ImageResult(
                        file_name=file_name,
                        subfolder=subfolder,
                        mime_type=response.headers.get(
                            "content-type", "application/octet-stream"
                        ),
                        data=response.content,
                    )
                )
        if not images:
            raise RuntimeError(
                "ComfyUI history had no images in outputs; nodes="
                f"{list(history.get('outputs', {}).keys())}"
            )
        return images

    @property
    def _is_trace(self) -> bool:
        return self.log_level == "TRACE"

    def _log(self, level: str, message: str) -> None:
        print(f"[ComfyUIClient {level}] {message}")

    def _build_ws_url(self, client_id: str) -> str:
        if "clientId=" in self.ws_url:
            return self.ws_url
        query = urlencode({"clientId": client_id})
        separator = "&" if "?" in self.ws_url else "?"
        return f"{self.ws_url}{separator}{query}"

    def _build_image_url(self, file_name: str, subfolder: str) -> str:
        params = urlencode(
            {"filename": file_name, "subfolder": subfolder, "type": "output"}
        )
        return f"{self.api_base}/view?{params}"
