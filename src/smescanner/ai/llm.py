"""
Local-LLM client (Ollama first).

Thin wrapper over Ollama's HTTP API so the rest of the system depends on a
2-method interface (``complete`` / ``available``), not on a vendor SDK. Falls
back to a smaller local model, then degrades to ``None`` (templated output)
if no LLM is reachable — the pipeline must never hard-fail because Ollama is down.

Pull models once:  ``ollama pull qwen2.5:14b-instruct``  /  ``ollama pull llama3.1:8b``
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from ..config import get_settings

log = logging.getLogger("smescanner.ai.llm")


class LocalLLM:
    def __init__(self) -> None:
        cfg = get_settings()
        self.base = cfg.llm_base_url.rstrip("/")
        self.model = cfg.llm_model
        self.fallback = cfg.llm_fallback_model
        self.timeout = cfg.llm_timeout
        self.enabled = cfg.llm_enabled

    def available(self) -> bool:
        if not self.enabled:
            return False
        try:
            r = requests.get(f"{self.base}/api/tags", timeout=5)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def complete(self, prompt: str, system: str | None = None,
                 json_mode: bool = False, temperature: float = 0.2) -> Optional[str]:
        """Single-turn completion. Returns None if no model is reachable."""
        if not self.enabled:
            return None
        for model in (self.model, self.fallback):
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "system": system or "",
                    "stream": False,
                    "options": {"temperature": temperature},
                }
                if json_mode:
                    payload["format"] = "json"
                r = requests.post(f"{self.base}/api/generate", json=payload,
                                  timeout=self.timeout)
                r.raise_for_status()
                return r.json().get("response", "").strip()
            except requests.RequestException as exc:
                log.warning("LLM %s failed (%s), trying fallback", model, exc)
                continue
        return None

    def complete_json(self, prompt: str, system: str | None = None) -> Optional[dict]:
        raw = self.complete(prompt, system=system, json_mode=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("LLM returned non-JSON despite json_mode")
            return None
