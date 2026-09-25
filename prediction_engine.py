import re


class PredictionEngine:
    def __init__(self, store=None):
        self.store = store

    def parse_text(self, text):
        text = text.replace("\r", "")
        if "Driver" in text and "Entr" in text:
            return self.parse_pmu(text)
        return self.parse_simple(text)

    def parse_pmu(self, text):
        lines = [l.strip() for l in text.split("\n")]
        runners = []
        positions = []
        for i, line in enumerate(lines):
            if re.fullmatch(r"\d{1,2}", line):
                num = int(line)
                if 1 <= num <= 30:
                    for k in range(i + 1, min(i + 5, len(lines))):
                        candidat = lines[k]
                        if len(candidat) >= 3 and re.fullmatch(r"[A-ZÀ-Ý][A-ZÀ-Ý' \-\.]{2,40}", candidat):
                            if not candidat.startswith(("DRIVER", "ENTR", "LEGENDE", "LES")):
                                positions.append((i, k, num))
                                break
        for idx, (i_num, i_nom, num) in enumerate(positions):
            nom = lines[i_nom].title()
            fin = positions[idx + 1][0] if idx + 1 < len(positions) else len(lines)
            bloc = "\n".join(lines[i_nom + 1:fin])
            driver = None
            m = re.search(r"Driver\s*:\s*([^\n]+)", bloc)
            if m:
                driver = m.group(1).strip()
            gains = None
            m = re.search(r"[\d]+m\s*/\s*([\d\s]{3,15})\s*€", bloc)
            if m:
                try:
                    gains = int(m.group(1).replace(" ", ""))
                except:
                    pass
            musique = []
            for line in bloc.split("\n"):
                ligne = line.strip()
                if re.fullmatch(r"(0?[1-9]|[1-9]\d?|[DdAaPp])[apm]?", ligne, re.I):
                    musique.append(ligne.lower())
                    if len(musique) >= 10:
                        break
            runners.append({
                "number": num, "num": num,
                "name": nom, "nom": nom,
                "driver": driver, "jockey": driver,
                "gains": gains,
                "musique": musique, "form": musique,
                "cote": 50, "cote_finale": 50, "odds": 50,
                "status": "active"
            })
        return runners

    def parse_simple(self, text):
        runners = []
        vus = set()
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^(\d{1,2})\s*[\.\)\-]?\s+(.+)$", line)
            if not m:
                continue
            num = int(m.group(1))
            if num < 1 or num > 30 or num in vus:
                continue
            rest = m.group(2).strip()
            nom = re.split(r"\s*[-–—]\s*|\s+cote\s+|\s+driver\s+", rest, maxsplit=1, flags=re.I)[0].strip()
            nom = " ".join(nom.split()[:4]).title()
            cote = None
            mc = re.search(r"cote\s*[:=]?\s*(\d{1,3}(?:[.,]\d)?)", rest, re.I)
            if mc:
                try:
                    cote = float(mc.group(1).replace(",", "."))
                except:
                    pass
            driver = None
            md = re.search(r"(?:driver|jockey)\s*[:=]?\s*([A-ZÀ-Ý][A-Za-zÀ-ÿ\.\-' ]{2,40}?)(?=\s*[-–—]|\s+(?:cote|musique)|\s*$)", rest, re.I)
            if md:
                driver = md.group(1).strip()
            musique = []
            for a, b in re.findall(r"\b([0-9]{1,2}|[DdAaPp][apm]?)\s*([apm])\b", rest):
                musique.append(f"{a}{b}".lower())
            vus.add(num)
            runners.append({
                "number": num, "num": num,
                "name": nom, "nom": nom,
                "driver": driver, "jockey": driver,
                "cote": cote or 50, "cote_finale": cote or 50, "odds": cote or 50,
                "musique": musique[:10], "form": musique[:10],
                "status": "active"
            })
        return runners

    def rank(self, runners, race_key, race_name="Course", race_date=None, limit=10):
        if not runners:
            raise ValueError("Aucun partant")
        scored = []
        for r in runners:
            musique = r.get("musique") or []
            forme = 0.0
            for i, m in enumerate(musique[:5]):
                num = re.sub(r"[^0-9]", "", str(m))
                if num:
                    p = int(num)
                    if 1 <= p <= 9:
                        forme += max(0, 11 - p) * (1 / (i + 1))
            forme = forme / 10
            gains = r.get("gains") or 0
            gains_score = min(gains / 300000, 1) if gains else 0
            cote = r.get("cote") or 50
            market = 1 / cote if cote > 0 else 0
            score = forme * 2.0 + gains_score * 1.5 + market * 2
            scored.append({**r, "score": round(score, 5)})
        scored.sort(key=lambda x: x["score"], reverse=True)
        total = sum(x["score"] for x in scored) or 1
        for x in scored:
            x["p_calibree"] = round(x["score"] / total, 4)
            x["proba"] = x["p_calibree"]
            x["confidence"] = round(min(x["p_calibree"] * 3, 0.95), 4)
        ranking = [{"rank": i + 1, **x} for i, x in enumerate(scored[:limit])]
        try:
            pid = self.store.save_prediction(race_key, race_name, race_date, runners, ranking, {}) if self.store else 0
        except:
            pid = 0
        return {
            "prediction_id": pid,
            "race_key": race_key,
            "race_name": race_name,
            "ranking": ranking,
            "recommendations": ranking,
            "ranked": ranking,
            "runners": ranking,
            "non_runners": [],
            "method": "score explicable",
            "disclaimer": "Estimation sans garantie."
        }