from __future__ import annotations

import re
from typing import Any

from prediction_store import PredictionStore


class PredictionEngine:
    """Moteur déterministe et explicable. Calibré par l'historique."""

    def __init__(self, store: PredictionStore | None = None):
        self.store = store or PredictionStore()

    # ------------------------------------------------------------------
    # PARSING
    # ------------------------------------------------------------------

    def parse_text(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r", "").replace("\u00a0", " ")
        runners: list[dict[str, Any]] = []
        vus: set[int] = set()

        for raw_line in normalized.split("\n"):
            line = raw_line.strip()
            if not line or len(line) < 4:
                continue

            # Ignorer les entêtes
            low = line.lower()
            if any(kw in low for kw in [
                "liste", "partant", "course", "distance", "prix",
                "réunion", "hippodrome", "corde", "terrain"
            ]) and not re.match(r"^\d", line):
                continue

            # Chercher un numéro au début (1., 1), 1 -, 1  ou 01)
            m = re.match(r"^(\d{1,2})\s*[\.\)\-]?\s+(.+)$", line)
            if not m:
                continue

            number = int(m.group(1))
            if number < 1 or number > 30 or number in vus:
                continue

            rest = m.group(2).strip()

            # Non partant ?
            if re.search(r"\b(NP|Non Partant|Non-partant)\b", rest, re.I):
                vus.add(number)
                continue

            # --- Nom ---
            name = self._extraire_nom(rest)

            # --- Cote ---
            odds = self._extraire_cote(rest, name)

            # --- Driver / Jockey ---
            driver = self._extraire_driver(rest)

            # --- Musique ---
            musique = self._extraire_musique(rest)

            # --- Poids ---
            weight = self._extraire_poids(rest)

            # --- Corde ---
            corde = self._extraire_corde(rest)

            # --- Gains ---
            gains = self._extraire_gains(rest)

            vus.add(number)
            runners.append({
                "number": number,
                "num": number,
                "name": name,
                "nom": name,
                "form": musique,
                "musique": musique,
                "odds": odds,
                "cote": odds,
                "cote_finale": odds,
                "weight": weight,
                "poids": weight,
                "corde": corde,
                "driver": driver,
                "jockey": driver,
                "gains": gains,
                "status": "active",
            })

        return runners

    # ------------------------------------------------------------------
    # HELPERS D'EXTRACTION
    # ------------------------------------------------------------------

    def _extraire_nom(self, rest: str) -> str:
        """Extrait le nom du cheval (majuscules ou Title Case)."""
        # Couper au premier séparateur courant
        coupe = re.split(
            r"\s*[-–—]\s*|\s+cote\s+|\s+driver\s+|\s+jockey\s+|\s+musique\s+|\s+gains\s+|\s*\(|\s+\d{2,3}\s*€",
            rest, maxsplit=1, flags=re.I
        )[0]
        coupe = coupe.strip()

        if not coupe:
            return rest[:40]

        # Prendre les 4 premiers mots maximum
        mots = coupe.split()[:4]
        return " ".join(mots).title()

    def _extraire_cote(self, rest: str, name: str) -> float | None:
        """Cherche une cote après le nom."""
        # 1. Format explicite "cote 24" ou "cote : 24"
        m = re.search(r"cote\s*[:=]?\s*(\d{1,3}(?:[.,]\d)?)", rest, re.I)
        if m:
            return self._to_float(m.group(1))

        # 2. Après le nom, chercher un nombre isolé
        idx = rest.find(name)
        if idx >= 0:
            after = rest[idx + len(name):]
            m = re.search(r"\b(\d{1,3}(?:[.,]\d)?)\b", after)
            if m:
                v = self._to_float(m.group(1))
                if v and 1.01 <= v <= 999:
                    return v

        return None

    def _extraire_driver(self, rest: str) -> str | None:
        m = re.search(
            r"(?:driver|jockey|entraîneur|entraineur)\s*[:=]?\s*"
            r"([A-ZÀ-Ý][A-Za-zÀ-ÿ\.\-' ]{2,40}?)(?=\s*[-–—]|\s+(?:cote|musique|gains|corde|poids)|\s*$)",
            rest, re.I
        )
        if m:
            return m.group(1).strip()
        return None

    def _extraire_musique(self, rest: str) -> list[str]:
        """Cherche une séquence de résultats type 6a 3a 2a 1a 7a ou Da Dm."""
        results = re.findall(r"\b([0-9]{1,2}|[DdAaPp][apm]?)\s*([apm])\b", rest)
        musique = [f"{a}{b}".lower() for a, b in results]
        return musique[:10]

    def _extraire_poids(self, rest: str) -> float | None:
        m = re.search(r"(\d{2}(?:[.,]\d)?)\s*kg", rest, re.I)
        if m:
            return self._to_float(m.group(1))
        return None

    def _extraire_corde(self, rest: str) -> int | None:
        m = re.search(r"corde\s*[:=]?\s*(\d{1,2})", rest, re.I)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None

    def _extraire_gains(self, rest: str) -> int | None:
        m = re.search(r"gains?\s*[:=]?\s*([\d\s]{3,15})", rest, re.I)
        if m:
            try:
                return int(m.group(1).replace(" ", ""))
            except ValueError:
                return None
        return None

    def _to_float(self, value: str) -> float | None:
        try:
            v = float(value.replace(",", ".").replace(" ", ""))
            return v if v > 0 else None
        except (ValueError, AttributeError):
            return None

    # ------------------------------------------------------------------
    # RANKING
    # ------------------------------------------------------------------

    def rank(
        self,
        runners: list[dict[str, Any]],
        race_key: str,
        race_name: str = "Course importée",
        race_date: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if not runners:
            raise ValueError("Aucun partant actif reconnu")

        weights = self.store.weights()
        scored = []

        for runner in runners:
            # Forme (musique)
            form = runner.get("form") or []
            form_score = 0.0
            for index, place in enumerate(form[:5]):
                if isinstance(place, str):
                    # Format "1a", "Da", etc.
                    num = re.sub(r"[^0-9]", "", place)
                    if num:
                        p = int(num)
                        if 1 <= p <= 9:
                            form_score += max(0, 11 - p) * (1 / (index + 1))
                elif isinstance(place, int):
                    if 1 <= place <= 9:
                        form_score += max(0, 11 - place) * (1 / (index + 1))
            form_score = form_score / 10

            # Cote
            odds = runner.get("odds") or runner.get("cote") or runner.get("cote_finale")
            if odds and odds > 0:
                market_score = 1 / odds
            else:
                market_score = 0.05
                odds = 50

            # Poids
            weight = runner.get("weight") or runner.get("poids")
            weight_score = 1 / max(float(weight or 60), 1)

            # Corde
            corde = runner.get("corde") or 8
            corde_score = 1 - abs(corde - 8) / 16

            # Score global
            raw = (
                weights["form"] * form_score
                + weights["odds"] * market_score
                + weights["weight"] * weight_score
                + weights["corde"] * corde_score
                + weights["market"] * market_score
            )

            scored.append({
                **runner,
                "score": round(raw, 5),
                "proba": round(raw, 5),
                "p_calibree": round(raw, 5),
                "confidence": round(min(raw * 8, 0.95), 4),
                "reasons": {
                    "form": round(form_score, 3),
                    "market": round(market_score, 3),
                    "weight": round(weight_score, 3),
                    "corde": round(corde_score, 3),
                },
            })

        scored.sort(key=lambda item: item["score"], reverse=True)

        # Normaliser les probabilités
        total_score = sum(r["score"] for r in scored) or 1
        for r in scored:
            r["p_calibree"] = round(r["score"] / total_score, 4)

        ranking = [
            {"rank": index + 1, **runner}
            for index, runner in enumerate(scored[:limit])
        ]

        prediction_id = self.store.save_prediction(
            race_key, race_name, race_date, runners, ranking, {"weights": weights}
        )

        return {
            "prediction_id": prediction_id,
            "race_key": race_key,
            "race_name": race_name,
            "ranking": ranking,
            "recommendations": ranking,
            "ranked": ranking,
            "runners": ranking,
            "non_runners": [],
            "method": "score explicable + calibration historique",
            "disclaimer": "Estimation probabiliste, sans garantie de résultat ni conseil de pari.",
        }