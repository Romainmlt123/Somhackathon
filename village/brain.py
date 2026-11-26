"""Cerveau de l'agent : observe, note, décide avec un modèle, puis agit avec le corps (Body).

Boucle : construire un contexte compact (état, ce qu'on voit, ce qu'on entend, mémoire, invitations) ->
un appel au modèle (réponse JSON) -> validation -> exécution par le corps -> résultat réinjecté au tour suivant.
Tout est journalisé (logs/agent-*.jsonl) : contexte envoyé, réponse brute, action, résultat, coût.
"""
import asyncio
import json
import logging
import os
import random
import time
from collections import deque
from pathlib import Path

import journal
import moteur
from graphe import Graphe

from .geometry import local_to_world, polar_to_local
from .llm import parse_json
from .persona import system_prompt
from .rules import Rules

log = logging.getLogger("village.brain")

STATIC = {"house", "door", "bed", "bench", "campfire", "board", "stone", "chapel", "canteen"}
PEOPLE = {"person", "wolf", "game_master", "corpse"}
KNOWN_PLACES = ("campfire", "board", "stone", "chapel", "canteen")


def hhmm(minute):
    return "??:??" if minute is None else f"{int(minute // 60):02d}:{int(minute % 60):02d}"


class Brain:
    def __init__(self, session, body, llm, persona_text, data_dir, log_dir, max_calls=300, min_interval=1.5, graphe=None):
        self.s, self.st, self.b, self.llm = session, session.state, body, llm
        self.persona_text = persona_text
        self.max_calls, self.min_interval = max_calls, min_interval
        self.data_dir = Path(data_dir)
        self.mem_path = self.data_dir / "memory.json"
        self.notes = deque(maxlen=40)          # faits retenus (par le modèle)
        self.sightings = deque(maxlen=40)      # personnes vues (automatique)
        self.people = {}                       # nom -> dernière observation
        self.heard = deque(maxlen=12)
        self.events = deque(maxlen=10)
        self.history = deque(maxlen=6)         # (action, résultat)
        self.last_say = 0.0
        self.fail_streak = 0
        # Graphe de soupçons (partagé avec l'observabilité) et réflexes de parole du moteur de règles.
        self.graphe = graphe or Graphe()
        if graphe is None:
            journal.subscribe(self.graphe.observe)
        self.moteur = moteur.Moteur(self.graphe, secrets=(os.environ.get('TEAM_TOKEN'),))
        self.paroles = deque(maxlen=3)         # réponses du moteur (C6, V5, L11) à dire avant tout
        self.rules = Rules(self)
        self.decisions = open(Path(log_dir) / f"agent-{int(time.time())}.jsonl", "w", buffering=1)
        self._load()

    # ------------------------------------------------------------ mémoire
    def _load(self):
        if self.mem_path.exists():
            try:
                d = json.loads(self.mem_path.read_text())
                self.notes.extend(d.get("notes", []))
                self.people.update(d.get("people", {}))
            except (OSError, ValueError):
                pass

    def _save(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mem_path.write_text(json.dumps({"notes": list(self.notes), "people": self.people}, ensure_ascii=False, indent=1))

    def note(self, text):
        text = (text or "").strip()[:200]
        if text and (not self.notes or self.notes[-1]["txt"] != text):
            self.notes.append({"t": hhmm(self.st.minute), "txt": text})
            log.info("NOTE %s", text)
            self._save()

    # ------------------------------------------------------------ perception passive
    async def observer(self):
        """Note en continu qui est vu, où et quand ; et collecte paroles / événements."""
        seen_at = {}
        while True:
            await asyncio.sleep(1.0)
            w = self.st.world
            for v in list(self.st.visible.values()):
                if v["kind"] == "wolf" and v.get("name") and self.st.role == "wolf":
                    self.rules.meute.add(v["name"])          # un loup ne nomme que ses semblables
                if v["kind"] not in PEOPLE or v["kind"] == "game_master":
                    continue
                key = v.get("name") or f"inconnu({v['kind']} {v['ref'][:4]})"
                near = None
                if w.usable:
                    pt = local_to_world(polar_to_local(v["bearing_deg"], v["distance_m"]), w.pose)
                    cands = [(((pt[0] - lm["x"]) ** 2 + (pt[1] - lm["y"]) ** 2) ** 0.5, r) for r, lm in w.landmarks.items()
                             if lm["kind"] not in ("door", "bed")]
                    if cands and min(cands)[0] < 12:
                        near = min(cands)[1]
                prev = self.people.get(key)
                if prev is None or time.time() - seen_at.get(key, 0) > 45 or prev.get("near") != near:
                    seen_at[key] = time.time()
                    txt = f"{hhmm(self.st.minute)} {key} vu" + (f" près de {near}" if near else "") + (f" ({v.get('posture')})" if v.get("posture") else "")
                    self.sightings.append(txt)
                    self.people[key] = {"t": hhmm(self.st.minute), "near": near, "kind": v["kind"]}

    async def listen(self):
        """Consomme la file d'événements du serveur."""
        while True:
            f = await self.s.events.get()
            journal.handled(f)
            k, d = f["type"], f["data"]
            self.rules.on_event(k, d)
            self.sync_clock()
            if k == 'game_event':
                self.moteur.evenement(d)
            elif k == 'sound' and d.get('kind') == 'speech':
                reponse = self.moteur.entendre(d, self.st.me.get('name'), self.st.role)
                if reponse:
                    self.paroles.append(reponse)
            if k == "sound" and d.get("kind") == "speech":
                who = d.get("speaker_name") or ("un loup" if d.get("speaker_ref") and d.get("source") != "game_master" else None)
                if d.get("source") == "game_master":
                    who = "Maître du jeu"
                self.heard.append(f"{hhmm(self.st.minute)} {who or 'quelqu’un'} ({d.get('sector', '?')}, {d.get('volume')}): {d.get('text', '')[:160]}")
                self.wake.set()
            elif k == "game_event":
                self.events.append(f"{hhmm(self.st.minute)} {d.get('kind')}: {d.get('text') or json.dumps({x: y for x, y in d.items() if x != 'kind'}, ensure_ascii=False)[:140]}")
            elif k == "decision_request":
                self.wake.set()

    def sync_clock(self):
        """L'horloge de l'état (extrapolée) alimente le moteur de règles."""
        if self.st.minute is not None:
            self.graphe.minute = int(self.st.minute) % 1440

    def parole_moteur(self):
        """Parole décidée par les règles (réponse, fait observé, annonce de la Voyante), ou None."""
        if time.time() - self.last_say <= 2.2 or self.st.posture == 'sleeping':
            return None
        self.sync_clock()
        if self.paroles:
            return self.paroles.popleft()
        m, nom, role = self.st.minute, self.st.me.get('name'), self.st.role
        if m is None:
            return None
        if 'council' in self.st.zones and moteur.CONSEIL <= m < moteur.VOTE_FIN:
            return self.moteur.au_conseil(nom, role)
        if 'challenge' in self.st.zones:
            return self.moteur.a_l_epreuve(nom, role)
        return None

    # ------------------------------------------------------------ contexte
    def context(self):
        st, w = self.st, self.st.world
        w.advance()
        me = st.me
        lines = [f"HEURE {hhmm(st.minute)} ({'NUIT' if st.is_night() else 'jour'}) — jour {st.clock.get('day')} — manche: "
                 f"{(st.round or {}).get('mode', 'aucune')}",
                 f"TOI: {me.get('name')} | rôle={me.get('role')} forme={me.get('form')} posture={st.posture} zones={st.zones} "
                 f"maison={me.get('home')} fatigue={me.get('fatigue')} pouvoirs={me.get('powers') or {}}"]
        vis = sorted(st.visible.values(), key=lambda v: v["distance_m"])
        rows = []
        for v in vis:
            if v["kind"] in ("house", "door", "bed") and len([r for r in rows if r[1] == v["kind"]]) >= 3:
                continue
            extra = v.get("name") or ""
            if v.get("posture") and v["kind"] in PEOPLE:
                extra += f" [{v['posture']}]"
            rows.append((v["ref"], v["kind"], f"{v['ref']} ({v['kind']}{' ' + extra if extra else ''}) angle {v['bearing_deg']:.0f}° dist {v['distance_m']:.1f} m"))
        lines.append("TU VOIS: " + ("; ".join(r[2] for r in rows[:16]) if rows else "rien d'identifiable"))
        places = []
        if w.usable:
            home = self.b.home_ref()
            for r in list(KNOWN_PLACES) + ([home] if home else []):
                p = w.polar_to(r)
                if p and (r not in st.visible):
                    places.append(f"{r}: angle {p[0]:.0f}° dist {p[1]:.0f} m")
            if places:
                lines.append("LIEUX CONNUS (hors de vue): " + "; ".join(places))
        else:
            lines.append("POSITION incertaine (fais un tour d'horizon: action tourner, ou explorer).")
        if self.heard:
            lines.append("ENTENDU RÉCEMMENT:\n  " + "\n  ".join(list(self.heard)[-6:]))
        if self.events:
            lines.append("ÉVÉNEMENTS:\n  " + "\n  ".join(list(self.events)[-5:]))
        if self.sightings:
            lines.append("PERSONNES VUES (auto):\n  " + "\n  ".join(list(self.sightings)[-8:]))
        if self.notes:
            lines.append("TES NOTES:\n  " + "\n  ".join(f"[{n['t']}] {n['txt']}" for n in list(self.notes)[-12:]))
        for rid, rq in st.requests.items():
            left = max(0, (rq["deadline_ms"] - st.now_ms()) / 1000)
            acts = []
            for a in rq.get("actions", []):
                ch = ", ".join(f"{c['choice_id']}={c['label']}" for c in a.get("choices", []))
                acts.append(f"{a['action']}[{a.get('format')}]" + (f" choix: {ch}" if ch else ""))
            extra = f" ÉNONCÉ: {rq['prompt'][:700]}" if rq.get("prompt") else ""
            lines.append(f"INVITATION URGENTE request_id={rid} type={rq.get('kind')} reste {left:.0f}s — {' | '.join(acts)}{extra}")
        if self.history:
            lines.append("TES DERNIÈRES ACTIONS:\n  " + "\n  ".join(f"{a} -> {r}" for a, r in self.history))
        lines.append("Que fais-tu maintenant ? Réponds par le JSON.")
        return "\n".join(lines)

    # ------------------------------------------------------------ décision
    async def decide(self):
        ctx = self.context()
        system = system_prompt(self.st.me.get("name", "l'habitant"), self.persona_text, self.st.role)
        raw, usage, d, err = "", {}, None, None
        if self.llm.calls >= self.max_calls:
            err = "budget d'appels épuisé"
        else:
            try:
                raw, usage = await self.llm.chat(system, ctx)
                d = parse_json(raw)
            except (OSError, ValueError, KeyError) as e:
                err = repr(e)
        if d is None:
            d = {"pensee": f"(modèle indisponible: {err})", "action": "attendre", "duree": 3}
        return ctx, raw, usage, d, err

    async def execute(self, d):
        """Valide et exécute une action ; renvoie un résumé du résultat pour le tour suivant."""
        st, b, w = self.st, self.b, self.st.world
        act = str(d.get("action", "attendre")).strip().lower()
        tgt = str(d.get("cible") or "").strip()
        tgt = self.resolve(tgt)
        known = lambda r: r in st.visible or r in w.landmarks
        if act == "aller":
            if not known(tgt):
                return f"cible inconnue '{tgt}' (choisis une référence listée)"
            ok = await b.goto(tgt, stop=1.5, timeout=45)
            v = st.visible.get(tgt)
            return ("arrivé" if ok else "échec ou interrompu") + (f" (dist {v['distance_m']:.1f} m)" if v else "")
        if act == "entrer":
            return "dedans" if await b.enter(tgt) else "échec (porte non trouvée ou bloquée)"
        if act == "sortir":
            return "dehors" if await b.leave(tgt or b.home_ref() or "") else "échec"
        if act == "asseoir":
            r = await b.sit(tgt if known(tgt) else None)
            return "assis" if r.get("ok") else f"refus {r.get('code')}"
        if act == "lever":
            await b.stand()
            return f"posture={st.posture}"
        if act == "dormir":
            r = await b.sleep()
            return "endormi" if r.get("ok") else f"refus {r.get('code')} (il faut être près d'un lit, chez toi)"
        if act == "rentrer":
            r = await b.go_home()
            return "chez toi" if r.get("ok") else f"refus {r.get('code')}"
        if act == "lire_panneau":
            e = await b.read_board()
            return "panneau: " + (json.dumps([x["text"] for x in e][-6:], ensure_ascii=False) if e else "vide ou introuvable")
        if act == "ecrire_panneau":
            r = await b.write_board(str(d.get("texte") or d.get("dire") or ""))
            return "écrit" if r.get("ok") else f"refus {r.get('code')}"
        if act == "geste":
            r = await b.emote(tgt if tgt in ("dance", "fear", "shrug", "point") else "shrug")
            return "ok" if r.get("ok") else f"refus {r.get('code')}"
        if act == "explorer":
            await b.explore(budget=15)
            return "exploré 15 s"
        if act == "tourner":
            await b.turn(float(d.get("angle") or 90))
            return "tourné"
        if act == "attendre":
            await asyncio.sleep(min(10.0, max(1.0, float(d.get("duree") or 3))))
            return "attendu"
        if act == "transformer":
            r = await b.transform()
            return "transformé en loup" if r.get("ok") else f"refus {r.get('code')}"
        if act == "attaquer":
            if not known(tgt):
                return "cible inconnue"
            r = await b.attack(tgt)
            return "attaque réussie" if r.get("ok") else f"refus {r.get('code')}"
        if act == "repondre":
            rq = st.requests.get(tgt) or (next(iter(st.requests.values())) if st.requests else None)
            if not rq:
                return "aucune invitation ouverte"
            return await self.answer(rq, str(d.get("reponse") or ""))
        return f"action inconnue '{act}'"

    def resolve(self, tgt):
        """Accepte une référence, le nom d'une personne visible, ou « maison 7 » / « 7 » pour une maison."""
        if not tgt or tgt in self.st.visible or tgt in self.st.world.landmarks:
            return tgt
        low = tgt.lower().strip()
        for v in self.st.visible.values():
            if v.get("name") and v["name"].lower() == low:
                return v["ref"]
        digits = "".join(c for c in low if c.isdigit())
        if digits and ("maison" in low or low.startswith(("h", "d-h")) or low.isdigit()):
            return f"d-h{digits}" if low.startswith("d-") or "porte" in low else f"h{digits}"
        return tgt

    async def answer(self, rq, reply):
        act = rq["actions"][0]
        name = act["action"]
        kw = {}
        choices = [c["choice_id"] for c in act.get("choices", [])]
        if act.get("format") == "text":
            kw["text"] = reply
        elif act.get("format") == "multi_choice":
            kw["choice_ids"] = [c.strip() for c in reply.split(",") if c.strip() in choices]
        elif act.get("format") == "choice":
            if reply not in choices:
                low = {c["label"].lower(): c["choice_id"] for c in act.get("choices", [])}
                reply = low.get(reply.lower(), random.choice(choices) if choices else reply)
            kw["choice_id"] = reply
        for attempt in range(3):
            if name == "vote" and "council" not in self.st.zones:
                await self.b.goto("campfire", stop=3.0, timeout=30)
            res = await self.b.respond(rq["request_id"], name, **kw)
            if res.get("ok") or res.get("code") not in ("outside_council", "outside_challenge"):
                return f"{name} -> {'ok' if res.get('ok') else res.get('code')}"
        return f"{name} -> {res.get('code')}"

    # ------------------------------------------------------------ boucle principale
    async def run(self):
        self.wake = asyncio.Event()
        helpers = [asyncio.create_task(self.observer()), asyncio.create_task(self.listen())]
        try:
            while not self.st.alive:
                await self.st.wait_change(1.0)
            log.info("Cerveau actif : %s, modèle %s", self.st.me.get("name"), self.llm.model)
            while True:
                try:
                    if await self.rules.tick():          # gère aussi l'habitant mort (autosauvetage, succession)
                        await asyncio.sleep(0.2)
                        continue
                except Exception:
                    log.exception("erreur de réflexe")
                    await self.b.stop()
                    await asyncio.sleep(1.0)
                    continue
                t0 = time.time()
                ctx, raw, usage, d, err = await self.decide()
                journal.why(str(d.get("action", "attendre")), cible=d.get("cible"), pensee=d.get("pensee"),
                            dire=d.get("dire"), erreur=err, heure=hhmm(self.st.minute))
                say, volume, regle = str(d.get("dire") or "").strip(), d.get("volume"), None
                parole = self.parole_moteur()
                if parole:
                    say, volume, regle = parole.texte, parole.volume, parole.regle
                # C5, C7, L4 : 240 caractères, jamais le jeton, aucun mot qui trahit un loup.
                filtre = moteur.nettoyer(say, self.moteur.secrets, self.st.role, self.rules.meute) if say else None
                if say and filtre is None:
                    journal.why("silence", regle=regle or "L4", brouillon=say[:80])
                say = filtre or ""
                if say and time.time() - self.last_say > 2.2 and self.st.posture != "sleeping" and time.time() > self.rules.mute_until:
                    r = await self.b.speak(say, volume if volume in ("whisper", "say", "shout") else "say")
                    self.last_say = time.time()
                    if r.get("code") == "muted":
                        self.rules.mute_until = time.time() + 60
                    log.info("DIT (%s) %s -> %s", d.get("volume", "say"), say, r.get("ok") or r.get("code"))
                self.note(d.get("note"))
                try:
                    result = self.rules.veto(d) or await asyncio.wait_for(self.execute(d), 80)
                except asyncio.TimeoutError:
                    result = "trop long, interrompu"
                except Exception as e:                      # une erreur de corps ne doit jamais tuer l'agent
                    log.exception("erreur d'exécution")
                    result = f"erreur {e!r}"
                    await self.b.stop()
                bad = result.startswith(("échec", "refus", "cible inconnue", "action inconnue", "erreur"))
                self.fail_streak = self.fail_streak + 1 if bad else 0
                if self.fail_streak >= 3:
                    self.note("Plusieurs échecs de suite : changer de plan (explorer, ou aller ailleurs).")
                    await self.b.explore(budget=8)
                    self.fail_streak = 0
                self.history.append((f"{d.get('action')} {d.get('cible') or ''}".strip(), result))
                journal.event("resultat", action=d.get("action"), cible=d.get("cible"), result=result,
                              cout_total=round(self.llm.cost, 6), appels=self.llm.calls)
                log.info("[%s] %s | %s %s -> %s", hhmm(self.st.minute), d.get("pensee"), d.get("action"), d.get("cible") or "", result)
                self.decisions.write(json.dumps({"t": time.time(), "hour": hhmm(self.st.minute), "context": ctx, "raw": raw,
                                                 "decision": d, "result": result, "usage": usage, "error": err,
                                                 "total_cost": round(self.llm.cost, 6), "calls": self.llm.calls}, ensure_ascii=False) + "\n")
                self.wake.clear()
                if not self.st.requests:
                    try:
                        await asyncio.wait_for(self.wake.wait(), max(0.2, self.min_interval - (time.time() - t0)))
                    except asyncio.TimeoutError:
                        pass
        finally:
            for t in helpers:
                t.cancel()
            self._save()
