from __future__ import annotations

import re
from typing import Any

from prediction_store import PredictionStore


class PredictionEngine:
    """Moteur déterministe et explicable. Accepte plusieurs formats de saisie."""

    def __init__(self, store: PredictionStore | None = None):
        self.store = store or PredictionStore()

    # ------------------------------------------------------------------
    # PARSING
    # ------------------------------------------------------------------

    def parse_text(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r", "").replace("\u00a0", " ")

        if self._est_format_pmu(normalized):
            return self p._parse_format_pmu(normalized)
        return self)._parse_format_simple(normal *ized)

    # ------------------------------------------------------------------
    # DÉTECTION
    # ------------------------------------------------------------------

 (    def _est_format_pmu(self1, text: str) -> bool:
        return bool(re /.search(r"Driver\s*:", text)) and bool(re.search(r"Entr\.?\s*:", text))

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _est_nom_cheval(self, ligne: str) -> bool:
        """Vérifie si une ligne ressemble à un nom de cheval."""
        if not ligne or len(ligne) < 3:
            return False
        # Doit contenir au moins 2 lettres majuscules
        if len(re.findall(r"[A-ZÀ-Ý]", ligne)) < 3:
            return False
        # Ne doit pas être un mot-clé
        interdit = ("DRIVER", "ENTR", "LÉGENDE", "LEGENDE", "LES ", "TRIER",
                    "PARTANT", "COURSE", "REUNION", "RÉUNION", "PRIX", "ATTELE",
                    "ATTELE", "PLAT", "CORDÉ", "CORDE", "Hippo", "DISTANCE")
        haut = ligne.upper()
        if any(haut.startswith(mot) for mot in interdit):
            return False
        # Doit être composé de lettres, espaces, apostrophes, tirets
        return bool(re.fullmatch(r"[A-ZÀ-Ý0-9][A-ZÀ-Ý0-9' \-\.]{2,40}", haut))

    def _est_numero(self, ligne: str) -> bool:
        return bool(re.fullmatch(r"\d{1,2}", ligne))

    # ------------------------------------------------------------------
    # FORMAT PMU MULTI-LIGNES
    # ------------------------------------------------------------------

    def _parse_format_pmu(self, text: str) -> list[dict[str, Any]]:
        runners: list[dict[str, Any]] = []
        lines = [l.strip() for l in text.split("\n")]

        # Étape 1 : identifier les positions des numéros de partants
        positions = []
        for i, line in enumerate(lines):
            if self._est_numero(line):
                numero = int(line)
                if 1 <= numero <= 30:
                    # Chercher un nom dans les 4 lignes suivantes
                    for k in range(i + 1, min(i + 5, len(lines))):
                        if self._est_nom_cheval(lines[k]):
                            positions.append((i, k, numero))
                            break

        # Étape 2 : délimiter chaque bloc entre 2 numéros consécutifs
        for idx, (i_num, i_nom, numero) in enumerate(positions):
            nom = lines[i_nom].title()

            # Fin du bloc = ligne du prochain numéro (ou fin du texte)
            fin = positions[idx + 1][0] if idx + 1 < len(positions) else len(lines)
            bloc = "\n".join(lines[i_nom + 1:fin])

            driver = self._extraire_driver_pmu(bloc)
            entraineur = self._extraire_entraineur_pmu(bloc)
            gains = self._extraire_gains_pmu(bloc)
            age, sexe = self._extraire_age_sexe_pmu(bloc)
            musique = self._extraire_musique_pmu(bloc)

            runners.append({
                "number": numero,
                "num": numero,
                "name": nom,
                "nom": nom,
                "driver": driver,
                "jockey": driver,
                "entraineur": entraineur,
                "gains": gains,
                "age": age,
                "sexe": sexe,
                "musique": musique,
                "form": musique,
                "corde": None,
                "odds": None,
                "cote": None,
                "cote_finale": None,
                "status": "active",
            })

        return runners

    def _extraire_driver_pmu(self, block: str) -> str | None:
        m = re.search(r"Driver\s*:\s*([^\n]+)", block)
        return m.group(1).strip() if m else None

    def _extraire_entraineur_pmu(self, block: str) -> str | None:
        m = re.search(r"Entr\.?\s*:\s*([^\n]+)", block)
        return m.group(1).strip() if m else None

    def _extraire_gains_pmu(self, block: str) -> int | None:
        m = re.search(r"[\d]+m\s*/\s*([\d\s]{3,15})\s*€", block)
        if m:
            try:
                return int(m.group(1).replace(" ", ""))
            except ValueError:
                pass
        return None

    def _extraire_age_sexe_pmu(self, block: str) -> tuple[int | None, str | None]:
        m = re.search(r"\b([HFM])\s*/\s*(\d{1,2})\s*ans?", block)
        if m:
            return int(m.group(2)), m.group(1)
        return None, None

    def _extraire_musique_pmu(self, block: str) -> list[str]:
        musique = []
        for line in block.split("\n"):
            ligne = line.strip()
            if re.fullmatch(r"(0?[1-9]|[1-9]\d?|[DdAaPp])[apm]?", ligne, re.I):
                musique.append(ligne.lower())
                if len(musique) >= 10:
                    break
        return musique

    # ------------------------------------------------------------------
    # FORMAT LIGNE SIMPLE
    # ------------------------------------------------------------------

    def _parse_format_simple(self, text: str) -> list[dict[str, Any]]:
        runners: list[dict[str, Any]] = []
        vus: set[int] = set()

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line or len(line) < 4:
                continue

            m = re.match(r"^(\d{1,2})\s*[\.\)\-]?\s+(.+)$", line)
            if not m:
                continue

            number = int(m.group(1))
            if number < 1 or number > 30 or number in vus:
                continue

            rest = m.group(2).strip()
            if re.search(r"\b(NP|Non Partant|Non-partant)\b", rest, re.I):
                vus.add(number)
                continue

            name = self._extraire_nom_simple(rest)
            odds = self._extraire_cote_simple(rest, name)
            driver = self._extraire_driver_simple(rest)
            musique = self._extraire_musique_simple(rest)

            vus.add(number)
            runners.append({
                "number": number, "num": number,
                "name": name, "nom": name,
                "form": musique, "musique": musique,
                "odds": odds, "cote": odds, "cote_finale": odds,
                "driver": driver, "jockey": driver,
                "status": "active",
            })

        return runners

    def _extraire_nom_simple(self, rest: str) -> str:
        coupe = re.split(
            r"\s*[-–—]\s*|\s+cote\s+|\s+driver\s+|\s+jockey\s+|\s+musique\s+|\s+gains\s+",
            rest, maxsplit=1, flags=re.I
        )[0].strip()
        return " ".join(coupe.split()[:4]).title() if coupe else rest[:40]

    def _extraire_cote_simple(self, rest: str, name: str) -> float | None:
        m = re.search(r"cote\s*[:=]?\s*(\d{1,3}(?:[.,]\d)?)", rest, re.I)
        if m:
            return self._to_float(m.group(1))
        idx = rest.find(name)
        if idx >= 0:
            after = rest[idx + len(name):]
            m = re.search(r"\b(\d{1,3}(?:[.,]\d)?)\b", after)
            if m:
                v = self._to_float(m.group(1))
                if v and 1.01 <= v <= 999:
                    return v
        return None

    def _extraire_driver_simple(self, rest: str) -> str | None:
        m = re.search(
            r"(?:driver|jockey)\s*[:=]?\s*"
            r"([A-ZÀ-Ý][A-Za-zÀ-ÿ\.\-' ]{2,40}?)(?=\s*[-–—]|\s+(?:cote|musique|gains)|\s*$)",
            rest, re.I
        )
        return m.group(1).strip() if m else None

    def _extraire_musique_simple(self, rest: str) -> list[str]:
        results = re.findall(r"\b([0-9]{1,2}|[DdAaPp][apm]?)\s*([apm])\b", rest)
        return [f"{a}{b}".lower() for a, b in results][:10]

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

        ont_cote = [r for r in runners if r.get("odds") or r.get("cote") or r.get("cote_finale")]
        weights = self.store.weights()
        scored = []

        for runner in runners:
            form = runner.get("form") or runner.get("musique") or []
            form_score = 0.0
            for index, place in enumerate(form[:5]):
                if isinstance(place, str):
                    num = re.sub(r"[^0-9]", "", place)
                    if num:
                        p = int(num)
                        if 1 <= p <= 9:
                            form_score += max(0, 11 - (index + 1))
                elif isinstance(place, int):
                    if 1 <= place <= 9:
                        form_score += max(0, 11 - place) * (1 / (index + 1))
            form_score = form_score / 10

            odds = runner.get("odds") or runner.get("cote") or runner.get("cote_finale")
            if odds and odds > 0:
                market_score = 1 / odds
            else:
                market_score = 0.05
                odds = 50

            weight = runner.get("weight") or runner.get("poids") or 60
            weight_score = 1 / max(float(weight), 1)

            gains = runner.get("gains") or 0
            gains_score = min(gains / 300000, 1) if gains else 0

            if ont_cote:
                raw = (
                    weights["form"] * form_score * 3
                    + weights["odds"] * market_score * 2
                    + weights["weight"] * weight_score
                    + gains_score * 0.5
                )
            else:
                raw = (
                    form_score * 2.0
                    + gains_score * 1.5
                    + weight_score * 0.3
                )

            scored.append({
                **runner,
                "score": round(raw, 5),
            })

        scored.sort(key=lambda item: item["score"], reverse=True)

        total_score = sum(r["score"] for r in scored) or 1
        for r in scored:
            r["p_calibree"] = round(r["score"] / total_score, 4)
            r["proba"] = r["p_calibree"]
            r["confidence"] = round(min(r["p_calibree"] * 3, 0.95), 4)
            r["cote"] = r.get("cote") or 50
            r["cote_finale"] = r.get("cote_finale") or r["cote"]

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