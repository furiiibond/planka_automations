#!/usr/bin/env python3
"""
Planka Repeater (.env + délai avant retour en To Do)
====================================================

Principe:
- Si une carte est placée dans la liste DONE et contient un tag de récurrence
  dans le titre ou la description:
      [R-D]    -> 1 jour
      [R-3D]   -> 3 jours
      [R-W]    -> 1 semaine
      [R-2W]   -> 2 semaines
      [R-M]    -> 1 mois
      [R-6M]   -> 6 mois
  (le nombre est optionnel; défaut=1)

- ALORS: on NE la remet PAS tout de suite dans To Do.
  On règle son `dueDate` à (now + période).
  Quand `now >= dueDate`, on la remet automatiquement dans To Do.

Configuration (fichier .env à la racine) :
    PLANKA_BASE_URL=https://planka.example.com
    PLANKA_USERNAME=admin
    PLANKA_PASSWORD=admin123
    BOARD_ID=1
    TODO_LIST_NAME=To Do
    DONE_LIST_NAME=Done
    POLL_SECONDS=10

Dépendances :
    pip install -r requirements.txt
      -> requests
      -> python-dateutil
      -> python-dotenv
"""
import os
import re
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import requests
from dateutil import parser as dtparse
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv


# --- Chargement .env ----------------------------------------------------------
load_dotenv()

# --- Logs --------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# --- Regex pour la récurrence : [R-<n><U>] où n optionnel, U ∈ {D, W, M} ------
REPEAT_REGEX = re.compile(r"\[(R-(?:(\d+)?\s*(D|W|M)))\]", re.IGNORECASE)


# --- Helpers -----------------------------------------------------------------
def _to_planka_iso(dt: datetime) -> str:
    """Format ISO strict attendu par Planka: YYYY-MM-DDTHH:MM:SS.000Z (UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_iso_safe(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO → datetime (timezone-aware UTC). Retourne None si invalide/absent."""
    if not s:
        return None
    try:
        dt = dtparse.parse(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


# --- Client Planka ------------------------------------------------------------
class PlankaClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.token: Optional[str] = None

    # Extraction robuste du token quel que soit le format de réponse
    def _extract_token(self, payload) -> Optional[str]:
        if isinstance(payload, str):
            s = payload.strip().strip('"').strip("'")
            if s.lower().startswith("<!doctype") or s.lower().startswith("<html"):
                return None
            if " " not in s and len(s) >= 20:
                return s
            return None

        if isinstance(payload, dict):
            for k in ("token", "accessToken", "access_token", "jwt", "bearer"):
                v = payload.get(k)
                if isinstance(v, str) and len(v) >= 20:
                    return v
                if isinstance(v, dict):
                    vv = v.get("token") or v.get("jwt")
                    if isinstance(vv, str) and len(vv) >= 20:
                        return vv
            for v in payload.values():
                t = self._extract_token(v)
                if t:
                    return t
            return None

        if isinstance(payload, list):
            for it in payload:
                t = self._extract_token(it)
                if t:
                    return t
        return None

    def login(self) -> None:
        url = f"{self.base_url}/api/access-tokens"
        resp = self.session.post(
            url,
            json={"emailOrUsername": self.username, "password": self.password},
            timeout=20,
        )
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            data = resp.text

        token = self._extract_token(data)
        if not token:
            ct = resp.headers.get("Content-Type", "unknown")
            preview = resp.text[:300].replace("\n", "\\n")
            raise RuntimeError(
                f"Impossible d'extraire le token. "
                f"Status={resp.status_code}, Content-Type={ct}, Body[:300]='{preview}'"
            )

        self.token = token
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        logging.info("✅ Authentifié auprès de Planka")

    def get_board(self, board_id: str) -> dict:
        url = f"{self.base_url}/api/boards/{board_id}"
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def patch_card(self, card_id: str, payload: dict) -> dict:
        url = f"{self.base_url}/api/cards/{card_id}"
        resp = self.session.patch(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()


# --- Utilitaires de récurrence -----------------------------------------------
def parse_repeat_rule(text: str) -> Optional[Tuple[int, str]]:
    """Retourne (count, unit) pour le premier tag [R-nX] trouvé (X ∈ {D,W,M})."""
    if not text:
        return None
    m = REPEAT_REGEX.search(text)
    if not m:
        return None
    count = int(m.group(2)) if m.group(2) else 1
    unit = m.group(3).upper()
    return count, unit


def add_period(base: datetime, count: int, unit: str) -> datetime:
    """Ajoute count*unit à base et renvoie un datetime (tz-aware UTC)."""
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    else:
        base = base.astimezone(timezone.utc)
    unit = unit.upper()
    if unit == "D":
        return base + relativedelta(days=+count)
    if unit == "W":
        return base + relativedelta(weeks=+count)
    if unit == "M":
        return base + relativedelta(months=+count)
    return base


# --- Cœur du service ----------------------------------------------------------
def run_loop():
    base_url = os.getenv("PLANKA_BASE_URL")
    username = os.getenv("PLANKA_USERNAME")
    password = os.getenv("PLANKA_PASSWORD")
    board_id = os.getenv("BOARD_ID")
    todo_list_name = os.getenv("TODO_LIST_NAME", "To Do")
    done_list_name = os.getenv("DONE_LIST_NAME", "Done")
    poll_seconds = int(os.getenv("POLL_SECONDS", "10"))

    missing = [
        k
        for k, v in {
            "PLANKA_BASE_URL": base_url,
            "PLANKA_USERNAME": username,
            "PLANKA_PASSWORD": password,
            "BOARD_ID": board_id,
        }.items()
        if not v
    ]
    if missing:
        raise SystemExit(f"❌ Variables manquantes: {', '.join(missing)}")

    client = PlankaClient(base_url, username, password)
    client.login()

    # Mémoire process: évite doublons tant que l'état (listId+dueDate) ne change pas
    processed_in_this_state: Dict[str, str] = {}

    while True:
        try:
            board = client.get_board(board_id)
            included = board.get("included", {})
            lists = {str(lst["id"]): lst for lst in included.get("lists", [])}
            cards = included.get("cards", [])

            # IDs des listes
            todo_id = next(
                (lid for lid, l in lists.items() if l.get("name") == todo_list_name),
                None,
            )
            done_id = next(
                (lid for lid, l in lists.items() if l.get("name") == done_list_name),
                None,
            )
            if not todo_id or not done_id:
                raise RuntimeError("Impossible de trouver les listes TODO/DONE")

            # Position de fin de To Do (empiler en bas)
            todo_positions = [
                c.get("position", 0) for c in cards if str(c.get("listId")) == str(todo_id)
            ]
            end_position = (max(todo_positions) + 1) if todo_positions else 1

            now_utc = datetime.now(timezone.utc)

            for card in cards:
                cid = str(card.get("id"))
                list_id = str(card.get("listId"))
                title = card.get("name") or ""
                desc = (card.get("description") or "")
                rep = parse_repeat_rule(title + "\n" + desc)

                if not rep:
                    continue  # pas de tag de récurrence -> on ignore

                # On ne gère la minuterie QUE quand la carte est en DONE
                if list_id != str(done_id):
                    continue

                count, unit = rep
                due_raw = card.get("dueDate")
                due_dt = _parse_iso_safe(due_raw)

                state_key = f"{cid}:{list_id}:{due_raw}"
                if processed_in_this_state.get(cid) == state_key:
                    continue  # pas de changement d'état depuis le dernier poll

                # 1) Si pas de dueDate ou dueDate déjà passée/égale -> on programme le retour
                if (due_dt is None) or (due_dt <= now_utc):
                    new_due = add_period(now_utc, count, unit)
                    payload = {"dueDate": _to_planka_iso(new_due)}
                    client.patch_card(cid, payload)
                    logging.info(
                        "⏱️ Programmation retour (%s, R-%s%s) | dueDate=%s",
                        cid, count, unit, payload["dueDate"]
                    )
                    # mémoriser l'état (va inclure la nouvelle dueDate au prochain tour)
                    processed_in_this_state[cid] = state_key
                    continue

                # 2) Si dueDate future mais arrivée à échéance -> remettre en To Do
                #    (ce bloc est atteint quand due_dt <= now_utc; mais on l'a géré au-dessus)
                if due_dt <= now_utc:
                    # remettre en To Do en bas de liste
                    payload = {"listId": str(todo_id), "position": end_position}
                    client.patch_card(cid, payload)
                    logging.info(
                        "♻️ Retour en To Do (%s, R-%s%s) | position=%s",
                        cid, count, unit, end_position
                    )
                    end_position += 1
                    processed_in_this_state[cid] = state_key
                    continue

                # 3) Sinon: dueDate > now -> on attend tranquillement
                logging.debug(
                    "🕰️ En attente (%s): dueDate=%s > now=%s",
                    cid, due_dt.isoformat(), now_utc.isoformat()
                )
                processed_in_this_state[cid] = state_key

        except requests.HTTPError as e:
            logging.error("HTTP error: %s - %s", e, getattr(e.response, "text", ""))
        except Exception as e:
            logging.exception("Erreur inattendue: %s", e)

        time.sleep(poll_seconds)


if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        print("🛑 Interruption par l'utilisateur.")
