import re
import unicodedata

from app.models import Lek

MAX_SENTENCES = 4
MAX_CHARS = 600


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part]


DIAGNOSIS = re.compile(
    r"\b(?:febriln\w*|neutropen\w*|seps(?:e|a|i|y|ou|u)\b|septick\w*|kolitid\w*|srdecn\w* selhan\w*|selhan\w* srdce"
    r"|srdcov\w* zlyhan\w*|zlyhan\w* srdca|tromboz\w*|embol\w*|ketoacidoz\w*|infarkt\w*|metastaz\w*|pneumonitid\w*"
    r"|zapal\w* plic|zapal\w* pluc|hepatitid\w*|nefritid\w*|ileus\w*|perforac\w*|mrtvic\w*|mozkov\w* prihod\w*"
    r"|meningitid\w*|anafylax\w*|pankreatitid\w*|kardiotoxic\w*|mukozitid\w*|dehydratac\w*|infekc\w*"
    r"|progres\w* nador\w*|recidiv\w*)"
)

REASSURANCE = re.compile(
    r"\b(?:nemusite (?:se|sa) bat|nebojte|nemate se ceho bat|nic vazne\w*|neni to vazne|nie je to vazne|nic se nedeje"
    r"|(?:je|jsou) (?:to )?(?:uplne |zcela )?normaln\w*|neznepokoj\w*|zadny strach|ziadny strach|bez obav"
    r"|bude (?:to )?(?:vsechno )?v poradku|bude (?:to )?(?:vsetko )?v poriadku|bude (?:to )?dobre|netreba sa (?:bat|znepokojovat))"
)

TIME_WORDS = re.compile(
    r"\b(?:ihned|hned|okamzit\w*|dnes|dneska|do \d+ hod\w*|behem|do konce|do konca|nasledujic\w*|nasledujuc\w*"
    r"|zitra|zajtra|teraz|ted|nejdrive|nejpozdeji|najneskor)\b"
)

CALL_TO_ACTION = re.compile(r"\s*(?:ihned |hned |okamzite )?vol[ae]jte\b")

DOSE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|ug|g|ml|iu|tbl|tablet\w*|tabliet\w*|kaps\w*|kapk\w*|kvapk\w*|sáč\w*|dávk\w*|dávok)\b",
    re.IGNORECASE,
)

TREATMENT_CHANGE = re.compile(
    r"\b(?:zvyste|zvysujte|snizte|snizujte|znizte|znizujte|zdvojnasobte|vysadte|prestante (?:uzivat|brat|podavat)"
    r"|(?:vezmete|vezmite|uzijte|dejte|podejte|dajte|podajte) (?:si |ji |jej |mu |jim |ju )?(?:jeste|este|dalsi|dalsiu|navic|navyse))"
)

NEGATED_IMPERATIVE = re.compile(r"\bne(?:uzivej|uzivaj|ber|podavej|podavaj|davej|davaj|dav)\w*")

DRUGS = {
    "paralen": "paracetamol", "panadol": "paracetamol", "paracetamol": "paracetamol",
    "ibalgin": "ibuprofen", "nurofen": "ibuprofen", "brufen": "ibuprofen", "ibuprofen": "ibuprofen",
    "aspirin": "acetylsalicyl", "acylpyrin": "acetylsalicyl", "anopyrin": "acetylsalicyl",
    "novalgin": "metamizol", "metamizol": "metamizol", "voltaren": "diklofenak", "diklofenak": "diklofenak",
    "aulin": "nimesulid", "nimesulid": "nimesulid", "tramal": "tramadol", "tramadol": "tramadol",
    "kodein": "kodein", "morfin": "morfin", "oramorph": "morfin", "fentanyl": "fentanyl", "oxykodon": "oxykodon",
    "imodium": "loperamid", "loperamid": "loperamid", "smecta": "diosmektit", "endiaron": "endiaron",
    "degan": "metoklopramid", "metoklopramid": "metoklopramid", "ondansetron": "ondansetron",
    "prednison": "prednison", "dexametazon": "dexametazon", "hydrokortizon": "hydrokortizon",
    "antibiotik": "antibiotik", "amoxicilin": "amoxicilin", "augmentin": "amoxicilin",
    "warfarin": "warfarin", "heparin": "heparin", "clexane": "enoxaparin", "fraxiparin": "nadroparin",
    "inzulin": "inzulin", "metformin": "metformin", "furosemid": "furosemid",
    "makrogol": "makrogol", "laktuloz": "laktuloz", "guttalax": "pikosiran", "bisakodyl": "bisakodyl",
    "diazepam": "diazepam", "lexaurin": "bromazepam", "neurol": "alprazolam", "alprazolam": "alprazolam",
    "zolpidem": "zolpidem", "stilnox": "zolpidem",
}
DRUG_PATTERN = re.compile(r"\b(" + "|".join(DRUGS) + r")\w*")

SK_MARKERS = re.compile(
    r"[äôľĺŕ]|\b(?:volajte|ak|alebo|lekár\w*|ešte|ďakujeme|ihneď|hneď|nie|sa|môž\w*|bolesť|horúčk\w*|hnačk\w*|ozvite)\b"
)
CS_MARKERS = re.compile(
    r"[řůě]|\b(?:volejte|pokud|nebo|lékař\w*|ještě|děkujeme|ihned|hned|se|jsme|jste|když|průjem\w*|horečk\w*)\b"
)


def _med_texts(meds: list[Lek]) -> list[str]:
    return [" ".join(part for part in (med.lek, med.davka, med.frekvence) if part) for med in meds]


def _compact(text: str) -> str:
    return re.sub(r"(\d)\s+(?=[^\W\d_])", r"\1", " ".join(text.lower().split()))


def _without_meds(text: str, meds: list[Lek]) -> str:
    for med in meds:
        for part in (med.frekvence, med.davka, med.lek):
            if part:
                text = text.replace(part, " ")
    return text


def _contact_problems(norm_text: str, contact: str | None) -> list[str]:
    if not contact:
        return [] if re.search(r"155|monitorovac|lekar|\bt[yi]m", norm_text) else ["missing_contact"]
    norm_contact = normalize(contact)
    if "155" in contact:
        required = r"155"
    elif "724 590 848" in contact:
        required = r"724 590 848"
    elif "telekonzult" in norm_contact:
        required = r"lekar|telekonzult"
    elif "monitorovac" in norm_contact:
        required = r"monitorovac|\bt[yi]m\w*|sestr"
    else:
        required = r"155|monitorovac|lekar|\bt[yi]m"
    return [] if re.search(required, norm_text) else [f"missing_contact: {contact}"]


def _dose_problems(text: str, meds: list[Lek]) -> list[str]:
    med_texts = [_compact(med_text) for med_text in _med_texts(meds)]
    problems = []
    for match in DOSE.finditer(text):
        token = _compact(match.group(0))
        if not any(re.search(rf"(?<![\d,.]){re.escape(token)}", med_text) for med_text in med_texts):
            problems.append(f"dose_not_in_meds: {match.group(0)}")
    return problems


def _medicine_problems(text: str, meds: list[Lek]) -> list[str]:
    med_names = [normalize(med.lek) for med in meds]
    problems = []
    for sentence in sentences(normalize(text)):
        if NEGATED_IMPERATIVE.search(sentence):
            continue
        for match in DRUG_PATTERN.finditer(sentence):
            alias = match.group(1)
            generic = DRUGS[alias]
            if not any(alias in name or generic in name for name in med_names):
                problems.append(f"new_medicine: {match.group(0)}")
    return problems


def _language_problems(text: str, lang: str, meds: list[Lek]) -> list[str]:
    plain = _without_meds(text, meds).lower()
    foreign = (CS_MARKERS if lang == "sk" else SK_MARKERS).search(plain)
    return [f"wrong_language: {foreign.group(0)!r} in {lang} text"] if foreign else []


def validate_patient_text(text: str, level: int, lang: str, meds: list[Lek], contact: str | None) -> list[str]:
    if not text or not text.strip():
        return ["empty"]
    norm_text = normalize(text)
    problems: list[str] = []
    if level >= 2:
        problems += _contact_problems(norm_text, contact)
        if not TIME_WORDS.search(norm_text):
            problems.append("missing_time")
        reassurance = REASSURANCE.search(norm_text)
        if reassurance:
            problems.append(f"reassurance: {reassurance.group(0)}")
    if level == 4 and not CALL_TO_ACTION.match(norm_text):
        problems.append("level4_no_call_to_action")
    problems += [f"diagnosis_word: {match.group(0)}" for match in DIAGNOSIS.finditer(normalize(_without_meds(text, meds)))]
    problems += _dose_problems(text, meds)
    problems += _medicine_problems(text, meds)
    change = TREATMENT_CHANGE.search(norm_text)
    if change:
        problems.append(f"treatment_change: {change.group(0)}")
    problems += _language_problems(text, lang, meds)
    count = len(sentences(text))
    if count > MAX_SENTENCES:
        problems.append(f"too_many_sentences: {count}")
    if len(text) > MAX_CHARS:
        problems.append(f"too_long: {len(text)}")
    return problems
