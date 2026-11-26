"""Appel du modèle via la passerelle de l'équipe (compatible OpenRouter). Le jeton n'apparaît que dans l'en-tête."""
import asyncio
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import journal

DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"   # ~0,05 $ / million de jetons d'entrée


class LLM:
    def __init__(self, model=None, max_tokens=None, temperature=0.7, timeout=60.0):   # max_tokens=None : aucune limite de réponse
        self.model = model or os.environ.get("MODEL") or DEFAULT_MODEL
        self.max_tokens, self.temperature, self.timeout = max_tokens, temperature, timeout
        self.effort = "none"                # « none » si le modèle l'accepte ; Gemini 4 l'impose : repli sur « minimal »
        self.calls = 0
        self.cost = 0.0
        self.tokens_in = self.tokens_out = 0

    def _post(self, system, user):
        body = {"model": self.model, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        body["reasoning"] = {"effort": self.effort}

        def call():
            req = Request(os.environ["LLM_GATEWAY_URL"] + "/chat/completions", json.dumps(body).encode(),
                          headers={"Authorization": "Bearer " + os.environ["TEAM_TOKEN"], "Content-Type": "application/json"})
            with urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        try:
            return call()
        except HTTPError as e:
            if e.code == 400 and self.effort == "none":      # réflexion obligatoire sur ce modèle : on la réduit au minimum
                self.effort = "minimal"
                body["reasoning"] = {"effort": "minimal"}
                return call()
            raise

    async def chat(self, system, user):
        """Renvoie (texte, usage). Lève OSError / ValueError en cas d'échec (crédit épuisé : HTTP 402)."""
        t0 = time.time()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            data = await asyncio.to_thread(self._post, system, user)
        except Exception as e:
            journal.event("llm_error", model=self.model, messages=messages, error=repr(e),
                          latency_s=round(time.time() - t0, 2))
            if isinstance(e, HTTPError):
                raise OSError(f"HTTP {e.code}") from e
            raise
        self.calls += 1
        u = data.get("usage") or {}
        self.cost += float(u.get("cost") or 0)
        self.tokens_in += u.get("prompt_tokens", 0)
        self.tokens_out += u.get("completion_tokens", 0)
        text = (data["choices"][0]["message"].get("content") or "").strip()
        usage = {**u, "latency_s": round(time.time() - t0, 2)}
        journal.event("llm", model=self.model, messages=messages, answer=text, usage=usage)
        return text, usage


def parse_json(text):
    """Extrait le premier objet JSON d'une réponse de modèle (tolère le texte autour)."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("pas de JSON")
    return json.loads(text[a:b + 1])
