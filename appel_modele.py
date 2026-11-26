"""Appel explicite à un modèle via le crédit de l’équipe."""

import json
import os
import time
from urllib.request import Request, urlopen

from dotenv import load_dotenv

import journal


def complete(model, messages, *, max_tokens=16, timeout=8):
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        # Sans réflexion préalable : elle consommerait les jetons de la réponse.
        "reasoning": {"effort": "none"},
    }
    req = Request(
        os.environ["LLM_GATEWAY_URL"] + "/chat/completions",
        json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + os.environ["TEAM_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    start = time.time()
    try:
        with urlopen(req, timeout=timeout) as response:
            payload = json.load(response)
        answer = payload["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        journal.event("llm_error", model=model, messages=messages, error=repr(exc),
                      latency_s=round(time.time() - start, 2))
        raise
    journal.event("llm", model=model, messages=messages, answer=answer,
                  usage=payload.get("usage"), latency_s=round(time.time() - start, 2))
    return answer


def choose(model, kind, name, role, choices, remarks, timeout, suspicions=""):
    situation = {
        "scrutin": kind,
        "habitant": name,
        "rôle": role,
        "candidats": [v["label"] for v in choices],
        "paroles entendues": remarks,
        # Tiré du graphe de connaissances : probabilité d’être loup et ses motifs.
        "soupçons": suspicions,
    }
    text = complete(
        model,
        [
            {
                "role": "system",
                "content": "Tu joues au Loup-Garou. Choisis un candidat selon ton rôle et tes observations. Réponds uniquement par son numéro, en comptant depuis 1.",
            },
            {"role": "user", "content": json.dumps(situation, ensure_ascii=False)},
        ],
        max_tokens=8,
        timeout=timeout,
    )
    index = int(text.strip())
    if not 1 <= index <= len(choices):
        raise ValueError("Choix indisponible.")
    return choices[index - 1]["choice_id"]


if __name__ == "__main__":
    load_dotenv()
    print(
        complete(
            os.getenv("MODEL", "openai/gpt-6-luna"),
            [{"role": "user", "content": "Salue le village en trois mots."}],
        )
    )
