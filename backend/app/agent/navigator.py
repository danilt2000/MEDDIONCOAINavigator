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

log = logging.getLogger("navigator")

VERSION = "navigator 0.1.0"
MAX_TOOL_ROUNDS = 3
ON_DUTY_PHONE = "724 590 848"

_fallback_history: dict[str, list[dict]] = {}
_pending: dict[str, tuple[str, str, int]] = {}
RESOLVABLE_RULES = {"C-CONTRADICTION", "U-VERIFY"}
_locks: dict[str, asyncio.Lock] = {}
_turns: set[asyncio.Task] = set()
_client = None


def fold(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char))


# ---------- conservative lexicon (engine fallback and red-flag safety net) ----------

SUICIDE = r"zabi(t|ju|jem|t sa)|spolknu|vsechny prasky|vsetky tabletky|vsechny tablety|ublizit si|ublizim si|ukoncim to|skoncim to|nechci tu byt|nechcem tu byt|vzit si zivot|vziat si zivot|skoncit (se|so) zivotem|skoncit so zivotom|sebevrazd|samovrazd|predavkuj|obesit|obesim|skocim|skocit z"
SUICIDE_PLAN = r"plan|priprav|prasky|tablet|naspor|nasetr|promysl|premysl|dnes|zitra|zajtra|vim jak|viem ako|provaz|skocim|mam doma|mam u sebe"
HOPELESS = r"uz nemuzu dal|uz nevladzem|nema to cenu|nema to zmysel|nechci (uz )?zit|nechcem (uz )?zit|chci umrit|chcem zomriet"
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
NO_FEVER = r"(nemam|nema|bez|zadn\w*|ziadn\w*)\s+(\w+\s+)?(horeck|horuck|teplot|zimnic)|teplot\w* (je |mam |ma )?(normaln|v poradku|v poriadku|ok\b)"
SYMPTOMS = r"bolest|bolet|boli|nevoln|zvrac|prujem|prujm|hnack|stolic|zacp|unav|slab|kasl|kasel|otok|oteklo|vyrazk|afty|pali|svedi|krvac|modrin|zavrat|tocit|necit|brneni|smut|uzkost|nespim|vycerp|teplot|horec|horuc|zimnic"
DOSE_QUESTION = r"(muzu|mozem|smim|smiem|mam|dat|podat|vzit|zobrat|uzit|pridat|zvysit|dalsi|jeste|este|vic|viac)\b.*\b(davk|oramorph|morfin|tablet|lek|liek|prasek|kapk|loperamid|paralen|paracetamol|ibalgin|ibuprofen|novalgin)"


def _numbers(pattern: str, text: str) -> list[float]:
    return [float(match.group(1).replace(",", ".")) for match in re.finditer(pattern, text)]


def lexicon_level(text: str, ctx: PatientContext, lang: str) -> tuple[int, list[str], str | None]:
    """(level, findings, follow-up question). Escalates when unsure; never used to lower the engine's level."""
    folded = fold(text)
    sk = lang == "sk"
    found: list[tuple[int, str]] = []
    question = None
    chemo = ctx.chemo_window or "cytotoxic" in ctx.drug_classes or not ctx.drug_classes
    temperatures = _numbers(r"\b(3[5-9](?:[.,]\d)?|4[0-2](?:[.,]\d)?)\s*(?:°|stup|c\b)", folded)
    temperatures += _numbers(r"\b(3[5-9][.,]\d|4[0-2][.,]\d)\b", folded)
    if re.search(r"teplot|horec|horuc|namer", folded):
        temperatures += _numbers(r"\b(3[5-9]|4[0-2])\b", folded)
    chills = re.search(r"zimnic|tresavk|triask|\btres(e|u)\b|\btras(ie|iem|u)\b|klepu se", folded)
    if (temperatures and max(temperatures) >= 38.0) or chills:
        found.append((4 if chemo else 3, "teplota ≥ 38 °C nebo zimnice" + (" během chemoterapie" if chemo else "")))
    elif re.search(NO_FEVER, folded):
        pass
    elif re.search(r"horec|horuc", folded):
        found.append((4 if chemo else 3, "hlášená horečka"))
    elif re.search(r"teplot", folded) and not temperatures:
        found.append((3, "zvýšená teplota bez hodnoty"))
        question = "Koľko stupňov ste namerali?" if sk else "Kolik stupňů jste naměřil/a?"
    if re.search(SUICIDE, folded):
        found.append((4 if re.search(SUICIDE_PLAN, folded) else 3, "myšlenky na sebevraždu"))
    elif re.search(HOPELESS, folded):
        found.append((3, "výroky beznaděje"))
    for finding, pattern in RED_FLAGS.items():
        if re.search(pattern, folded):
            found.append((4, finding))
    stools = _numbers(r"(\d+)\s*(?:x|×|-?krat)(?![a-z])", folded) if re.search(r"prujem|prujm|hnack|stolic", folded) else []
    if stools:
        count = max(stools)
        found.append((4 if count >= 7 else 3 if count >= 4 else 2, f"průjem asi {count:g}× za den"))
    elif re.search(r"prujem|prujm|hnack", folded):
        found.append((2, "průjem bez počtu stolic"))
        question = question or ("Koľkokrát ste mali hnačku za posledných 24 hodín?" if sk else "Kolikrát jste měl/a průjem za posledních 24 hodin?")
    vomits = _numbers(r"(\d+)\s*(?:x|×|-?krat)(?![a-z])", folded) if re.search(r"zvrac|vracia|vraci", folded) and not stools else []
    if vomits:
        found.append((4 if max(vomits) > 5 else 2, f"zvracení {max(vomits):g}× za den"))
    if re.search(r"neudrz\w* (ani )?(vodu|tekutin|nic|pit)|nemuze pit|nemoze pit|nemoc\w* (uz )?\d+|nemoci od|nemocila|nemocil\b|nemocim\b", folded):
        found.append((3, "neudrží tekutiny / málo močí"))
    if re.search(r"hrozn\w* bolest|bolest\w* hrozn|nesnesiteln|ani po (\d+ )?(davk|tablet|oramorph)|nepomaha|nepomohl|nepovolil|nepomohl", folded):
        found.append((3, "silná bolest nereagující na léky"))
    if re.search(DOSE_QUESTION, folded):
        found.append((2, "dotaz na další dávku léku – rozhoduje tým"))
        if re.search(r"oramorph|morfin|bolest|bolet|\bboli|tramal|novalgin|ibalgin|ibuprofen", folded):
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
    level, findings, question = lexicon_level(text, ctx, lang)
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
            output = triage_chat(patient_id, text, author, ctx, nlu, at, use_llm=False)
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


def template(output: TriageOutput, lang: str, palliative: bool, fever: bool, suicide: bool, meds: list = []) -> str:
    sk = lang == "sk"
    contact = output.doporuceny_kontakt or ""
    prescription = " ".join(
        (f"Podľa predpisu: {med.lek} {med.davka}, {med.frekvence}; o ďalšej dávke navyše rozhoduje lekár." if sk
         else f"Podle předpisu: {med.lek} {med.davka}, {med.frekvence}; o další dávce navíc rozhoduje lékař.")
        for med in meds[:1]
    )
    level_text = _level_template(output, contact, sk, palliative, fever, suicide)
    return f"{prescription} {level_text}" if prescription and output.uroven < 4 else level_text


def _palliative_line(sk: bool) -> str:
    return ("V paliatívnej starostlivosti môžete kedykoľvek volať 24h linku paliatívneho tímu alebo hospicu." if sk
            else "V paliativní péči můžete kdykoli volat 24h linku paliativního týmu nebo hospice.")


def _level_template(output: TriageOutput, contact: str, sk: bool, palliative: bool, fever: bool, suicide: bool) -> str:
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
            parts.append("Paralen neužívajte, kým vás nevyšetrí lekár." if sk else "Paralen neužívejte, dokud vás nevyšetří lékař.")
        return " ".join(parts)
    if output.uroven == 3:
        if ON_DUTY_PHONE in contact:
            who = (f"Zavolajte prosím ihneď službukonajúcemu lekárovi MOÚ na číslo {ON_DUTY_PHONE}." if sk
                   else f"Zavolejte prosím hned sloužícímu lékaři MOÚ na číslo {ON_DUTY_PHONE}.")
        else:
            who = ("Lekár MOÚ vám zavolá cez monitorovacie centrum do 2 hodín." if sk
                   else "Lékař MOÚ vám zavolá přes monitorovací centrum do 2 hodin.")
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
5. Paralen zmiň jen tehdy, když pacient hlásí horečku nebo zimnici, a to jen větou „Paralen neužívejte, dokud vás nevyšetří lékař.“ Jinak léky na horečku nezmiňuj.
6. Odpovídej výhradně v jazyce: {language}. Nejvýš 4 krátké věty, jednoduchá slova bez odborných termínů, vykej.
7. {addressee}
8. Vycházej jen ze schválených textů (guidance) a z údajů pacienta v kontextu. Když si nejsi jistý, nabídni předání týmu. Nikdy nepiš jména ani data narození.
9. Doplňující otázku (followup_question) připojí systém sám za tvou odpověď – nepiš ji ani jinou otázku na totéž.
10. Když zpráva popisuje něco vážnějšího, než ukazuje triage (např. náhlý pokles koutku, porucha řeči, zraku nebo síly jedné strany těla, bezvědomí, silné krvácení), nejdřív zavolej nástroj escalate s vyšší úrovní (4 = ohrožení života, 3 = lékař ještě dnes, 2 = tým do následujícího pracovního dne) a krátkým důvodem, teprve potom odpověz podle nové úrovně.
Ostatní nástroje použij, jen když v kontextu něco chybí; jinak odpověz rovnou. Výstup je jen text odpovědi pro pacienta."""

ADDRESSEE = {
    "pacient": "Píše pacient sám – oslovuj přímo jeho.",
    "pecujici": "Píše pečující (blízká osoba, např. dcera). Oslovuj pečujícího a o pacientovi mluv ve 3. osobě (např. „maminka“).",
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
                  fever: bool = False, followup: bool = False) -> list[str]:
    must = [f"jazyk: {'slovenčina' if lang == 'sk' else 'čeština'}, nejvýš {3 if followup else 4} krátké věty"]
    if "NAV-OPEN-EPISODE" in output.pravidla:
        must.append("platí dřívější pokyn z otevřené epizody – zopakuj ho, nic neruš a neuklidňuj; zrušit ho může jen člověk z týmu")
    if fever:
        must.append("přidej větu „" + ("Paralen neužívajte, kým vás nevyšetrí lekár." if lang == "sk" else "Paralen neužívejte, dokud vás nevyšetří lékař.") + "“")
    if card is not None and card.kontakt:
        must.append(f"kontakt a čas řekni přirozeně, smyslem této věty (přelož do jazyka odpovědi, text karty nekopíruj): „{_contact_phrase(card.kontakt)}“")
    if suicide and lang == "cs":
        must.append("nabídni i Linku první psychické pomoci 116 123 (nonstop)")
    if output.uroven == 4:
        must.append(f"první věta začíná slovem „{'Volajte' if lang == 'sk' else 'Volejte'}“ a obsahuje 155")
    if palliative and output.uroven in (2, 3):
        must.append("zmiň 24h linku paliativního týmu nebo hospice (když se nedovolají, 155)")
    for med in meds[:2]:
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
    if any(message.get("role") == "user" and message.get("at", "") > last.as_of.isoformat() for message in live.list_chat(patient_id)[:-1]):
        return None
    checkin = live.get_checkin(last.checkin_id)
    return (checkin.zprava_pacienta or "") if checkin else "", last.doplnujici_otazka, _resolvable_level(last)


def _followup_text(pending: tuple[str, str, int], answer: str) -> str:
    """An answer with its own numbers supersedes only the numbers the question asked about; a bare 'yes' keeps them."""
    earlier = f"{pending[0]}\n{pending[1]}"
    if re.search(r"\d", answer):
        for number in set(re.findall(r"\d+(?:[.,]\d+)?", pending[1])):
            earlier = re.sub(rf"(?<![\d.,]){re.escape(number)}(?![\d]|[.,]\d)\s*(?:×|x\b|-?\s?krat|-?\s?krát)?", "…", earlier)
    return f"{earlier}\n{answer}"


def _open_episode_floor(patient_id: str, output: TriageOutput, at: datetime, answered_level: int = 0) -> TriageOutput:
    """While an orange/red task is open, a chat message cannot bring the patient's level or instruction below it (spec §9)."""
    live = _store()
    task = live.open_task(patient_id) if live is not None and hasattr(live, "open_task") else None
    if task is None or task.uroven < 3 or task.uroven <= output.uroven or answered_level >= task.uroven:
        return output
    step, contact, _notify, sla = tools.route(task.uroven, at)
    return output.model_copy(update={
        "uroven": task.uroven, "doporuceny_krok": step, "doporuceny_kontakt": contact, "upozornit_tym": True, "sla_do": sla,
        "pravidla": [*output.pravidla, "NAV-OPEN-EPISODE"],
        "zduvodneni": f"Otevřená epizoda úrovně {task.uroven} ({task.why}) – zpráva v chatu ji nesnižuje, uzavírá ji člověk z týmu.",
        "klicove_nalezy": [task.why, *output.klicove_nalezy], "varovne_priznaky": [task.why, *output.varovne_priznaky],
    })


def history(patient_id: str) -> list[dict]:
    live = _store()
    return live.list_chat(patient_id) if live is not None else list(_fallback_history.get(patient_id, []))


def clear_history(patient_id: str) -> None:
    """Clears the patient's chat view only: team tasks, alerts and the FHIR copy of every message stay."""
    live = _store()
    if live is not None:
        live.clear_chat(patient_id)
    _fallback_history.pop(patient_id, None)
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
    triage_text = _followup_text(pending, text) if pending else text
    answered_level = pending[2] if pending else 0
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
    fever = output.uroven == 4 and bool(re.search(r"teplot|horec|horuc|zimnic|\btres|\btras|3[89][.,]\d", folded))
    suicide = bool(re.search(SUICIDE + "|" + HOPELESS, folded))
    palliative = tools.palliative_care(ctx)
    meds = mentioned_meds(text, ctx)
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
    payload["must"] = _requirements(output, card, palliative, meds, lang, suicide, fever, bool(followup))
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
            payload["must"] = _requirements(output, card, palliative, meds, lang, suicide, fever, bool(followup))
        candidate = " ".join(candidate.split())
        if followup:
            candidate = " ".join(part for part in re.split(r"(?<=[.!?])\s+", candidate) if fold(part) != fold(followup))
        feedback = validate(f"{candidate} {followup}" if followup else candidate, output, ctx, lang, allowed_text)
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
        reply_text = template(output, lang, palliative, fever, suicide, meds)
    llm_followup = tools.pop_followup(patient_id)
    followup = followup or llm_followup
    if followup:
        if fold(followup) not in fold(reply_text):
            reply_text = f"{reply_text} {followup}"
        _pending[patient_id] = (triage_text, followup, _resolvable_level(output))

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
