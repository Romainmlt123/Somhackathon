"""Appel du modèle via la passerelle de l'équipe (compatible OpenRouter). Le jeton n'apparaît que dans l'en-tête."""
import asyncio
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"   # ~0,05 $ / million de jetons d'entrée


class LLM:
    def __init__(self, model=None, max_tokens=260, temperature=0.7, timeout=12.0):
        self.model = model or os.environ.get("MODEL") or DEFAULT_MODEL
        self.max_tokens, self.temperature, self.timeout = max_tokens, temperature, timeout
        self.calls = 0
        self.cost = 0.0
        self.tokens_in = self.tokens_out = 0

    def _post(self, system, user):
        body = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = Request(os.environ["LLM_GATEWAY_URL"] + "/chat/completions", json.dumps(body).encode(),
                      headers={"Authorization": "Bearer " + os.environ["TEAM_TOKEN"], "Content-Type": "application/json"})
        with urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    async def chat(self, system, user):
        """Renvoie (texte, usage). Lève OSError / ValueError en cas d'échec (crédit épuisé : HTTP 402)."""
        t0 = time.time()
        try:
            data = await asyncio.to_thread(self._post, system, user)
        except HTTPError as e:
            raise OSError(f"HTTP {e.code}") from e
        self.calls += 1
        u = data.get("usage") or {}
        self.cost += float(u.get("cost") or 0)
        self.tokens_in += u.get("prompt_tokens", 0)
        self.tokens_out += u.get("completion_tokens", 0)
        text = (data["choices"][0]["message"].get("content") or "").strip()
        return text, {**u, "latency_s": round(time.time() - t0, 2)}


def parse_json(text):
    """Extrait le premier objet JSON d'une réponse de modèle (tolère le texte autour)."""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("pas de JSON")
    return json.loads(text[a:b + 1])
