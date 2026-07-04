"""Custom actions for the car rental chatbot."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Text

from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict

# ---------------------------------------------------------------------------
# Business constants
# ---------------------------------------------------------------------------

VALID_CATEGORIES = {
    "economique": "Économique",
    "économique": "Économique",
    "eco": "Économique",
    "citadine": "Citadine",
    "suv": "SUV / Familiale",
    "familiale": "SUV / Familiale",
    "4x4": "SUV / Familiale",
}

DAILY_RATES_DH = {
    "Économique": 200,
    "Citadine": 250,
    "SUV / Familiale": 450,
}

FLEET_SIZE = {
    "Économique": 8,
    "Citadine": 6,
    "SUV / Familiale": 4,
}

MONTH_NAMES = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}


def normalize_category(value: Text) -> Optional[Text]:
    if not value:
        return None
    key = value.strip().lower()
    return VALID_CATEGORIES.get(key)


def parse_french_date(value: Text, reference: Optional[datetime] = None) -> Optional[datetime]:
    """Parse common French date expressions used in NLU examples."""
    if not value:
        return None

    ref = reference or datetime.now()
    text = value.strip().lower()

    if text in {"aujourd'hui", "aujourdhui"}:
        return ref.replace(hour=0, minute=0, second=0, microsecond=0)
    if text == "demain":
        return (ref + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if "après-demain" in text or "apres-demain" in text:
        return (ref + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    match = re.search(r"(\d{1,2})\s+([a-zéèêûôàù]+)(?:\s+(\d{4}))?", text)
    if match:
        day = int(match.group(1))
        month = MONTH_NAMES.get(match.group(2))
        year = int(match.group(3)) if match.group(3) else ref.year
        if month:
            try:
                return datetime(year, month, day)
            except ValueError:
                return None

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def rental_duration_days(start: datetime, end: datetime) -> int:
    days = (end - start).days
    return max(days, 1)


def season_multiplier(start: datetime) -> float:
    """High season: July–August and December."""
    if start.month in {7, 8, 12}:
        return 1.25
    if start.month in {6, 9}:
        return 1.10
    return 1.0


def format_date_fr(dt: datetime) -> Text:
    return dt.strftime("%d/%m/%Y")


class ValidateReservationForm(FormValidationAction):
    """Validate reservation form slots."""

    def name(self) -> Text:
        return "validate_reservation_form"

    def validate_categorie_voiture(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        normalized = normalize_category(str(slot_value))
        if not normalized:
            dispatcher.utter_message(response="utter_slot_categorie_invalide")
            return {"categorie_voiture": None}
        return {"categorie_voiture": normalized}

    def validate_date_debut(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        parsed = parse_french_date(str(slot_value))
        if not parsed:
            dispatcher.utter_message(response="utter_slot_date_invalide")
            return {"date_debut": None}

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if parsed < today:
            dispatcher.utter_message(response="utter_slot_date_passee")
            return {"date_debut": None}

        return {"date_debut": format_date_fr(parsed)}

    def validate_date_fin(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        parsed_end = parse_french_date(str(slot_value))
        if not parsed_end:
            dispatcher.utter_message(response="utter_slot_date_invalide")
            return {"date_fin": None}

        start_raw = tracker.get_slot("date_debut")
        parsed_start = parse_french_date(str(start_raw)) if start_raw else None
        if parsed_start and parsed_end <= parsed_start:
            dispatcher.utter_message(response="utter_slot_date_fin_invalide")
            return {"date_fin": None}

        return {"date_fin": format_date_fr(parsed_end)}


class ActionCheckAvailability(Action):
    """Simulate vehicle availability for the requested category and dates."""

    def name(self) -> Text:
        return "action_check_availability"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        category = tracker.get_slot("categorie_voiture")
        date_debut = tracker.get_slot("date_debut")
        date_fin = tracker.get_slot("date_fin")

        if not category:
            dispatcher.utter_message(response="utter_demander_categorie_pour_dispo")
            return []

        seed = f"{category}|{date_debut}|{date_fin}|{tracker.sender_id}"
        digest = int(hashlib.md5(seed.encode()).hexdigest(), 16)
        fleet = FLEET_SIZE.get(category, 3)
        booked = digest % (fleet + 1)
        available = max(fleet - booked, 0)

        if available == 0:
            dispatcher.utter_message(
                response="utter_disponibilite_indisponible",
                category=category,
                date_debut=date_debut or "—",
                date_fin=date_fin or "—",
            )
        elif available <= 2:
            dispatcher.utter_message(
                response="utter_disponibilite_limitee",
                category=category,
                available=available,
                date_debut=date_debut or "—",
                date_fin=date_fin or "—",
            )
        else:
            dispatcher.utter_message(
                response="utter_disponibilite_ok",
                category=category,
                available=available,
                date_debut=date_debut or "—",
                date_fin=date_fin or "—",
            )

        return [SlotSet("disponibilite", str(available))]


class ActionEstimateRentalPrice(Action):
    """Estimate rental price from category and rental period."""

    def name(self) -> Text:
        return "action_estimate_rental_price"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        category = tracker.get_slot("categorie_voiture")
        date_debut = tracker.get_slot("date_debut")
        date_fin = tracker.get_slot("date_fin")

        if not category:
            dispatcher.utter_message(response="utter_prix_info")
            return []

        daily = DAILY_RATES_DH.get(category, 250)
        parsed_start = parse_french_date(str(date_debut)) if date_debut else None
        parsed_end = parse_french_date(str(date_fin)) if date_fin else None

        if parsed_start and parsed_end:
            days = rental_duration_days(parsed_start, parsed_end)
            multiplier = season_multiplier(parsed_start)
            total = int(daily * days * multiplier)
            dispatcher.utter_message(
                response="utter_estimation_prix_detail",
                categorie_voiture=category,
                date_debut=date_debut,
                date_fin=date_fin,
                jours=days,
                tarif_journalier=daily,
                total=total,
            )
            return [SlotSet("prix_estime", str(total))]

        dispatcher.utter_message(
            response="utter_estimation_prix_base",
            categorie_voiture=category,
            tarif_journalier=daily,
        )
        return []


class ActionReservationSummary(Action):
    """Build a human-readable reservation summary before confirmation."""

    def name(self) -> Text:
        return "action_reservation_summary"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        category = tracker.get_slot("categorie_voiture")
        date_debut = tracker.get_slot("date_debut")
        date_fin = tracker.get_slot("date_fin")
        prix = tracker.get_slot("prix_estime")

        if not all([category, date_debut, date_fin]):
            dispatcher.utter_message(response="utter_resume_incomplet")
            return []

        if not prix:
            parsed_start = parse_french_date(str(date_debut))
            parsed_end = parse_french_date(str(date_fin))
            if parsed_start and parsed_end:
                days = rental_duration_days(parsed_start, parsed_end)
                daily = DAILY_RATES_DH.get(category, 250)
                multiplier = season_multiplier(parsed_start)
                prix = str(int(daily * days * multiplier))

        dispatcher.utter_message(
            response="utter_resume_reservation",
            categorie_voiture=category,
            date_debut=date_debut,
            date_fin=date_fin,
            prix_estime=prix or "—",
        )
        return [SlotSet("prix_estime", prix)] if prix else []


class ActionConfirmReservation(Action):
    """Confirm the reservation and assign a reference number."""

    def name(self) -> Text:
        return "action_confirm_reservation"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        category = tracker.get_slot("categorie_voiture")
        date_debut = tracker.get_slot("date_debut")
        date_fin = tracker.get_slot("date_fin")
        reservation_id = tracker.get_slot("reservation_id")

        if not reservation_id:
            suffix = hashlib.sha1(
                f"{tracker.sender_id}{datetime.now().isoformat()}".encode()
            ).hexdigest()[:6].upper()
            reservation_id = f"RES-{datetime.now().strftime('%y%m%d')}-{suffix}"

        dispatcher.utter_message(
            response="utter_reservation_confirmee",
            reservation_id=reservation_id,
            categorie_voiture=category,
            date_debut=date_debut,
            date_fin=date_fin,
        )

        return [
            SlotSet("reservation_id", reservation_id),
            SlotSet("reservation_status", "confirmed"),
        ]


class ActionConfirmCancellation(Action):
    """Confirm cancellation of an existing reservation."""

    def name(self) -> Text:
        return "action_confirm_cancellation"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        reservation_id = tracker.get_slot("reservation_id")

        if reservation_id and tracker.get_slot("reservation_status") == "confirmed":
            dispatcher.utter_message(
                response="utter_annulation_confirmee",
                reservation_id=reservation_id,
            )
            return [
                SlotSet("reservation_status", "cancelled"),
                SlotSet("reservation_id", None),
                SlotSet("categorie_voiture", None),
                SlotSet("date_debut", None),
                SlotSet("date_fin", None),
                SlotSet("prix_estime", None),
                SlotSet("disponibilite", None),
            ]

        dispatcher.utter_message(response="utter_annulation_sans_reservation")
        return []


class ActionResetReservationForm(Action):
    """Clear reservation-related slots after a completed or aborted flow."""

    def name(self) -> Text:
        return "action_reset_reservation_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        return [
            SlotSet("categorie_voiture", None),
            SlotSet("date_debut", None),
            SlotSet("date_fin", None),
            SlotSet("prix_estime", None),
            SlotSet("disponibilite", None),
        ]


class ActionDefaultFallback(Action):
    """Two-step fallback: rephrase once, then offer structured help."""

    def name(self) -> Text:
        return "action_default_fallback"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        fallback_count = tracker.get_slot("fallback_count") or 0

        if int(fallback_count) >= 1:
            dispatcher.utter_message(response="utter_aide_defaut")
            return [SlotSet("fallback_count", 0)]

        dispatcher.utter_message(response="utter_fallback_rephrase")
        return [SlotSet("fallback_count", int(fallback_count) + 1)]
