"""Navigator chat pipeline (spec §9): NLU -> deterministic triage -> level card -> LLM answer with tools -> validator."""

import asyncio
import json
import logging
import re
import threading
import unicodedata
from datetime import datetime
from typing import AsyncIterator

from app.adapters.meddi_json import load_patient
from app.agent import tools
from app.config import settings
from app.models import Fact, LevelCard, NavigatorReply, NluResult, PatientContext, TriageOutput
from app.nlu.lexicon_cs_sk import _count

log = logging.getLogger("navigator")

VERSION = "navigator 0.1.0"
MAX_TOOL_ROUNDS = 3
ON_DUTY_PHONE = "724 590 848"

_fallback_history: dict[str, list[dict]] = {}
_pending: dict[str, tuple[str, str, int]] = {}
_resolved: dict[str, tuple[str, int, datetime]] = {}
RESOLVABLE_RULES = {"C-CONTRADICTION", "U-VERIFY"}
_locks: dict[str, asyncio.Lock] = {}
_turns: set[asyncio.Task] = set()
_client = None


def fold(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char))


# ---------- conservative lexicon (engine fallback and red-flag safety net) ----------

SUICIDE = r"zabi(t|ju|jem|t sa)|spolknu|vsechny prasky|vsetky tabletky|vsechny tablety|ublizit si|ublizim si|si ublizit|si ublizim|ukoncim to|skoncim to|nechci tu byt|nechcem tu byt|vzit si zivot|vziat si zivot|skoncit (se|so) zivotem|skoncit so zivotom|sebevrazd|samovrazd|predavkuj|obesit|obesim|skocim|skocit z"
SUICIDE_PLAN = r"plan|priprav|prasky|tablet|naspor|nasetr|promysl|premysl|dnes|zitra|zajtra|vim jak|viem ako|provaz|skocim|mam doma|mam u sebe"
HOPELESS = r"uz nemuzu dal|uz nevladzem dalej|nema to cenu|nema to zmysel|nechci (uz )?zit|nechcem (uz )?zit|chci umrit|chcem zomriet"
RED_FLAGS = {
    "dusnost v klidu": r"nemuzu dychat|nemozem dychat|dusim se|dusi sa|lapa(m)? po dechu|dusnost v klidu",
    "bolest na hrudi": r"bolest (na |v )?hrud|bolest na prsou|pichani na hrudi|tlak na hrudi|bolest v hrudniku|bolest na hrudniku",
    "porucha vědomí": r"nejde (ji |ho )?probudit|neda sa zobudit|\b(neda|nejde|nelze|nemuz\w*|nemoz\w*|nemohu)\s+(\w+\s+){0,3}(pro|vz|z|zo|pre)bud|nereaguje|bezvedom|zmaten|nevi kde je|nevie kde je|zachvat|kroutilo|dycha pomalu|dycha (velmi )?pomaly",
    "krvácení": r"(krev|krv)\w* (ve |v )?(stolic|moc|zvrat)|zvracel\w* krev|zvracal\w* krv|cern\w* stolic|ciern\w* stolic|vykaslav\w* krev",
    "mdloba": r"omdlel|odpadl|odpadol|mdlob|zkolaboval",
    # ponytail: hand-written stroke phrasings (cs/sk); the LLM escalate rule and the 155 backstop cover wordings missing here
    "pokles koutku, porucha řeči, zraku nebo síly jedné strany": "|".join([
        # face: the mouth corner with any droop verb, broader face words only with face-specific verbs (hair loss is common)
        r"\b(pad|pokles|povis|visi|ovis|spadl|klesl|klesa)\w*\s+(\w+\s+){0,3}(koutek|koutk|kutik)",
        r"\b(koutek|koutk|kutik)\w*\s+(\w+\s+){0,3}(pad|pokles|povis|visi|ovis|spadl|klesl|klesa)",
        r"\b(pokles|povis|ovis|kriv|pokriv|zkriv|skriv)\w*\s+(\w+\s+){0,2}(tvar[a-z]?\b|oblic|pus[a-z]?\b|ust\b|usta\b)",
        r"\b(tvar[a-z]?|oblic\w*|pus[a-z]?|ust|usta)\s+(\w+\s+){0,2}(visi|povis|ovis|pokles|klesa|pad|kriv)",
        r"\b(pad|spadl|klesl|pokles)\w*\s+(\w+\s+)?(pulk|polovin)\w*\s+(tvar|oblic)",
        # speech
        r"nesrozumiteln|nezrozumiteln|\bhuhl|\bdrmol|\bblabol|zadrhav|porucha reci|plete s[ea] m\w* (jazyk|rec|slova)|nejdou m\w* slova",
        r"\b(nem\w*|nevedel\w*) (najit|najst) slov",
        r"\b(najednou|nahle|zrazu|odrazu)\s+(\w+\s+){0,2}nem[ou]z\w*\s+(\w+\s+){0,2}(mluvit|hovorit|rozpravat)",
        r"\b(nemuze|nemoze|nedokaze|nevie|nejde (mu|jej|ji))\s+(\w+\s+){0,2}(mluvit|hovorit|rozpravat)",
        r"\bmluv\w* (jako opil|divne|zvlastne|z cesty|nesmysl)|\b(hovor|rozprav)\w* (ako opit|divne|zvlastne|z cesty|nezmysl)",
        r"\b(zle|tazko|spatne|tezko) s[ea] (mu|jej|ji) (mluvi|hovori|rozprava)",
        # vision on one eye, double vision
        r"\b(nevid|nevyd|rozmazan|zatm|prestal\w* (\w+ )?vid)\w*\s+(\w+\s+){0,3}(jedn|lev|lav|prav)[a-z]{0,3}\s+(ok|oc)",
        r"\b(jedn|lev|lav|prav)[a-z]{0,3}\s+(ok|oc)\w*\s+(\w+\s+){0,3}(nevid|nevyd|rozmazan|zatm|oslep|prestal)",
        r"dvojit\w* vid|\bvid\w* dvoj(it|mo)|\boslep",
        # weakness or numbness of one side
        r"\bochrn|\b(necit|slab|nehyb|neovlad|ochab|nem[ou]z\w* (zvednout|zdvihnut|pohnout|pohnut|hybat))\w*\s+(\w+\s+){0,3}"
        r"(jedn|lev|lav|prav)[a-z]{0,3}\s+(ruk|ruc|noh|stran|polovin|polovic)",
        r"\b(jedn|lev|lav|prav)[a-z]{0,3}\s+(ruk|ruc|noh|stran|polovin|polovic)\w*\s+(\w+\s+){0,3}(necit|slab|nehyb|neovlad|ochab|neposlouch|neposluch)",
    ]),
}
NO_FEVER = r"teplot\w* (je |mam |ma )?(normaln|v poradku|v poriadku|ok\b)"
FEVER_REPORT = (r"\b(mam|ma|mame|mate|mel\w*|mal\w*)\s+((asi|trochu|nejak\w*|zvysen\w*|vysok\w*|lehk\w*|mirn\w*|porad|stale|zase|uz|taky|tez|tiez"
                r"|jeste|este|jsem|som|vcera|dnes)\s+){0,2}teplot|zvysen\w* teplot|vysok\w* teplot|teplotu mam|\bteplot(im|i)\b|\basi teplot"
                r"|teplot\w*\s+((mi|mu|ji|jej|se|sa|uz|zase|porad|stale|furt)\s+){0,2}(stoup|stup|roste|rastie|zvys|zved|nejde dol|neklesa|nepovol|neni normal|nie je normal)"
                r"|(stoupl|stupl|zvysil|zvedl|vyskocil)\w*\s+((se|sa|mi|mu|ji|jej)\s+){0,2}teplot")
SYMPTOMS = r"bolest|bolet|boli|nevoln|zvrac|prujem|prujm|hnack|stolic|zacp|unav|slab|kasl|kasel|otok|oteklo|vyrazk|afty|pali|svedi|krvac|modrin|zavrat|tocit|necit|brneni|smut|uzkost|nespim|vycerp|teplot|horec|horuc|zimnic"
DOSE_QUESTION = r"(muzu|mozem|smim|smiem|mam|dat|podat|vzit|zobrat|uzit|pridat|zvysit|dalsi|jeste|este|vic|viac)\b.*\b(davk|oramorph|morfin|tablet|lek(?!ar)|liek|prasek|kapk|loperamid|paralen|paracetamol|ibalgin|ibuprofen|novalgin)"
# the engine's denial forms (lexicon_cs_sk._negated) without the ones that also open a report: "ani po Paralenu horečka neklesá",
# "nikdy jsem neměla takovou bolest", "nemám hlad a bolest na hrudi", "nemám čím změřit horečku", "horečka ne a ne klesnout",
# "stolice není normální"
DENIED_BEFORE = (r"\b(bez|nemam|nema|nemame|nemaji|nemal\w*|zadn\w*|ziadn\w*|neni|nebyl\w*|nebol\w*|netrpi\w*|netrapi\w*)\s+"
                 r"((?!(a|ale|tak\w*|mam|ma|mame|mate|maji|cim|jak|z?mer\w*)\s)\w+(,(?=\s+ani\s))?\s+){0,3}$")
DENIED_AFTER = r"^\w*\s*(ne|nie|nemam|nema|nemame|neni|nebyl\w*|nebol\w*)\b(?!\s+(a\s+(ne|nie)\b|(je\s+)?(normaln|obvykl|bezn|tak)))"
CLAUSE_END = r"([!?;\n]|(?<!\d)\.|\.(?!\d)|(?<!\d),|,(?!\d))"
# ponytail: (clause subject, pronoun that keeps the clause, contrast the writer must state). A symptom clause led by another person
# (pacient) or by "já mám …" (pecujici) is dropped only when the writer also says the patient is fine, since a caregiver may leave the
# app's caregiver switch in the wrong position; no real subject parsing, ambiguous texts stay in.
SOMEONE_ELSE = {
    "pacient": (r"\s*(a |ale |muj |moje |moj |nas |nase )?(manzel|partner|dcer|syn|vnuk|vnuc|sestr|bratr|mama|mamka|maminka|tata|tatka|tatinek|otec|matk"
                r"|kamarad|soused)\w*\s+(\w+\s+)?(ma|mel\w*|mal\w*|nema|je|byl\w*|bol\w*)\b",
                r"\b(mi|me|mne|mna|ja|jsem|som|mam|taky|tez|tiez|oba|obe|obaja)\b",
                r"\b(jsem|som) (\w+ )?(v pohode|v poradku|v poriadku|ok\b|zdrav)|\b(mne|me|mna) (se|sa) to (\w+ )?vyhnul|\bja (nic )?nemam\b"),
    "pecujici": (r"\s*(a |ale |i |aj )?ja\s+(taky |tez |tiez |ted |teraz )?(mam|mivam)\s+(\w+\s+)?(horec|horuc|teplot|zimnic|prujem|prujm|hnack|kasel|kasl"
                 r"|ryma|chripk|nachlad|viroz|covid)",
                 r"\b(ona|on|ji|ju|jej|ho|mu|taky|tez|tiez|oba|obe|obaja)\b|\b(manzel|partner|dcer|syn|vnuk|vnuc|sestr|bratr|mama|mamk|mamin|tat"
                 r"|otec|otc|matk)\w*",
                 r"\bje (\w+ )?(v pohode|v poradku|v poriadku|ok\b|zdrav)"),
}


def _numbers(pattern: str, text: str) -> list[float]:
    return [float(match.group(1).replace(",", ".")) for match in re.finditer(pattern, text)]


def _said(pattern: str, text: str) -> bool:
    """A match the writer does not deny ("nemám bolest na hrudi", "horečku nemám"); unsure counts as said."""
    return any(not (re.search(DENIED_BEFORE, text[:match.start()]) or re.search(DENIED_AFTER, text[match.end():]))
               for match in re.finditer(pattern, text))


def _own_clauses(folded: str, author: str) -> str:
    """The text with the clauses about someone else blanked out, so positions and numbers elsewhere stay as written."""
    subject, pointer, contrast = SOMEONE_ELSE["pecujici" if author == "pecujici" else "pacient"]
    if not re.search(contrast, folded):
        return folded
    return "".join(" " * len(part) if re.match(subject, part) and not re.search(pointer, part) else part
                   for part in re.split(CLAUSE_END, folded))


def lexicon_level(text: str, ctx: PatientContext, lang: str, author: str = "pacient") -> tuple[int, list[str], str | None]:
    """(level, findings, follow-up question). Escalates when unsure; never used to lower the engine's level."""
    folded = _own_clauses(fold(text), author)
    sk = lang == "sk"
    found: list[tuple[int, str]] = []
    question = None
    chemo = ctx.chemo_window or "cytotoxic" in ctx.drug_classes
    temperatures = _numbers(r"\b(3[5-9](?:[.,]\d)?|4[0-2](?:[.,]\d)?)\s*(?:°|stup|c\b)", folded)
    temperatures += _numbers(r"\b(3[5-9][.,]\d|4[0-2][.,]\d)\b", folded)
    if re.search(r"teplot|horec|horuc|namer", folded):
        temperatures += _numbers(r"\b(3[5-9]|4[0-2])\b", folded)
    chills = _said(r"zimnic|tresavk|triask|\btres(e|u)\b|\btras(ie|iem|u)\b|klepu se", folded)
    if (temperatures and max(temperatures) >= 38.0) or chills:
        hot = bool(temperatures) and max(temperatures) >= 40
        level = 4 if chemo or hot else 3 if temperatures and max(temperatures) >= 39 else 2
        found.append((level, "teplota ≥ 38 °C nebo zimnice" + (" během chemoterapie" if chemo else "")))
    elif _said(r"horec|horuc", folded):
        found.append((4 if chemo else 3, "hlášená horečka"))
    elif _said(FEVER_REPORT, folded) and not temperatures and not re.search(NO_FEVER, folded):
        found.append((3, "zvýšená teplota bez hodnoty"))
        question = "Koľko stupňov ste namerali?" if sk else "Kolik stupňů jste naměřil/a?"
    if re.search(SUICIDE, folded):
        found.append((4 if re.search(SUICIDE_PLAN, folded) else 3, "myšlenky na sebevraždu"))
    elif re.search(HOPELESS, folded):
        found.append((3, "výroky beznaděje"))
    for finding, pattern in RED_FLAGS.items():
        if _said(pattern, folded):
            found.append((4, finding))
    counts = _numbers(r"(\d+)\s*(?:x|×|-?krat)(?![a-z])", folded)
    counts += [count for word in re.findall(r"\w+[\s-]?krat\b", folded) if (count := _count(word))]
    stools = counts if _said(r"prujem|prujm|hnack|stolic", folded) else []
    if stools:
        count = max(stools)
        found.append((4 if count >= 7 else 3 if count >= 4 else 2, f"průjem asi {count:g}× za den"))
    elif _said(r"prujem|prujm|hnack", folded):
        found.append((2, "průjem bez počtu stolic"))
        question = question or ("Koľkokrát ste mali hnačku za posledných 24 hodín?" if sk else "Kolikrát jste měl/a průjem za posledních 24 hodin?")
    vomits = counts if re.search(r"zvrac|vracia|vraci", folded) and not stools else []
    if vomits:
        found.append((4 if max(vomits) > 5 else 2, f"zvracení {max(vomits):g}× za den"))
    if re.search(r"neudrz\w* (ani )?(vodu|tekutin|nic|pit)|nemuze pit|nemoze pit|nemoc\w* (uz )?\d+|nemoci od|nemocila|nemocil\b|nemocim\b", folded):
        found.append((3, "neudrží tekutiny / málo močí"))
    if re.search(r"hrozn\w* bolest|bolest\w* hrozn|nesnesiteln|ani po (\d+ )?(davk|tablet|oramorph)|nepomaha|nepomohl|nepovolil|nepomohl", folded):
        found.append((3, "silná bolest nereagující na léky"))
    if re.search(DOSE_QUESTION, folded):
        found.append((2, "dotaz na další dávku léku – rozhoduje tým"))
        if re.search(r"oramorph|morfin|bolest|bolet|\bboli|(dalsi|jeste|este|vic|viac|znovu)\b.*\b(tramal|novalgin|ibalgin|ibuprofen)", folded):
            question = question or ("Koľko dávok už dnes bolo a ako veľmi bolesť povolila?" if sk else "Kolik dávek už dnes bylo a jak moc bolest povolila?")
        elif re.search(r"paralen|paracetamol|teplot|horec|horuc|zima|zimnic", folded) and not temperatures:
            question = question or ("Koľko stupňov ste namerali?" if sk else "Kolik stupňů jste naměřil/a?")
    if not found and re.search(SYMPTOMS, folded):
        found.append((2, "hlášené potíže – posoudí tým"))
    if not found:
        return 1, [], None
    level = max(level for level, _ in found)
    return level, [finding for _, finding in found], question


def _fallback_triage(patient_id: str, text: str, author: str, ctx: PatientContext, at: datetime, lang: str) -> TriageOutput:
    level, findings, question = lexicon_level(text, ctx, lang, author)
    step, contact, notify, sla = tools.route(level, at)
    return TriageOutput(
        checkin_id=f"{patient_id}-CHAT-{at:%Y%m%d%H%M%S}", patient_id=patient_id, uroven=level, doporuceny_krok=step,
        upozornit_tym=notify, doporuceny_kontakt=contact, klicove_nalezy=findings, varovne_priznaky=findings if level >= 3 else [],
        zduvodneni="Chat vyhodnocen záložním slovníkem navigátoru (engine nedostupný); při nejistotě vyšší úroveň.",
        doporuceni_pro_pacienta="", doplnujici_otazka=question, pravidla=["NAV-LEXICON"], dukazy=[], jistota="nizka",
        sla_do=sla, verze=VERSION, lang=lang, adresat="pecujici" if author == "pecujici" else "pacient", zdroj="chat", as_of=at,
    )


def _analyze(text: str, ctx: PatientContext, author: str, lang: str, use_llm: bool = True) -> NluResult:
    try:
        from app.nlu import analyze_text
    except ImportError:
        return NluResult(lang=lang, author=author)
    try:
        return analyze_text(text, ctx, author, use_llm)
    except Exception:
        log.exception("analyze_text failed")
        return NluResult(lang=lang, author=author)


def _triage(patient_id: str, text: str, author: str, ctx: PatientContext, nlu: NluResult, at: datetime, lang: str) -> TriageOutput:
    fallback = _fallback_triage(patient_id, text, author, ctx, at, lang)
    try:
        from app.triage.engine import triage_chat
    except ImportError:
        return fallback
    try:
        try:
            output = triage_chat(patient_id, text, author, ctx, nlu, at, use_llm=False, lang=lang)
        except TypeError:
            output = triage_chat(patient_id, text, author, ctx, nlu, at)
    except Exception:
        log.exception("triage_chat failed, using the lexicon fallback")
        return fallback
    raise_to = output.uroven
    if fallback.doplnujici_otazka and not output.doplnujici_otazka:
        output = output.model_copy(update={"doplnujici_otazka": fallback.doplnujici_otazka})
        raise_to = fallback.uroven
    elif fallback.uroven >= 3:
        raise_to = fallback.uroven
    # ponytail: only strong lexicon signals (>= 3) or an open question raise the engine level, mild words never do
    if raise_to > output.uroven:
        return output.model_copy(update={
            "uroven": fallback.uroven, "doporuceny_krok": fallback.doporuceny_krok, "doporuceny_kontakt": fallback.doporuceny_kontakt,
            "upozornit_tym": True, "sla_do": fallback.sla_do, "pravidla": [*output.pravidla, "NAV-SAFETY-NET"],
            "zduvodneni": "Pojistka navigátoru zvýšila úroveň podle textu zprávy (" + "; ".join(fallback.klicove_nalezy)
                          + "); při nejistotě platí vyšší úroveň.",
            "klicove_nalezy": [*output.klicove_nalezy, *fallback.klicove_nalezy],
            "varovne_priznaky": [*output.varovne_priznaky, *fallback.varovne_priznaky],
        })
    return output


def level_card(output: TriageOutput) -> LevelCard | None:
    if output.uroven < 2:
        return None
    contact = output.doporuceny_kontakt or ""
    buttons = []
    if ON_DUTY_PHONE in contact:
        buttons.append("tel:724590848")
    if output.uroven == 4 or "155" in contact:
        buttons.append("tel:155")
    return LevelCard(uroven=output.uroven, krok=output.doporuceny_krok, kontakt=output.doporuceny_kontakt, buttons=buttons,
                     sla_do=output.sla_do)


# ---------- guardrails ----------

DIAGNOSIS_WORDS = r"neutropen|febriln|seps[ae]|\bsepti|kolitid|srdecni selhani|srdecn\w* zlyhan|zlyhani\w* srdc|tromboz|embol|ketoacidoz|infarkt|metasta|pneumoni|zapal plic|zapal pluc|\bileus|mrtvic|cevni mozkov|toxicit|perforac|zanet\w* stre|zapal\w* crie|zanet\w* plic|zapal\w* pluc|zanet\w* zil|krevni srazenin|krvn\w* zrazenin"
REASSURANCE = r"nemusite se bat|nebojte se|nic vazneho|to je normalni|neni duvod k obavam|nebojte sa|netreba sa bat|nic vazne|nie je dovod na obavy|bez obav"
OTC_DRUGS = r"paralen|paracetamol|ibalgin|ibuprofen|nurofen|aspirin|brufen|novalgin|imodium|smecta|acylpyrin"
NEGATION = r"\bne(uzivejte|uzivajte|berte|davejte|davajte|brat|uzivat|podavejte|podavajte|uzivajte|dava(j)?te)|\bnie\b|\bne\b"
DOSE = r"\d+(?:[.,]\d+)?\s*(?:mg|ml|µg|μg|ug|mcg|g\b|tbl|tablet|kapk|kapsl|davk|×|x\b|krat)"
PERMISSION = r"\b(muzete|smite|mozete|smiete|lze|mate)\b[^.;]{0,40}\b(dat|podat|vzit|uzit|zobrat|davat|podavat|pridat)\b|\b(dejte|podejte|vezmete si|vezmite si|uzijte|dajte|podajte|pridejte)\b"
CALL = r"volejte|zavolejte|volajte|zavolajte|vytocte"
CONDITIONAL = r"\b(pokud|kdyby|jestli\w*|kdyz|kdykoli\w*|jakmile|ak|keby|ked|kedykolvek|akonahle|v pripade|pri)\b"
CONCESSIVE = r"\b(i|aj|ani) (kdyz|ked)\b"
LATER_CALLBACK = r"do konce nasledujic|nasledujic\w* pracovn|do konca nasledujuc|nasledujuc\w* pracovn"
TIME_BY_LEVEL = {2: r"do konce|nasledujic|nasledujuc|pracovn|zitra|zajtra|ozve|ihned|hned", 3: r"dnes|do 2|ihned|hned|okamzit",
                 4: r"ihned|hned|okamzit|ted\b|teraz|necekejte|necakajte"}


def guard(text: str, level: int, lang: str, meds_text: str, contact: str | None, allowed_text: str = "") -> list[str]:
    """Deterministic chat validator (runs with the engine validator, if present). [] = ok."""
    problems = []
    folded = fold(text)
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]
    if not text.strip():
        return ["prázdná odpověď"]
    if len(sentences) > 4:
        problems.append("víc než 4 krátké věty")
    if re.search(DIAGNOSIS_WORDS, folded):
        problems.append("diagnóza v textu pro pacienta")
    allowed = re.sub(r"\s+", "", fold(meds_text + " " + allowed_text))
    for match in re.finditer(DOSE, folded):
        if re.sub(r"\s+", "", match.group(0)) not in allowed:
            problems.append(f"dávka mimo předpis: {match.group(0)}")
    for sentence in sentences:
        folded_sentence = fold(sentence)
        drug = re.search(OTC_DRUGS, folded_sentence)
        if drug and drug.group(0) not in fold(meds_text) and not re.search(NEGATION, folded_sentence):
            problems.append(f"nový lék: {drug.group(0)}")
    if lang == "sk" and re.search(r"[řůě]", text):
        problems.append("odpověď není slovensky")
    if lang == "cs" and re.search(r"[äľĺŕô]", text):
        problems.append("odpověď není česky")
    if level >= 2:
        if re.search(REASSURANCE, folded):
            problems.append("uklidnění místo předání")
        named = contact and (
            (ON_DUTY_PHONE in contact and ON_DUTY_PHONE in text)
            or ("155" in contact and "155" in text)
            or (ON_DUTY_PHONE not in contact and "155" not in contact and re.search(r"monitorovac|lekar|tym|tim", folded))
        )
        if not named:
            problems.append("chybí kontakt z karty")
        if not re.search(TIME_BY_LEVEL[level], folded):
            problems.append("chybí čas")
    if level >= 3 and re.search(LATER_CALLBACK, folded):
        problems.append("slib pozdějšího kontaktu u vysoké úrovně")
    if level == 4:
        if "155" not in text:
            problems.append("chybí 155")
        if sentences and not re.search(CALL, fold(sentences[0])):
            problems.append("úroveň 4 nezačíná výzvou k volání")
    return problems


def urges_155(text: str) -> bool:
    """A sentence tells the patient to call 155 now ("i když už to odeznělo" included), not "if it gets worse"."""
    for sentence in re.split(r"(?<=[.!?])\s+", fold(text)):
        sentence = re.sub(CONCESSIVE, "", sentence)
        if "155" in sentence and re.search(CALL, sentence) and not re.search(CONDITIONAL, sentence):
            return True
    return False


def validate(text: str, output: TriageOutput, ctx: PatientContext, lang: str, allowed_text: str) -> list[str]:
    meds_text = " ".join(f"{med.lek} {med.davka} {med.frekvence}" for med in ctx.meds)
    problems = guard(text, output.uroven, lang, meds_text, output.doporuceny_kontakt, allowed_text)
    med_words = {word[:6] for med in ctx.meds for word in re.findall(r"\w{5,}", fold(med.lek))}
    for sentence in re.split(r"(?<=[.!?])\s+", fold(text)):
        if (any(word in sentence for word in med_words) or "davk" in sentence) and re.search(PERMISSION, sentence):
            problems.append("svolení k dávce místo citace předpisu")
    if output.uroven in (2, 3) and tools.palliative_care(ctx) and not re.search(r"paliativ|hospic", fold(text)):
        problems.append("chybí 24h linka paliativního týmu nebo hospice")
    try:
        from app.triage.validator import validate_patient_text
    except ImportError:
        return problems
    try:
        return problems + validate_patient_text(text, output.uroven, lang, ctx.meds, output.doporuceny_kontakt)
    except Exception:
        log.exception("validate_patient_text failed")
        return problems


def mentioned_meds(text: str, ctx: PatientContext) -> list:
    folded = fold(text)
    return [med for med in ctx.meds if any(word[:6] in folded for word in re.findall(r"\w{5,}", fold(med.lek)))]


def template(output: TriageOutput, lang: str, palliative: bool, fever: str, suicide: bool, meds: list = [],
             self_medication: bool = False) -> str:
    """fever: the Paralen sentence to add, or "" when it does not belong to this reply."""
    sk = lang == "sk"
    contact = output.doporuceny_kontakt or ""
    level_text = _level_template(output, contact, sk, palliative, fever, suicide)
    if self_medication:
        fits = len(re.split(r"(?<=[.!?])\s+", level_text)) < 4
        prescription = _self_medication_line(sk, output.adresat == "pecujici") if fits else ""
    else:
        prescription = " ".join(
            (f"Podľa predpisu: {med.lek} {med.davka}, {med.frekvence}; o ďalšej dávke navyše rozhoduje lekár." if sk
             else f"Podle předpisu: {med.lek} {med.davka}, {med.frekvence}; o další dávce navíc rozhoduje lékař.")
            for med in meds[:1]
        )
    return f"{prescription} {level_text}" if prescription and output.uroven < 4 else level_text


def _palliative_line(sk: bool) -> str:
    return ("V paliatívnej starostlivosti môžete kedykoľvek volať 24h linku paliatívneho tímu alebo hospicu." if sk
            else "V paliativní péči můžete kdykoli volat 24h linku paliativního týmu nebo hospice.")


def _paralen_line(sk: bool, caregiver: bool, sex: str | None) -> str:
    if caregiver:
        whom = {"F": "ju " if sk else "ji ", "M": "ho "}.get(sex or "", "")
        return f"Paralen nepodávajte, kým {whom}nevyšetrí lekár." if sk else f"Paralen nepodávejte, dokud {whom}nevyšetří lékař."
    return "Paralen neužívajte, kým vás nevyšetrí lekár." if sk else "Paralen neužívejte, dokud vás nevyšetří lékař."


def _self_medication_line(sk: bool, caregiver: bool) -> str:
    if sk:
        return f"Bez porady s lekárom žiadny ďalší liek {'nepodávajte' if caregiver else 'neužívajte'} a nič nevymieňajte ani nevysadzujte."
    return f"Bez porady s lékařem žádný další lék {'nepodávejte' if caregiver else 'neužívejte'} a nic nevyměňujte ani nevysazujte."


def _level_template(output: TriageOutput, contact: str, sk: bool, palliative: bool, fever: str, suicide: bool) -> str:
    if output.uroven == 4 and suicide:
        if sk:
            return "Volajte prosím ihneď 155. Nezostávajte teraz sami – povedzte niekomu blízkemu, nech je s vami, a dajte lieky z dosahu."
        return ("Volejte prosím ihned 155. Nezůstávejte teď sami – řekněte někomu blízkému, ať je s vámi, a dejte léky z dosahu. "
                "Můžete volat i Linku první psychické pomoci 116 123 (nonstop).")
    if output.uroven == 4:
        parts = ["Volajte ihneď 155 alebo choďte na urgentný príjem." if sk else "Volejte ihned 155 nebo jeďte na urgentní příjem."]
        if ON_DUTY_PHONE in contact:
            parts.append(f"Môžete volať aj službukonajúceho lekára MOÚ {ON_DUTY_PHONE}." if sk else f"Můžete volat i sloužícího lékaře MOÚ {ON_DUTY_PHONE}.")
        parts.append("Nečakajte do rána." if sk else "Nečekejte do rána.")
        if fever:
            parts.append(fever)
        return " ".join(parts)
    if output.uroven == 3:
        if ON_DUTY_PHONE in contact:
            who = (f"Zavolajte prosím ihneď službukonajúcemu lekárovi MOÚ na číslo {ON_DUTY_PHONE}." if sk
                   else f"Zavolejte prosím hned sloužícímu lékaři MOÚ na číslo {ON_DUTY_PHONE}.")
        else:
            who = ("Lekár MOÚ vám zavolá cez monitorovacie centrum do 2 hodín." if sk
                   else "Lékař MOÚ vám zavolá přes monitorovací centrum do 2 hodin.")
        if output.adresat == "pecujici":
            first = "Ťažkosti vášho blízkeho je potrebné ešte dnes prebrať s lekárom." if sk else "Potíže vašeho blízkého je potřeba ještě dnes probrat s lékařem."
        else:
            first = "Vaše ťažkosti je potrebné ešte dnes prebrať s lekárom." if sk else "Vaše potíže je potřeba ještě dnes probrat s lékařem."
        last = "Ak sa stav zhorší, volajte 155." if sk else "Pokud se stav zhorší, volejte 155."
        return " ".join([first, who, _palliative_line(sk), last] if palliative else [first, who, last])
    if output.uroven == 2:
        when = ("do konca nasledujúceho pracovného dňa" if sk else "do konce následujícího pracovního dne") if "do konce" in contact \
            else ("nasledujúci pracovný deň" if sk else "následující pracovní den")
        first = (f"Vašu správu sme odovzdali tímu monitorovacieho centra, ozve sa vám {when}." if sk
                 else f"Vaši zprávu jsme předali týmu monitorovacího centra, ozve se vám {when}.")
        palliative_line = " " + _palliative_line(sk) if palliative else ""
        last = (f" Ak sa stav zhorší, objaví sa horúčka, krvácanie alebo dýchavičnosť, volajte ihneď 155 (mimo pracovného času službukonajúceho lekára MOÚ {ON_DUTY_PHONE})." if sk
                else f" Pokud se stav zhorší, objeví se horečka, krvácení nebo dušnost, volejte ihned 155 (mimo pracovní dobu sloužícího lékaře MOÚ {ON_DUTY_PHONE}).")
        return first + palliative_line + last
    if sk:
        return ("Ďakujeme za správu. Na túto otázku vám najlepšie odpovie váš tím, radi ju odovzdáme. "
                "Ak sa objaví horúčka 38 °C a viac, zimnica, dýchavičnosť, krvácanie alebo silná bolesť, volajte ihneď 155.")
    return ("Děkujeme za zprávu. Na tuto otázku vám nejlépe odpoví váš tým, rádi ji předáme. "
            "Pokud se objeví horečka 38 °C a víc, zimnice, dušnost, krvácení nebo silná bolest, volejte ihned 155.")


# ---------- LLM ----------

SYSTEM_PROMPT = """Jsi MEDDI navigátor, asistent monitorovacího centra Masarykova onkologického ústavu (MOÚ) v chatu pro onkologické pacienty a jejich blízké.

Pravidla, která nikdy neporušíš:
1. Nikdy nestanovuj diagnózu a nepiš názvy diagnóz (např. kolitida, sepse, neutropenie, infekce, dehydratace, trombóza, embolie, infarkt, srdeční selhání, metastázy, toxicita) – ani je neopakuj po pacientovi a neopisuj je laickými slovy (např. „zánět střev“). Na otázku „Mám …?“ odpověz, že to v chatu posoudit nelze a posoudí to lékař, a nabídni předání týmu monitorovacího centra.
2. Nikdy neměň ani nepočítej dávky a nedoporučuj žádné nové léky. Smíš jen doslova zopakovat předpis z pole meds (davka a frekvence přesně tak, jak jsou napsané), nic navíc. Na otázku na další dávku řekni, co přesně říká předpis, a že o čemkoli navíc rozhoduje lékař; v paliativní péči odkaž na 24h linku paliativního týmu nebo hospice, a když se nedovolají, 155.
3. Úroveň závažnosti a kontakt určil bezpečnostní triážní systém (pole triage a level_card). Nikdy je nesnižuj, nezlehčuj a nevymýšlej jiný kontakt. U úrovně 2–4 už byl tým upozorněn automaticky: nenabízej předání, ale přirozeně řekni, kdo se ozve nebo koho volat a kdy (kontakt a čas z level_card), a nepiš uklidňování typu „nemusíte se bát“ nebo „to je normální“.
U úrovně 1 tým sám nevolá: neslibuj, že se někdo ozve, jen nabídni, že dotaz můžeš předat týmu.
4. U úrovně 4 začni první větou výzvou k okamžitému volání (např. „Volejte ihned …“) a vždy uveď 155. Ohrožení života = vždy 155.
5. Paralen ani jiné léky na horečku nezmiňuj, pokud to nepožaduje pole must nebo se na ně pisatel sám neptá; větu o Paralenu z pole must napiš přesně tak, jak je.
6. Odpovídej výhradně v jazyce: {language}. Nejvýš 4 krátké věty, jednoduchá slova bez odborných termínů, vykej.
7. {addressee}
8. Vycházej jen ze schválených textů (guidance) a z údajů pacienta v kontextu. Když si nejsi jistý, nabídni předání týmu. Nikdy nepiš jména ani data narození.
9. Doplňující otázku (followup_question) připojí systém sám za tvou odpověď – nepiš ji ani jinou otázku na totéž.
10. Když zpráva popisuje něco vážnějšího, než ukazuje triage (např. náhlý pokles koutku, porucha řeči, zraku nebo síly jedné strany těla, bezvědomí, silné krvácení), nejdřív zavolej nástroj escalate s vyšší úrovní (4 = ohrožení života, 3 = lékař ještě dnes, 2 = tým do následujícího pracovního dne) a krátkým důvodem, teprve potom odpověz podle nové úrovně.
Ostatní nástroje použij, jen když v kontextu něco chybí; jinak odpověz rovnou. Výstup je jen text odpovědi pro pacienta."""

ADDRESSEE = {
    "pacient": "Píše pacient sám – oslovuj přímo jeho.",
    "pecujici": "Píše pečující (blízká osoba pacienta). Oslovuj pečujícího a o pacientovi mluv ve 3. osobě; vztah pojmenuj jen tak, jak ho napsal pisatel (manželka, tatínek …), jinak piš „váš blízký“. Pokyny piš pro pečujícího (např. „nepodávejte“), ne pro pacienta.",
}


def _tool_specs() -> list[dict]:
    def spec(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {"type": "function", "function": {"name": name, "description": description,
                                                 "parameters": {"type": "object", "properties": properties, "required": required}}}

    return [
        spec("get_patient_context", "Kontext léčby pacienta: režim, den cyklu, léky s předpisem, alergie, laboratoř, otevřený úkol.", {}, []),
        spec("get_recent_checkins", "Poslední check-iny s úrovní a nálezy.", {"n": {"type": "integer"}}, []),
        spec("get_trend", "Řada měření: weight, bp_sys, bp_dia, pulse, temperature, glucose, breathing_rate, pain.",
             {"metric": {"type": "string"}, "days": {"type": "integer"}}, ["metric"]),
        spec("search_guidance", "Schválené texty pro pacienty (IRIS Vector Search).", {"query": {"type": "string"}}, ["query"]),
        spec("get_contact", "Správný kontakt pro úroveň 1–4 v aktuální čas.", {"level": {"type": "integer"}}, ["level"]),
        spec("ask_followup", "Položit pacientovi jednu doplňující otázku.", {"question": {"type": "string"}}, ["question"]),
        spec("escalate", "Zvýšit úroveň a upozornit tým, když je zpráva vážnější než triage (jen zvýšit, nikdy snížit). "
                         "2 = tým do následujícího pracovního dne, 3 = lékař ještě dnes, 4 = ohrožení života / 155.",
             {"level": {"type": "integer"}, "reason": {"type": "string"}, "evidence": {"type": "string"}}, ["level", "reason"]),
    ]


def _run_tool(patient_id: str, lang: str, name: str, arguments: dict):
    if name == "get_patient_context":
        return tools.get_patient_context(patient_id)
    if name == "get_recent_checkins":
        return tools.get_recent_checkins(patient_id, int(arguments.get("n", 5)))
    if name == "get_trend":
        return tools.get_trend(patient_id, str(arguments.get("metric", "")), int(arguments.get("days", 14)))
    if name == "search_guidance":
        return tools.search_guidance(str(arguments.get("query", "")), lang)
    if name == "get_contact":
        return tools.get_contact(int(arguments.get("level", 1)))
    if name == "ask_followup":
        return tools.ask_followup(patient_id, str(arguments.get("question", "")))
    if name == "escalate":
        return tools.escalate(patient_id, int(arguments.get("level", 0)), str(arguments.get("reason", "")), str(arguments.get("evidence", "")))
    return {"error": f"unknown tool {name}"}


def _openai():
    global _client
    loop = asyncio.get_running_loop()
    if _client is None or _client[0] is not loop:
        from openai import AsyncOpenAI

        _client = (loop, AsyncOpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=1))
    return _client[1]


async def _llm_answer(patient_id: str, lang: str, author: str, payload: dict, history: list[dict], feedback: list[str],
                      cites: list[str]) -> str | None:
    if not (settings.llm_enabled and settings.openai_api_key):
        return None
    system = SYSTEM_PROMPT.format(language="slovenčina" if lang == "sk" else "čeština",
                                  addressee=ADDRESSEE["pecujici" if author == "pecujici" else "pacient"])
    messages: list[dict] = [{"role": "system", "content": system}]
    for message in history[-8:]:
        messages.append({"role": "user" if message.get("role") == "user" else "assistant", "content": message.get("text", "")})
    content = json.dumps(payload, ensure_ascii=False, default=str)
    if feedback:
        content += "\n\nPředchozí návrh odpovědi neprošel kontrolou: " + "; ".join(feedback) + ". Napiš ho znovu a oprav to."
    messages.append({"role": "user", "content": content})
    specs = _tool_specs()
    try:
        for round_number in range(MAX_TOOL_ROUNDS + 1):
            request = {"model": settings.llm_model, "messages": messages, "max_completion_tokens": 1500, "reasoning_effort": "none"}
            if round_number < MAX_TOOL_ROUNDS:
                request["tools"] = specs
            response = await _openai().chat.completions.create(**request)
            message = response.choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip() or None
            messages.append({"role": "assistant", "content": message.content or "",
                             "tool_calls": [call.model_dump() for call in message.tool_calls]})
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    result = await asyncio.to_thread(_run_tool, patient_id, lang, call.function.name, arguments)
                except Exception as error:
                    result = {"error": type(error).__name__}
                if call.function.name == "search_guidance" and isinstance(result, list):
                    cites.extend(hit["cite"] for hit in result[:3])
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]})
    except Exception as error:
        log.warning("navigator LLM failed: %s", type(error).__name__)
    return None


def _contact_phrase(contact: str) -> str:
    if "155" in contact:
        return "Volejte ihned 155 nebo jeďte na urgentní příjem" + (f"; můžete volat i sloužícího lékaře MOÚ {ON_DUTY_PHONE}" if ON_DUTY_PHONE in contact else "") + "."
    if ON_DUTY_PHONE in contact:
        return f"Zavolejte hned sloužícímu lékaři MOÚ na číslo {ON_DUTY_PHONE}."
    if "telekonzult" in fold(contact):
        return "Lékař MOÚ vám zavolá přes monitorovací centrum do 2 hodin."
    if "do konce" in contact:
        return "Tým monitorovacího centra se vám ozve do konce následujícího pracovního dne."
    return "Tým monitorovacího centra se vám ozve následující pracovní den."


def _requirements(output: TriageOutput, card: LevelCard | None, palliative: bool, meds: list, lang: str, suicide: bool = False,
                  fever: str = "", followup: bool = False, self_medication: bool = False) -> list[str]:
    must = [f"jazyk: {'slovenčina' if lang == 'sk' else 'čeština'}, nejvýš {3 if followup else 4} krátké věty"]
    if "NAV-OPEN-EPISODE" in output.pravidla:
        must.append("platí dřívější pokyn z otevřené epizody – zopakuj ho, nic neruš a neuklidňuj; zrušit ho může jen člověk z týmu")
    if fever:
        must.append(f"přidej větu „{fever}“")
    if self_medication:
        must.append(f"odpověz na dotaz na lék smyslem věty „{_self_medication_line(lang == 'sk', output.adresat == 'pecujici')}“ – rozhoduje lékař")
    if card is not None and card.kontakt:
        must.append(f"kontakt a čas řekni přirozeně, smyslem této věty (přelož do jazyka odpovědi, text karty nekopíruj): „{_contact_phrase(card.kontakt)}“")
    if suicide and lang == "cs":
        must.append("nabídni i Linku první psychické pomoci 116 123 (nonstop)")
    if output.uroven == 4:
        must.append(f"první věta začíná slovem „{'Volajte' if lang == 'sk' else 'Volejte'}“ a obsahuje 155")
    if palliative and output.uroven in (2, 3):
        must.append("zmiň 24h linku paliativního týmu nebo hospice (když se nedovolají, 155)")
    # an emergency or fever reply never quotes a dose: next to "no Paralen" a Paracetamol line reads as permission
    for med in [] if output.uroven == 4 or fever else meds[:1]:
        must.append(f"předpis jen zopakuj větou „Podle předpisu: {med.lek} {med.davka}, {med.frekvence}.“ – nikdy nepiš, že další dávku můžete/smíte dát; o tom rozhoduje lékař")
    return must


# ---------- history ----------

def _store():
    return tools.store()


def _resolvable_level(output: TriageOutput) -> int:
    """A contradiction / verify question may lower the episode once answered (spec §8.6); other questions never do."""
    return output.uroven if RESOLVABLE_RULES & set(output.pravidla) else 0


def _checkin_followup(patient_id: str, at: datetime) -> tuple[str, str, int] | None:
    """The follow-up question of the patient's last check-in, while the chat has not moved on since it."""
    live = _store()
    if live is None:
        return None
    outputs = [output for output in live.get_patient_outputs(patient_id) if output.zdroj != "chat" and output.as_of <= at]
    last = outputs[-1] if outputs else None
    if last is None or not last.doplnujici_otazka or (at - last.as_of).total_seconds() > 24 * 3600:
        return None
    if any(message.get("role") == "user" and message.get("at", "") > last.as_of.isoformat() for message in history(patient_id)[:-1]):
        return None
    checkin = live.get_checkin(last.checkin_id)
    return (checkin.zprava_pacienta or "") if checkin else "", last.doplnujici_otazka, _resolvable_level(last)


def _followup_text(pending: tuple[str, str, int], answer: str) -> tuple[str, bool]:
    """(text to triage, whether the answer answers the question). The question's own words ("…nebo nejde probudit?") join the
    text only for a bare yes or number. A count supersedes only the counts the question asked about, a temperature only its
    temperature; an answer about something else (an unrelated number included) leaves them and answers nothing."""
    folded = fold(answer)
    yes = re.match(r"\W*(ano|jo|jj)\b", folded)
    bare = re.fullmatch(r"\W*\d+(?:[.,]\d+)?\W*", folded)
    count = bare or _count(folded)
    temperature = bare or re.search(r"\b(3[5-9]|4[0-2])([.,]\d)?\b", folded)
    earlier = f"{pending[0]}\n{pending[1]}" if yes or bare else pending[0]
    superseded = False
    for number, unit in set(re.findall(r"(\d+(?:[.,]\d+)?)\s*(×|°)?", pending[1])):
        if (count and unit != "°") or (temperature and unit == "°"):
            earlier = re.sub(rf"(?<![\d.,]){re.escape(number)}(?![\d]|[.,]\d)\s*(?:×|x\b|-?\s?krat|-?\s?krát)?", "…", earlier)
            superseded = True
    return f"{earlier}\n{answer}", bool(yes or superseded or re.match(r"\W*(ne|nie)\b", folded))


def _open_episode_floor(patient_id: str, output: TriageOutput, at: datetime, answered_level: int = 0) -> TriageOutput:
    """While an orange/red task is open, a chat message cannot bring the patient's level or instruction below it (spec §9).
    An answer that resolves the task's own contradiction / verify question lifts the floor for that task at that level, until a
    new orange or red message or a new check-in."""
    live = _store()
    task = live.open_task(patient_id) if live is not None and hasattr(live, "open_task") else None
    if task is None or task.uroven < 3:
        return output
    resolved = _resolved.get(patient_id)
    if output.uroven >= 3 or (resolved and any(item.zdroj != "chat" and resolved[2] < item.as_of <= at
                                                for item in live.get_patient_outputs(patient_id))):
        _resolved.pop(patient_id, None)
    if output.uroven < 3 and answered_level >= task.uroven:
        _resolved[patient_id] = (task.id, task.uroven, at)
    resolved = _resolved.get(patient_id)
    if task.uroven <= output.uroven or answered_level >= task.uroven or (resolved and resolved[:2] == (task.id, task.uroven)):
        return output
    step, contact, _notify, sla = tools.route(task.uroven, at)
    return output.model_copy(update={
        "uroven": task.uroven, "doporuceny_krok": step, "doporuceny_kontakt": contact, "upozornit_tym": True, "sla_do": sla,
        "pravidla": [*output.pravidla, "NAV-OPEN-EPISODE"],
        "zduvodneni": f"Otevřená epizoda úrovně {task.uroven} ({task.why}) – zpráva v chatu ji nesnižuje, uzavírá ji člověk z týmu.",
        "klicove_nalezy": [task.why, *output.klicove_nalezy], "varovne_priznaky": [task.why, *output.varovne_priznaky],
    })


def history(patient_id: str) -> list[dict]:
    """The patient's current conversation; the team's timeline reads every message from the store."""
    live = _store()
    return live.visible_chat(patient_id) if live is not None else list(_fallback_history.get(patient_id, []))


def hide_history(patient_id: str) -> None:
    """Hides the conversation from the patient's chat and starts a new one: nothing is deleted, the team keeps seeing it."""
    live = _store()
    if live is not None:
        live.hide_chat(patient_id)
    _pending.pop(patient_id, None)
    tools.pop_followup(patient_id)


def _add_message(patient_id: str, message: dict) -> dict:
    live = _store()
    if live is not None:
        stored = live.add_chat(patient_id, message)
    else:
        stored = {"id": f"m{len(_fallback_history.get(patient_id, [])) + 1}", "at": tools.now().isoformat(), **message}
        _fallback_history.setdefault(patient_id, []).append(stored)

    def write() -> None:
        try:
            from app.fhir.writers import write_chat

            write_chat(patient_id, stored)
        except Exception:
            pass

    threading.Thread(target=write, daemon=True, name="fhir-chat").start()
    return stored


def _alert(output: TriageOutput, raise_task: bool = True, nlu: NluResult | None = None) -> None:
    """Records the turn's output (with its facts, for the symptom stats) and raises the task from level 2."""
    live = _store()
    if live is None:
        log.warning("level %s from chat but no store to raise a task", output.uroven)
        return
    try:
        live.record_output(None, output, nlu=nlu)
        if output.uroven >= 2 and raise_task:
            live.raise_task(output)
    except Exception:
        log.exception("alert hook failed")


# ---------- pipeline ----------

def _chunks(text: str) -> list[str]:
    words = text.split(" ")
    return [" ".join(words[index : index + 3]) + (" " if index + 3 < len(words) else "") for index in range(0, len(words), 3)]


async def stream_chat_turn(patient_id: str, text: str, author: str, lang: str | None = None,
                           at: datetime | None = None) -> AsyncIterator[dict]:
    """The turn runs in its own task: a patient who closes the app after the red card must not cancel the team's alert."""
    events: asyncio.Queue = asyncio.Queue()

    async def run() -> None:
        lock = _locks.setdefault(patient_id, asyncio.Lock())
        async with lock:
            try:
                async for event in _turn(patient_id, text.strip(), "pecujici" if author == "pecujici" else "pacient", lang, at):
                    events.put_nowait(event)
            except Exception:
                log.exception("chat turn failed")
                sk = lang == "sk"
                safe = (f"Prepáčte, odpoveď sa nepodarilo pripraviť. Ak sa necítite dobre, volajte 155 alebo službukonajúceho lekára MOÚ {ON_DUTY_PHONE}."
                        if sk else f"Omlouváme se, odpověď se nepodařilo připravit. Pokud se necítíte dobře, volejte 155 nebo sloužícího lékaře MOÚ {ON_DUTY_PHONE}.")
                events.put_nowait({"event": "delta", "data": safe})
                events.put_nowait({"event": "done", "data": NavigatorReply(reply_text=safe, lang="sk" if sk else "cs")})
            finally:
                events.put_nowait(None)

    task = asyncio.create_task(run())
    _turns.add(task)
    task.add_done_callback(_turns.discard)
    while (event := await events.get()) is not None:
        yield event


def _escalated(patient_id: str, output: TriageOutput, at: datetime) -> TriageOutput | None:
    """The output raised to the level escalate set during this turn, or None."""
    level = tools.floor(patient_id)
    if level <= output.uroven:
        return None
    step, contact, _notify, sla = tools.route(level, at)
    return output.model_copy(update={"uroven": level, "doporuceny_krok": step, "doporuceny_kontakt": contact, "upozornit_tym": True,
                                     "sla_do": sla, "pravidla": [*output.pravidla, "NAV-ESCALATE"]})


async def _turn(patient_id: str, text: str, author: str, lang: str | None, at: datetime | None) -> AsyncIterator[dict]:
    patient = load_patient(patient_id)
    at = at or tools.now()
    ctx = await asyncio.to_thread(tools.context_for, patient, at)
    lang = lang if lang in ("cs", "sk") else ctx.lang
    previous = history(patient_id)
    _add_message(patient_id, {"role": "user", "author": author, "text": text})

    pending = (_pending.pop(patient_id, None) if previous else None) or _checkin_followup(patient_id, at)
    triage_text, answered = _followup_text(pending, text) if pending else (text, False)
    answered_level = pending[2] if answered else 0
    if answered_level:
        # the answer resolves only what the message set: a level from the check-in form (a measured fever) stays until the team acts
        earlier_nlu = await asyncio.to_thread(_analyze, pending[0], ctx, author, lang, False)
        if (await asyncio.to_thread(_triage, patient_id, pending[0], author, ctx, earlier_nlu, at, lang)).uroven < answered_level:
            answered_level = 0
    # ponytail: the rules-only card goes out first (fast); the LLM facts can only add, so a second card only ever raises it
    quick_nlu = await asyncio.to_thread(_analyze, triage_text, ctx, author, lang, False)
    quick_raw = await asyncio.to_thread(_triage, patient_id, triage_text, author, ctx, quick_nlu, at, lang)
    quick = _open_episode_floor(patient_id, quick_raw, at, answered_level)
    card = level_card(quick)
    if card is not None:
        yield {"event": "card", "data": card}
    nlu = await asyncio.to_thread(_analyze, triage_text, ctx, author, lang)
    raw = await asyncio.to_thread(_triage, patient_id, triage_text, author, ctx, nlu, at, lang)
    if raw.uroven < quick_raw.uroven:
        raw = quick_raw
    output = _open_episode_floor(patient_id, raw, at, answered_level)
    tools.set_floor(patient_id, output.uroven)
    if output.uroven > quick.uroven:
        card = level_card(output)
        yield {"event": "card", "data": card}
    await asyncio.to_thread(_alert, output, "NAV-OPEN-EPISODE" not in output.pravidla, nlu)

    folded = fold(" ".join([triage_text, *output.varovne_priznaky]))
    # "no Paralen" belongs to fever during chemotherapy (do not mask neutropenia), not to 40 °C outside it; the warning signs
    # carry a fever only when a rule fired on it, so "Teplotu nemám, ale zvracím" gets no Paralen line
    fever = _paralen_line(lang == "sk", output.adresat == "pecujici", ctx.sex) if (
        output.uroven == 4 and output.pravidla != ["R-HYPERPYREXIA"]
        and re.search(r"teplot|horec|horuc|zimnic|\btres|\btras|3[89][.,]\d", fold(" ".join(output.varovne_priznaky)))) else ""
    suicide = bool(re.search(SUICIDE, folded))
    hopeless = suicide or bool(re.search(HOPELESS, folded))
    palliative = tools.palliative_care(ctx)
    meds = mentioned_meds(text, ctx)
    message = fold(text)
    prescribed = fold(" ".join(med.lek for med in ctx.meds))
    self_medication = (any(drug not in prescribed for drug in re.findall(OTC_DRUGS, message))
                       or bool((meds or re.search(r"\b(lek|liek|tablet|prask)", message)) and re.search(r"vysad|vymen|nahrad|\bmisto\b|\bmiesto\b", message)))
    guidance = await asyncio.to_thread(tools.search_guidance, " ".join([text, *(med.indikace for med in meds), *output.klicove_nalezy[:2]]), lang)
    cites = [hit["cite"] for hit in guidance[:3]]
    followup = output.doplnujici_otazka if not (pending and output.doplnujici_otazka == pending[1]) else None
    payload = {
        "message": text,
        "author": author,
        "now": at.isoformat(timespec="minutes"),
        "triage": {"level": output.uroven, "step": output.doporuceny_krok, "findings": output.klicove_nalezy,
                   "warning_signs": output.varovne_priznaky, "approved_patient_reply": (output.doporuceni_pro_pacienta or None) if output.uroven >= 2 else None},
        "level_card": card.model_dump(mode="json") if card else None,
        "followup_question": followup,
        "patient": {"age": ctx.age, "sex": ctx.sex, "diagnosis": ctx.diagnosis, "regimen": ctx.regimen, "intent": ctx.intent,
                    "palliative": palliative, "cycle": ctx.cycle, "cycle_day": ctx.cycle_day, "chemo_window": ctx.chemo_window,
                    "meds": tools.med_lines(ctx), "allergies": ctx.allergies},
        "guidance": [{"cite": hit["cite"], "text": hit["text"]} for hit in guidance],
    }
    payload["must"] = _requirements(output, card, palliative, meds, lang, hopeless, fever, bool(followup), self_medication)
    allowed_text = " ".join(hit["text"] for hit in guidance)
    reply_text = None
    feedback: list[str] = []
    # ponytail: a suicide crisis always gets the vetted template, never free LLM text
    for _attempt in range(0 if output.uroven == 4 and suicide else 3):
        candidate = await _llm_answer(patient_id, lang, author, payload, previous, feedback, cites)
        if candidate is None:
            break
        if raised := _escalated(patient_id, output, at):
            output, card = raised, level_card(raised)
            yield {"event": "card", "data": card}
            payload["triage"].update(level=output.uroven, step=output.doporuceny_krok)
            payload["level_card"] = card.model_dump(mode="json")
            payload["must"] = _requirements(output, card, palliative, meds, lang, hopeless, fever, bool(followup), self_medication)
        candidate = " ".join(candidate.split())
        if followup:
            candidate = " ".join(part for part in re.split(r"(?<=[.!?])\s+", candidate) if fold(part) != fold(followup))
        feedback = validate(f"{candidate} {followup}" if followup else candidate, output, ctx, lang, allowed_text)
        if re.search(r"paralen|paracetamol", fold(candidate)) and not re.search(r"paralen|paracetamol", fold(" ".join([text, *payload["must"]]))):
            feedback.append("Paralen ani léky na horečku nezmiňuj, pole must to nepožaduje")
        if not feedback:
            reply_text = candidate
            break
        log.warning("navigator reply rejected: %s", feedback)
        feedback = [f"návrh: „{candidate}“", *feedback]
    # ponytail: the model may tell the patient to call 155 without calling escalate; its own words then raise the alert
    if reply_text and tools.floor(patient_id) < 4 and urges_155(reply_text):
        await asyncio.to_thread(tools.escalate, patient_id, 4, "navigátor v odpovědi vyzval k volání 155", text)
    if raised := _escalated(patient_id, output, at):
        output, card = raised, level_card(raised)
        yield {"event": "card", "data": card}
        if reply_text and validate(reply_text, output, ctx, lang, allowed_text):
            reply_text = None
    if "NAV-ESCALATE" in output.pravidla:
        await asyncio.to_thread(_alert, output, False, nlu)
    generated_by = "llm" if reply_text else "template"
    if reply_text is None:
        reply_text = template(output, lang, palliative, fever, suicide, meds, self_medication)
    llm_followup = tools.pop_followup(patient_id)
    followup = followup or llm_followup
    if followup:
        if fold(followup) not in fold(reply_text):
            reply_text = f"{reply_text} {followup}"
        # the level before the open-episode floor: answering a verify question must not release some other open episode
        _pending[patient_id] = (triage_text, followup, _resolvable_level(raw))

    reply = NavigatorReply(
        reply_text=reply_text, lang=lang, level_card=card, followup_question=followup,
        facts=[fact if isinstance(fact, Fact) else Fact.model_validate(fact) for fact in nlu.facts],
        cites=list(dict.fromkeys(cites)), escalated=output.uroven >= 2, triage=output,
    )
    _add_message(patient_id, {"role": "navigator", "author": "navigator", "text": reply_text,
                              "level_card": card.model_dump(mode="json") if card else None, "followup_question": followup,
                              "generated_by": generated_by})
    for piece in _chunks(reply_text):
        yield {"event": "delta", "data": piece}
        await asyncio.sleep(0.02)
    yield {"event": "done", "data": reply}


async def chat_turn(patient_id: str, text: str, author: str, lang: str | None = None, at: datetime | None = None) -> NavigatorReply:
    reply = None
    async for event in stream_chat_turn(patient_id, text, author, lang, at):
        if event["event"] == "done":
            reply = event["data"]
    return reply
