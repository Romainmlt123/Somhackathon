"""Journal d'observabilité de l'agent : une ligne JSON par événement, un fichier par lancement.

Chaque ligne porte `n` (rang dans le lancement), `t` (heure locale, s), `run` et `ev` :

- `in`      : message reçu du serveur, avant tri par l'Inbox (ce que l'habitant perçoit) ;
- `handled` : message effectivement passé à `decide` (ce que l'agent a traité) ;
- `out`     : commande envoyée (ce que l'agent fait) ;
- `why`     : raison d'une décision, écrite par `agent.py` ;
- `llm`, `llm_error` : appel au modèle, prompt et réponse compris ;
- `state`   : mémoire interne de l'agent, à intervalle régulier ;
- `session` : connexion, déconnexion, erreur.

Le graphe de connaissances (`graphe.py`) se reconstruit à partir de ces seules lignes :
on peut donc corriger ses règles et le recalculer après une manche.

Variables d'environnement : `TRACE=0` coupe le journal, `TRACE_DIR` (défaut `traces`),
`TRACE_SCAN_S` (défaut 1.0) : au plus un `scan` journalisé par période.
"""

import json
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

ENABLED = os.getenv("TRACE", "1") != "0"
RUN_ID = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
TRACE_DIR = Path(os.getenv("TRACE_DIR", "traces"))
SCAN_PERIOD_S = float(os.getenv("TRACE_SCAN_S", "1.0"))

# Clés jamais écrites, où qu'elles soient dans un message.
_SECRETS = {"authorization", "team_token", "token", "api_key"}

_file = None
_n = 0
_last_scan = 0.0
_listeners = []
# Mémoire vive des derniers événements, interrogeable par les décisions.
_recent = deque(maxlen=int(os.getenv("TRACE_MEMOIRE", "2000")))
# Les appels au modèle journalisent depuis un thread (asyncio.to_thread).
_lock = threading.Lock()


def path():
    return TRACE_DIR / f"{RUN_ID}.jsonl"


def _open():
    global _file
    if _file is None:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        # buffering=1 : chaque ligne est écrite tout de suite, `tail -f` fonctionne.
        _file = open(path(), "a", buffering=1, encoding="utf-8")
    return _file


def _clean(value):
    if isinstance(value, dict):
        return {
            k: ("***" if str(k).lower() in _SECRETS else _clean(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def subscribe(listener):
    """`listener(record)` est appelé pour chaque ligne, par exemple par le graphe."""
    _listeners.append(listener)


def event(ev, **fields):
    """Écrit un événement et le transmet aux abonnés. Ne lève jamais d'exception."""
    with _lock:
        return _event(ev, fields)


def _event(ev, fields):
    global _n
    _n += 1
    record = {"n": _n, "t": round(time.time(), 3), "run": RUN_ID, "ev": ev}
    record.update(_clean(fields))
    _recent.append(record)
    if ENABLED:
        try:
            _open().write(
                json.dumps(record, ensure_ascii=False, default=str) + "\n"
            )
        except OSError:
            pass
    for listener in _listeners:
        try:
            listener(record)
        except Exception as exc:  # un abonné fautif ne doit pas tuer l'agent
            if ENABLED:
                _open().write(
                    json.dumps(
                        {"n": _n, "t": time.time(), "run": RUN_ID,
                         "ev": "listener_error", "error": repr(exc)},
                        ensure_ascii=False,
                    ) + "\n"
                )
    return record


def recent(ev=None, type=None, since_s=None, limit=50):
    """Derniers événements en mémoire, du plus ancien au plus récent.

    `recent(ev="in", type="sound", since_s=60)` : ce qui a été entendu depuis une minute.
    Fonctionne même avec `TRACE=0` (le fichier n'est alors pas écrit).
    """
    seuil = time.time() - since_s if since_s else None
    with _lock:
        items = [
            r for r in _recent
            if (ev is None or r["ev"] == ev)
            and (type is None or r.get("type") == type)
            and (seuil is None or r["t"] >= seuil)
        ]
    return items[-limit:]


def perceive(frame):
    """Message reçu du serveur. Les `scan` arrivent plusieurs fois par seconde : échantillonnés."""
    global _last_scan
    if frame.get("type") == "scan":
        now = time.time()
        if now - _last_scan < SCAN_PERIOD_S:
            return None
        _last_scan = now
    return event(
        "in",
        type=frame.get("type"),
        seq=frame.get("seq"),
        server_ms=frame.get("time_ms"),
        data=frame.get("data"),
    )


def handled(frame):
    return event("handled", type=frame.get("type"), seq=frame.get("seq"))


def act(kind, command_id, data):
    return event("out", type=kind, command_id=command_id, data=data)


def why(decision, **context):
    """Raison d'une décision : `why("turn", reason="obstacle", front_m=1.2)`."""
    return event("why", decision=decision, **context)


def state(**memory):
    return event("state", **memory)


def session(phase, **fields):
    return event("session", phase=phase, **fields)


def close():
    global _file
    if _file is not None:
        _file.close()
        _file = None
