"""Épreuves IA : outils de calcul exécutés localement, lecture sûre de la facture, sac à dos des provisions.

Le modèle ne sait pas calculer de tête : il choisit un outil et ses arguments, ce module calcule exactement.
"""
import hashlib
import math
import re

import epreuves

DOC_START, DOC_END = "--- DÉBUT DU DOCUMENT ---", "--- FIN DU DOCUMENT ---"


def modpow(a, e, m):
    return pow(int(a), int(e), int(m))


def sha256_hex(text):
    return hashlib.sha256(str(text).encode()).hexdigest()


def sha256_pow(prefix, zeros, limit=20_000_000):
    """Plus petit nonce n tel que sha256(prefix + str(n)) commence par `zeros` zéros hexadécimaux."""
    target = "0" * int(zeros)
    for n in range(limit):
        if hashlib.sha256(f"{prefix}{n}".encode()).hexdigest().startswith(target):
            return n
    raise ValueError("pas de nonce")


def _primes_upto(n):
    n = int(n)
    if n < 2:
        return []
    sieve = bytearray([1]) * (n + 1)
    sieve[0:2] = b"\x00\x00"
    for i in range(2, int(math.isqrt(n)) + 1):
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
    return [i for i, v in enumerate(sieve) if v]


def primes_sum_upto(n):
    """Somme des nombres premiers <= n."""
    return sum(_primes_upto(n))


def primes_sum_first(k):
    """Somme des k premiers nombres premiers."""
    k, limit = int(k), 100
    while True:
        ps = _primes_upto(limit)
        if len(ps) >= k:
            return sum(ps[:k])
        limit *= 2


def knapsack(items, budget):
    """items : [[id, prix, portions], ...]. Renvoie la liste des id qui maximise les portions sans dépasser le budget."""
    budget = int(budget)
    best = {0: (0, [])}                       # coût -> (portions, ids)
    for it in items:
        ident, price, portions = it[0], int(it[1]), float(it[2])
        for cost, (val, ids) in list(best.items()):
            c = cost + price
            if c <= budget and (c not in best or best[c][0] < val + portions):
                best[c] = (val + portions, ids + [ident])
    return max(best.values(), key=lambda t: t[0])[1]


TOOLS = {"modpow": modpow, "sha256": sha256_hex, "sha256_pow": sha256_pow, "primes_sum_upto": primes_sum_upto,
         "primes_sum_first": primes_sum_first, "sac_a_dos": knapsack}
TOOL_HELP = ("modpow(a, e, m)=a^e mod m ; sha256(texte)=empreinte hex ; sha256_pow(prefixe, zeros)=plus petit nonce ; "
             "primes_sum_upto(n)=somme des premiers <= n ; primes_sum_first(k)=somme des k premiers ; "
             "sac_a_dos(items=[[id,prix,portions],...], budget)=liste d'id optimale")


def run_tool(name, args):
    if name not in TOOLS:
        raise ValueError(f"outil inconnu {name}")
    return TOOLS[name](*args) if isinstance(args, (list, tuple)) else TOOLS[name](**args)


def facture_total(prompt):
    """Montant de la ligne « Total à payer » juste sous le tableau (lecture partagée : `epreuves.facture`)."""
    return epreuves.facture(prompt)


def clean_answer(text):
    """Une réponse texte doit être la valeur seule, sans phrase : « 42 » réussit, « Le résultat est 42 » échoue."""
    t = str(text).strip().strip("`\"'")
    if " " in t and re.search(r"\d", t):
        nums = re.findall(r"-?\d[\d.,]*", t)
        if nums:
            return nums[-1].rstrip(".,")
    return t
