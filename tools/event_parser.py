#!/usr/bin/env python3
"""Parser simplu pentru evenimente din calendarul UTCN.

Extrage:
- Materia și profesorul din titlu (format: "Materie - Profesor" sau "Materie (ABREV) - Profesor - Sala")
- Clădirea și sala din locație (email sau text)
"""

import re
import json
import pathlib
from dataclasses import dataclass
from typing import Optional, Dict

# Mapping-uri pentru clădiri UTCN
BUILDING_ALIASES = {
    'bar': 'Baritiu',
    'baritiu': 'Baritiu',
    'daic': 'DAIC',
    'doro': 'Dorobantilor',
    'dorobantilor': 'Dorobantilor',
    'obs': 'Observatorului',
    'memorandumului': 'Memorandumului',
    'memo': 'Memorandumului',
}

# Load extra aliases from config/building_aliases.json if present to make the
# heuristic data-driven and editable without code changes.
try:
    cfg_path = pathlib.Path('config') / 'building_aliases.json'
    if cfg_path.exists():
        with cfg_path.open('r', encoding='utf-8') as fh:
            user_map = json.load(fh)
            # user_map is alias -> canonical
            for k, v in user_map.items():
                if k and isinstance(k, str):
                    BUILDING_ALIASES[k.lower()] = v
except Exception:
    # Ignore config load errors and fall back to built-in mapping
    pass

# Prefixuri pentru săli speciale
ROOM_PREFIXES = {
    'bt': 'BT',  # BT5.03 etc
    's': 'S',    # S4.2 etc
    'p': 'P',    # P03 etc  
    'd': 'D',    # D01 etc
}


@dataclass
class ParsedEvent:
    """Rezultatul parsării unui eveniment."""
    subject: str = ''           # Materia (nume complet sau abreviere)
    abbreviation: str = ''      # Abrevierea materiei
    professor: str = ''         # Numele profesorului
    building: str = ''          # Clădirea
    room: str = ''              # Sala
    room_code: str = ''         # Codul complet al sălii (ex: "BT5.03")
    event_type: str = ''        # In-person, Online, etc
    is_lab: bool = False        # True dacă e laborator/seminar
    display_title: str = ''     # Titlul formatat pentru afișare
    original_title: str = ''    # Titlul original
    original_location: str = '' # Locația originală


def parse_location_email(email: str) -> Dict[str, str]:
    """Parsează locația din format email UTCN.
    
    Exemple:
        utcn_room_ac_bar_bt-503@campus.utcluj.ro -> {'building': 'Baritiu', 'room': 'BT5.03'}
        utcn_room_ac_daic_479@campus.utcluj.ro -> {'building': 'DAIC', 'room': '479'}
    """
    result = {'building': '', 'room': '', 'room_code': ''}
    
    if not email or '@' not in email:
        return result
    
    # Extrage partea înainte de @
    local_part = email.split('@')[0].lower()
    
    # Pattern: utcn_room_ac_BUILDING_ROOM
    match = re.match(r'utcn_room_ac_([a-z]+)_(.+)', local_part)
    if not match:
        return result
    
    building_code = match.group(1)
    room_raw = match.group(2)
    
    # Mapează building
    result['building'] = BUILDING_ALIASES.get(building_code, building_code.upper())
    
    # Parsează room (ex: bt-503 -> BT5.03, s42 -> S4.2, 479 -> 479)
    room_raw = room_raw.replace('-', '')
    
    # Verifică prefix special
    for prefix, display in ROOM_PREFIXES.items():
        if room_raw.startswith(prefix) and len(room_raw) > len(prefix):
            rest = room_raw[len(prefix):]
            # Formatează ca BT5.03 (adaugă punct între cifre dacă nu există)
            if rest.isdigit() and len(rest) >= 2:
                # bt503 -> BT5.03
                result['room'] = f"{display}{rest[0]}.{rest[1:]}"
            else:
                result['room'] = f"{display}{rest}"
            result['room_code'] = result['room']
            return result
    
    # Sala simplă (479, 26b, etc)
    result['room'] = room_raw.upper()
    result['room_code'] = result['room']
    return result


def parse_location_text(text: str) -> Dict[str, str]:
    """Parsează locația din format text.
    
    Exemple:
        "UTCN - AC Bar - Sala BT 503" -> {'building': 'Baritiu', 'room': 'BT503'}
        "Sala 479 DAIC" -> {'building': 'DAIC', 'room': '479'}
    """
    result = {'building': '', 'room': '', 'room_code': ''}
    
    if not text:
        return result
    
    text_lower = text.lower()
    
    # Caută clădirea - preferăm aliasuri mai lungi (de exemplu 'ac bar') peste 'bar'
    if text_lower:
        # Sort aliases by length desc so longer phrases are matched first
        aliases = sorted(BUILDING_ALIASES.keys(), key=lambda s: -len(s))
        for alias in aliases:
            if not alias:
                continue
            if alias in text_lower:
                result['building'] = BUILDING_ALIASES.get(alias, '')
                break
    
    # Caută sala - pattern-uri comune
    # "Sala BT 503", "Sala 479", "BT5.03", "S4.2"
    room_patterns = [
        r'sala\s+([a-z]*\s*[\d\.]+[a-z]?)',  # Sala BT 503, Sala 479
        r'\b(bt\s*[\d\.]+)',                   # BT5.03, BT 503
        r'\b(s\s*[\d\.]+)',                    # S4.2
        r'\b(p\s*\d+)',                        # P03
        r'\b(d\s*\d+)',                        # D01
        r'\b(\d{2,3}[a-z]?)\b',               # 479, 26B
    ]
    
    for pattern in room_patterns:
        match = re.search(pattern, text_lower)
        if match:
            room = match.group(1).strip().upper().replace(' ', '')
            result['room'] = room
            result['room_code'] = room
            break
    
    return result


def parse_location(location: str) -> Dict[str, str]:
    """Parsează locația din orice format (email sau text)."""
    if not location:
        return {'building': '', 'room': '', 'room_code': ''}
    
    # Dacă e email
    if '@' in location and 'utcn_room' in location.lower():
        return parse_location_email(location)
    
    # Altfel e text
    return parse_location_text(location)


def parse_title(title: str) -> ParsedEvent:
    """Parsează titlul unui eveniment.
    
    Formate suportate:
        1. "Materie - Profesor" -> subject=Materie, professor=Profesor
        2. "Materie (ABREV) - Profesor - Sala [In-person]"
        3. "ABREV Sala [In-person]" -> subject=ABREV, room=Sala
        4. "Materie" -> subject=Materie
    """
    result = ParsedEvent(original_title=title)
    
    if not title:
        return result
    
    # Curăță titlul
    title = title.strip()
    
    # Extrage [In-person], [Online] etc
    type_match = re.search(r'\[([^\]]+)\]', title)
    if type_match:
        result.event_type = type_match.group(1).strip()
        title = title[:type_match.start()].strip()
    
    # Verifică dacă e laborator/seminar
    title_lower = title.lower()
    if ' p ' in f' {title_lower} ' or 'seminar' in title_lower or 'lab' in title_lower:
        result.is_lab = True
    
    # Încearcă formatul complet: "Nume materie (ABREV) - Profesor - Sala"
    full_match = re.match(
        r'^(.+?)\s*\(([A-Z]{2,6})\)\s*-\s*([^-]+?)(?:\s*-\s*(.+))?$',
        title,
        re.IGNORECASE
    )
    if full_match:
        result.subject = full_match.group(1).strip()
        result.abbreviation = full_match.group(2).upper()
        result.professor = full_match.group(3).strip() if full_match.group(3) else ''
        if full_match.group(4):
            result.room_code = full_match.group(4).strip()
        result.display_title = result.subject
        return result
    
    # Încearcă formatul simplu cu liniuță: "Materie - Profesor"
    if ' - ' in title:
        parts = title.split(' - ', 1)
        result.subject = parts[0].strip()
        
        # Partea după - poate fi profesor sau poate conține și sala
        if len(parts) > 1:
            after_dash = parts[1].strip()
            
            # Dacă e gol (doar "Materie - "), nu avem profesor
            if not after_dash:
                result.display_title = result.subject
                return result
            
            # Verifică dacă e "Profesor - Sala" sau doar "Profesor"
            if ' - ' in after_dash:
                prof_parts = after_dash.split(' - ', 1)
                result.professor = prof_parts[0].strip()
                result.room_code = prof_parts[1].strip() if len(prof_parts) > 1 else ''
            else:
                # Poate fi profesor sau poate fi gol (doar liniuță)
                if after_dash:
                    result.professor = after_dash
        
        result.display_title = result.subject
        return result
    
    # Verifică dacă titlul se termină cu " - " (fără profesor)
    if title.rstrip().endswith(' -') or title.rstrip().endswith('-'):
        result.subject = title.rstrip().rstrip('-').strip()
        result.display_title = result.subject
        return result
    
    # Format scurt: "ABREV Sala" sau "ABREV p Sala" (laborator)
    # ABREV trebuie să fie uppercase (ex: "FP", "AI", "SCS")
    short_match = re.match(
        r'^([A-Z]{2,6})(?:\s+p)?\s+(.+)$',
        title
    )
    if short_match:
        abbrev = short_match.group(1)
        # Verifică că e efectiv o abreviere (toate literele uppercase)
        if abbrev.isupper():
            result.abbreviation = abbrev
            result.subject = result.abbreviation  # Folosim abrevierea ca subject
            result.room_code = short_match.group(2).strip()
            result.display_title = result.abbreviation
            return result
    
    # Fallback: titlul e doar materia
    result.subject = title
    result.display_title = title
    return result


def parse_event(event: dict) -> dict:
    """Parsează un eveniment complet și returnează date îmbogățite.
    
    Args:
        event: Dict cu 'title', 'location', 'raw', etc.
        
    Returns:
        Dict cu câmpuri adăugate: 'subject', 'professor', 'building', 'room', etc.
    """
    result = dict(event)  # Copie
    
    # Parsează titlul
    title = event.get('title', '') or ''
    raw = event.get('raw', {}) or {}
    
    # Folosește Subject din raw dacă există (e mai complet)
    if isinstance(raw, dict):
        subject_raw = raw.get('Subject', '')
        if subject_raw:
            title = subject_raw
    
    parsed_title = parse_title(title)
    result['subject'] = parsed_title.subject
    result['abbreviation'] = parsed_title.abbreviation
    result['professor'] = parsed_title.professor
    result['event_type'] = parsed_title.event_type
    result['is_lab'] = parsed_title.is_lab
    result['display_title'] = parsed_title.display_title or parsed_title.subject
    
    # Parsează locația - încearcă mai multe surse
    location = event.get('location', '') or ''
    
    # Încearcă și din raw.Location.DisplayName
    if isinstance(raw, dict):
        raw_loc = raw.get('Location', {})
        if isinstance(raw_loc, dict):
            raw_display = raw_loc.get('DisplayName', '')
            if raw_display:
                # Preferă locația text dacă nu e email
                if '@' not in raw_display:
                    location = raw_display
                elif not location:
                    location = raw_display
    
    parsed_loc = parse_location(location)
    result['building'] = parsed_loc.get('building', '')
    result['room'] = parsed_loc.get('room', '') or parsed_title.room_code
    
    # Dacă room-ul vine din titlu și nu din locație
    if not result['room'] and parsed_title.room_code:
        result['room'] = parsed_title.room_code
    
    return result


def parse_group_from_string(s: str) -> Dict[str, str]:
    """Extract year and group from a free-form string (calendar name / subject).

    Returns dict: {'year': '3', 'group': 'A', 'display': 'Year 3 • Group A'} or empty strings.
    """
    out = {'year': '', 'group': '', 'display': ''}
    if not s:
        return out
    try:
        txt = str(s).lower()
        # patterns: 'year 3', 'grupa A', 'group A', '3A', '3 A', 'eng 3', 'CTI A 3'
        m = re.search(r'\byear\s*([1-4])\b', txt)
        if m:
            out['year'] = m.group(1)
        m = re.search(r'\bgrup[ai]\s*([a-z0-9]+)\b', txt)
        if m:
            out['group'] = m.group(1).upper()
        m = re.search(r'\bgroup\s*([a-z0-9]+)\b', txt)
        if m and not out['group']:
            out['group'] = m.group(1).upper()
        # tokens like '3A' or '3 A'
        if not out['year']:
            m = re.search(r'\b([1-4])\s*([a-z])\b', txt)
            if m:
                out['year'] = m.group(1)
                out['group'] = m.group(2).upper()
        # trailing single digit year
        if not out['year']:
            m = re.search(r'\b([1-4])\b(?!.*\d)', txt)
            if m:
                out['year'] = m.group(1)
        # build display
        parts = []
        if out['year']:
            parts.append('Year ' + out['year'])
        if out['group']:
            parts.append('Group ' + out['group'])
        out['display'] = ' • '.join(parts)
    except Exception:
        pass
    return out


# Funcții de compatibilitate cu vechiul API
def parse_title_compat(title: str) -> dict:
    """Compatibilitate cu vechiul API parse_title()."""
    parsed = parse_title(title)
    return {
        'subject_name': parsed.subject,
        'abbreviation': parsed.abbreviation,
        'professor': parsed.professor,
        'room_code': parsed.room_code,
        'event_type': parsed.event_type,
        'is_practice': parsed.is_lab,
        'display_title': parsed.display_title,
        'original': parsed.original_title,
    }


if __name__ == '__main__':
    # Test
    test_titles = [
        "Functional programming (FP) - R. Slavescu - 40 [In-person]",
        "AI 26B [In-person]",
        "FP 479 [In-person]",
        "Materie - Profesor",
        "Materie - ",
        "Software engineering (SE) - E. Todoran  - P03 [In-person]",
        "SCS p S4.2 / SCS p S4.2  [In-person]",
    ]
    
    test_locations = [
        "utcn_room_ac_bar_bt-503@campus.utcluj.ro",
        "utcn_room_ac_daic_479@campus.utcluj.ro",
        "utcn_room_ac_bar_26b@campus.utcluj.ro",
        "UTCN - AC Bar - Sala BT 503",
    ]
    
    print("=== TITLURI ===")
    for t in test_titles:
        parsed = parse_title(t)
        print(f"  '{t}'")
        print(f"    -> subject='{parsed.subject}', prof='{parsed.professor}', room='{parsed.room_code}'")
    
    print("\n=== LOCAȚII ===")
    for loc in test_locations:
        parsed = parse_location(loc)
        print(f"  '{loc}'")
        print(f"    -> building='{parsed['building']}', room='{parsed['room']}'")
