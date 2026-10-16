"""Deterministic cs/sk red-flag lexicon (spec §8.7): diacritics-insensitive regexes over folded text, verbatim quotes."""
import re
from collections.abc import Callable

from app.context.builder import fold
from app.models import Fact

NUMBER_WORDS = {
    "jednou": 1, "raz": 1, "dvakrat": 2, "dvarazy": 2, "trikrat": 3, "ctyrikrat": 4, "stirikrat": 4, "petkrat": 5,
    "patkrat": 5, "sestkrat": 6, "sedmkrat": 7, "sedemkrat": 7, "osmkrat": 8, "osemkrat": 8, "devetkrat": 9,
    "desetkrat": 10, "desatkrat": 10,
    "dva": 2, "dve": 2, "tri": 3, "ctyri": 4, "styri": 4, "pet": 5, "pat": 5, "sest": 6, "sedm": 7, "osm": 8,
}
_NUMBER = r"(\d+|" + "|".join(NUMBER_WORDS) + r")"
_COUNT = re.compile(rf"\b{_NUMBER}\s*(?:x|×|-?\s?krat|kr\b)|\b(jednou|dvakrat|trikrat|ctyrikrat|stirikrat|petkrat|patkrat|sestkrat|sedmkrat|sedemkrat|osmkrat|osemkrat|devetkrat|desetkrat|desatkrat)\b")
_NEGATOR = re.compile(r"\b(bez|ani|ne|nie|nemam|nema|nemame|nemaji|nemal\w*|zadn\w*|ziadn\w*|neni|nebyl\w*|nebol\w*|nikdy|netrpi\w*|netrapi\w*)\s+(?:\w+\s+){0,2}$")
_NEGATOR_AFTER = re.compile(r"^\w*\s*(ne|nie|nemam|nema|nemame|neni|nebyl\w*|nebol\w*)\b")
_SENTENCE_END = re.compile(r"[;!?\n]|(?<!\d)\.|\.(?!\d)")
_PART_END = re.compile(r"(?<!\d),|,(?!\d)")
_SENTENCE = re.compile(r"[^.!?\n]+\?")


def _number(token: str) -> float | None:
    if token is None:
        return None
    token = token.strip()
    if token.isdigit():
        return float(token)
    return float(NUMBER_WORDS[token]) if token in NUMBER_WORDS else None


def _count(segment: str) -> float | None:
    match = _COUNT.search(segment)
    if not match:
        return None
    return _number(match.group(1) or match.group(2))


def _temperature(segment: str) -> float | None:
    for match in re.finditer(r"(?<![\d,./])(3[5-9]|4[0-2])(?:[,.](\d))?(?![\d/])\s*(kg|mmol|cm|let|rok|min|dn|den|hod|h\b|tyd|tablet|tbl|davk|kap|krat|x\b|×|%|ml|mg|kus|kc)?", segment):
        if match.group(3):
            continue
        if match.group(2):
            return float(f"{match.group(1)}.{match.group(2)}")
        if re.search(r"teplot|horeck|horuck|°|stup|namer|zimnic|tresu", segment) or re.search(r"\b(mam|ma|mame|mela|mel|mala|mal)\s+$", segment[:match.start()]):
            return float(match.group(1))
    return None


def _hours(segment: str) -> float | None:
    match = re.search(r"(\d+)\s*(h\b|hod)", segment)
    if match:
        return float(match.group(1))
    if re.search(r"od vcera|vcera vecer|vcerejs|od vecera|od rana|cely den|celou noc|od noci", segment):
        return 12.0
    return None


def _minutes(segment: str) -> float | None:
    match = re.search(r"(\d+)\s*min", segment)
    if match:
        return float(match.group(1))
    match = re.search(r"(\d+)\s*(h\b|hod)", segment)
    if match:
        return float(match.group(1)) * 60
    if re.search(r"pul hodin|pol hodin", segment):
        return 30.0
    return 60.0 if re.search(r"\bhodin(u|y)\b", segment) else None


def _nrs(segment: str) -> float | None:
    match = (re.search(r"(?:nrs|bolest\w*|boli\w*)\D{0,25}?\b(\d{1,2})\s*(?:/\s*10|z 10|ze 10)", segment) or re.search(r"nrs\s*(\d{1,2})", segment)
             or re.search(r"(?:bolest\w*|boli\w*)\s+(?:(?:je|ma|mam|porad|stale|furt|uz|zase|asi|na|tak|kolem|cca)\s+){0,3}(\d{1,2})\b(?![,.]\d)"
                          r"(?!\s*(?:x\b|×|krat|dn|den|h\b|hod|min|mg|ml|tbl|tablet|davk|°|stup|let|rok|tyd|kg|cm))", segment))
    return float(match.group(1)) if match and float(match.group(1)) <= 10 else None


def _blood_pressure(segment: str) -> tuple[float, float] | None:
    match = re.search(r"(?<![\d.,])(\d{2,3})\s*/\s*(\d{2,3})(?![\d.,])", segment)
    if not match or not re.search(r"tlak|\btk\b|mmhg", segment):
        return None
    systolic, diastolic = float(match.group(1)), float(match.group(2))
    return (systolic, diastolic) if 60 <= systolic <= 260 and 30 <= diastolic <= 160 and systolic > diastolic else None


def _bleeding_site(segment: str) -> str:
    sites = [("stolice", r"stolic|papir|prujem|hnack|konecnik|zachod|\bwc\b|zadek"), ("zvratky", r"zvrac|zvratk|vyzvrac"),
             ("moč", r"\bmoc|curan|mocen"), ("nos", r"\bnos"), ("dásně", r"dasn|dasen|zuby"), ("hlen", r"kasl|vykasl|hlen")]
    for site, pattern in sites:
        if re.search(pattern, segment):
            return site
    return "jiné"


def _weight(segment: str) -> float | None:
    match = re.search(r"(pribral|pribrala|zhubl|zhubla|ubral|ubrala|schudol|schudla)\w*\s*(?:jsem |sem |som |jsme )?(?:asi |skoro |cca |o |uz )?(\d+(?:[,.]\d)?)\s*kg", segment)
    if not match:
        return None
    value = float(match.group(2).replace(",", "."))
    return value if match.group(1).startswith("pribral") else -value


Rule = tuple[str, str, Callable[[str], object] | None, bool]
# (fact type, regex on the folded segment, value function, negatable)
RULES: list[Rule] = [
    ("chills", r"zimnic|tresavk|triask|tresu se|trese (me|mne|ma) zima|klepu se zimou|trasie ma|zimomriav|(\btres\w*|\btras\w*|\bklep\w*).*\bzim|\bzim\w*.*(\btres\w*|\btras\w*|\bklep\w*)", None, True),
    ("fever_reported", r"\bhorec\w*|\bhoruc\w*|\bmam teplotu|\bma teplotu|\bmam zvysenou teplotu|zvysen\w* teplot|teplotu mam|\bteplotim", None, True),
    ("blood_pressure", r"(tlak|\btk\b|mmhg)\D{0,30}\d{2,3}\s*/\s*\d{2,3}|\d{2,3}\s*/\s*\d{2,3}\D{0,10}(tlak|\btk\b|mmhg)", _blood_pressure, False),
    ("blood_in_stool", r"(\bkrev\b|\bkrv|krvav)(?=.*(stolic|papir|prujem|hnack|konecnik|zachod|\bwc\b))|(stolic|papir|prujem|hnack)\w*.*(\bkrev\b|\bkrv|krvav)", None, True),
    ("black_stool", r"cern\w* stolic|stolic\w* (je |byla |bola )?cern|dehtov|melen|cierna stolica", None, True),
    ("bleeding_site", r"\bkrev\b|\bkrv|krvac|krvav|vykasl\w* krev", _bleeding_site, True),
    ("nosebleed_minutes", r"(krvac|krvav|krev|krv)\w*.*\bnos|\bnos\w*.*(krvac|krev|krv)", _minutes, True),
    ("bleeding_uncontrolled", r"(krvac|krvav|krev|krv)\w*.*\b(nejde|neda|nelze|nemuz\w*|nemoz\w*|nevie\w*|nevim)\s+(\w+\s+){0,2}(za)?stavit|neprestava\w* krvac|krvac\w* (porad |stale )?neprestava", None, True),
    ("bruises_new", r"modrin|hematom|podlit|modrink", None, True),
    ("head_injury", r"(upadl|spadl|uhodil|uderil|narazil)\w*.*hlav|uraz hlavy|udrel\w* (sa )?do hlavy", None, True),
    ("cannot_keep_fluids", r"po vode|ani vodu|ani vod\w|neudrz\w*|vsechno (hned )?(vy)?zvrac|po vsem|nepolknu|nemuz\w* pit|nemoze pit|nepije|nedokaz\w* pit|ani tekutin|ani pit|vsetko vyvraca", None, False),
    ("low_fluid_intake", r"pul litru|0[,.]5 ?l\b|malo piju|malo pije|skoro nepiju|skoro nepije|vypil\w* (mozna |asi |jen )?(pul|0)", None, False),
    ("no_urine_hours", r"\bnemoc(i|il|ila|ilo|im|ime)\b|\bnecural\w*|\bnecikal\w*|\bnemocil\w*|anuri", _hours, False),
    ("oliguria", r"malo moc|moci malo|malo curam|malo cura|oligur|skoro nemoc", None, False),
    ("fainting", r"omdl|mdlob|\bodpadl|\bodpadol|zkolab|kolaps|ztratil\w* vedomi|stratil\w* vedomie|odpadla", None, True),
    ("dizziness_standing", r"toci se (mi )?hlava|mota se (mi )?hlava|toci sa (mi )?hlava|mota sa (mi )?hlava|zavrat|hlava se (mi )?toci|motam se|hlava (sa )?(mi )?toci|zatmi se (mi )?pred ocima", None, True),
    ("dyspnea_rest", r"(dych|dusn|dech)\w*.*(i v klidu|i kdyz sedim|i vsede|i vleze|i pri sezeni|aj v pokoji|v pokoji|aj ked sedim|aj v sede|aj v lahu|aj pri sedeni)|(i v klidu|i kdyz sedim|aj v pokoji|aj ked sedim).*(dych|dusn|dech)|dusnost (i |uz )?v klidu|v klidu .*dus|dusi (se|ma)\b|\bdusim\b|nemuz\w* (se )?nadechnout|nemuze dychat|nemuzu dychat|nemohu dychat|lapa\w* po dechu|nemozem dychat", None, True),
    ("dyspnea_exertion", r"tezko se (mi )?dycha|spatne se (mi )?dycha|tezko na dechu|tazko na dych|tazko sa (mi )?dycha|zadych|dusnost|dusna\b|dychavic|tezko se dycha|spatne se dycha|tazko sa dycha|nemam dech", None, True),
    ("orthopnea", r"polstar|vankus|vsede spi|spi vsede|spat vsede|v sede spat|spat v sede|vleze .*dych|nemuz\w* lezet|nemoze lezat", None, True),
    ("chest_pain_new", r"(\bpal|\bsvir|\btlak|\btlac|\bpich|\bbol|\bstah)\w*\s+(\w+\s+){0,3}(na|v|za|pri|u)\s+(prsou|prsech|hrud\w*|srdc\w*)\b|\b(hrud\w*|srdc\w*)\s+(\w+\s+){0,2}(\bpal|\bsvir|\btlac|\bpich|\bboli|\bbolest)|bol\w* (mne |me |mi |ma )?(na|v) prs(ou|ech|iach)|bol\w* (na|v|za) hrud|hrudn\w* bol|tlak na hrudi|pich\w* (na|v) hrud|svira\w* (na )?hrud|bolest na prsou|boli (ma |me |mi )?(na |v )?hrud", None, True),
    ("palpitations", r"busi (mi )?srdce|buseni srdce|busenie srdca|palpitac|srdce (mi )?(bije|busi|tluce|buch)|buchani srdce|busi mi srdce", None, True),
    ("confusion", r"zmaten|dezorient|nevi,? kde je|nevie,? kde je|nepozna (me|nas)|blouzn|mluvi (z cesty|nesmysl)|nesmysly|zmaten|nevi co se deje", None, True),
    ("drowsiness_new", r"\bspav(a|y|e|ost)\b|nereaguj|nejde (ji |ho )?probudit|neda se probudit|nemuz\w* (ji |ho )?probudit|tezko (se )?probou?z|somnol|nezvykle spi|ned(a|á) sa zobudit|\b(neda|nejde|nelze|nemuz\w*|nemoz\w*|nemohu|nemohl\w*|nevieme|nevim)\s+(\w+\s+){0,3}(pro|vz|z|zo|pre|pri)bud|(pro|vz|z|zo|pre)bud\w*\s+(\w+\s+){0,2}(nejde|neda|nelze)\b|bezvedom|neprobuditeln", None, True),
    ("breathing_slow", r"dycha pomalu|pomalu dycha|zpomalen\w* dych|dycha (velmi )?malo|malo dycha|dycha pomaly|dychani je pomale|dycha (jen )?obcas", None, True),
    ("fast_breathing", r"rychle dycha|zrychlen\w* dych|dycha rychle|rychly dech|zrychlene dychani", None, True),
    ("seizure", r"zachvat|epilep|krec\w* (cel|tel)|kŕc\w* cel|cukal\w* (se )?cel", None, True),
    ("limb_weakness_new", r"nohy (mu |ji |mi )?vypovid\w*|nemuz\w* (se )?postavit|nemoze (sa )?postavit|slabe nohy|ochabl\w* (ruk|noh)|nemuz\w* hybat|nehybe (rukou|nohou)|ochrn|slabost (v )?(prave|leve|ruky|nohy|ruce|noze)|necit\w* (ruku|nohu)|visi (mu |ji )?koutek|pokles\w* koutek", None, True),
    ("speech_problem", r"nemuz\w* (pro)?mluvit|mluvi nesrozumitel|zadrhava|porucha reci|huhla|nejde (mu |ji )?mluvit|nemoze hovorit|plete (si )?slova|nemuze najit slova", None, True),
    ("abdominal_pain_nrs", r"boli (mne |me |mi |ma |ji |ho )?(brich|bruch)|bolest\w* (brich|bruch)|(bricho|brucho|brisko) (ji |mi |ma |me )?(hrozne |strasne |dost |trochu )?boli|krec\w* v (brise|bruchu)|krc\w* v bruchu", _nrs, True),
    ("colicky_pain", r"\bkolik(a|y|ov)\w*|krec\w* v (brise|bruchu)|krc\w* v bruchu|krec\w* (v )?brich", None, True),
    ("no_stool_no_gas", r"(neodchaz\w*|nejdou|nechod\w*|zastav\w*) (ani )?plyn|plyny neodchaz\w*|ani plyny|zadne plyny|bez plynu|neprdi", None, False),
    ("constipation_days", rf"{_NUMBER}\s*(dn\w*|den)\s*(bez stolice|nebyl\w*|nic|bez vyprazdneni)|bez stolice\s*{_NUMBER}", lambda segment: _number((re.search(_NUMBER, segment) or [None, None])[1]) if re.search(_NUMBER, segment) else None, True),
    ("headache_severe", r"(silne|hrozne|strasne|velmi) (mne |me |mi |ma )?boli hlava|(silna|silne|hrozna|hrozne|strasna|strasne|nesnesiteln\w*|krut\w*|velka|velmi) (bolest )?(boli )?(mne |me |mi |ma )?hlav|hlava (mne |me |mi |ma )?(hrozne|strasne|silne|velmi) boli|nejhorsi bolest hlavy|bolest hlavy (je )?(silna|hrozna|nesnesitelna)", None, True),
    ("vision_problem", r"rozmazan|dvojit\w* vid|vidim dvoj|mzitk|nevidim|vypadek (zorneho )?pole|zhorsen\w* zrak|zle vidim|spatne vidim", None, True),
    ("thirst_polyuria", r"zizen|smad|caste moceni|casto (chodim )?(curat|mocit)|chodim (casto )?curat|porad (piju|pije)|casto mocim|polyur|polydips|stale piju", None, True),
    ("weight_change_kg", r"(pribral|zhubl|ubral|schudol|schudla)\w*\s*(jsem |sem |som |jsme )?(asi |skoro |cca |o |uz )?\d", _weight, True),
    ("edema", r"\botok|otekl|oteka|opuch|natekl|nateka", lambda segment: "i ráno" if re.search(r"rano|ryhy|ryha|stehn|cel(e|y|a) (noh|tel)|nezmiz", segment) else True, True),
    ("calf_swelling_one_side", r"lytk\w*.*(otok|otek|natek|boli|bolest)|(otok|otek|natek|bolest)\w*.*lytk|jednostrann\w* otok", None, True),
    ("pain_nrs", r"(nrs|bolest\w*|boli\w*)\D{0,25}?\b\d{1,2}|nrs\s*\d", _nrs, False),
    ("rescue_doses_per_day", rf"{_NUMBER}\s*(davk|davek)\w*", lambda segment: _number(re.search(rf"{_NUMBER}\s*(davk|davek)", segment).group(1)), False),
    ("liquids_only", r"jen tekut|pouze tekut|len tekut|jen kase|jen pyre|nutridrink|jen piti\b|iba tekut", None, True),
    ("weakness", r"\bslab(y|a|e|ost|ostí|ost')?\b|bez sil\b|nemam silu|nemam silu|nemá sílu", None, True),
    ("suicidal_thoughts", r"si (\w+ )?(vzit|vzal\w*|vzala) (\w+ )?zivot|(vzit|vzal\w*) si zivot|zabit (se|sa)|\b(se|sa)\s+(\w+\s+)?zabi(t|l|la|lo|ju|jem)\b|\bzabi(t|l|la|ju|jem)\s+(se|sa)\b|sebevrazd|samovrazd|neprobudit|nechci (uz )?zit|nechcem (uz )?zit|skoncit (to|se sebou|so sebou)|byt mrtv|radsi (bych )?(byla |byl )?mrtv|zomriet|nebyt tu\b|chci umrit|chcem umriet|umrit\b", None, True),
    ("suicide_plan_intent_means", r"mam plan|mam (to )?(uz )?(promyslen|premyslen|naplanovan|pripraven|nachystan)|(nasetril|nasetren|nasporil|nasporen|nazbiran)\w* (si )?(prasky|leky|lieky|tablet)|(prasky|leky|lieky|tablet)\w*.*\bto udelam\b|schoval\w* (si )?(prasky|leky|tablet)|vim,? jak to udelam|udelam to\b|chci to udelat|skoc\w* (z |pod )|obes\w* (se|sa)|predavkuj|predavkovat|mam doma (prasky|leky) na", None, True),
    ("lethal_dose_question", r"smrteln\w* (davk|mnozstv)|letaln|smrtiac\w* (davk|mnozstv)|(kolik|kolko)\w* .*\b(zabil|zabije|zabilo|zabit)\b|predavkovat (se|sa)\b", None, False),
    ("hopelessness", r"nema (to )?(cenu|smysl|zmysel)|k nicemu|beznadej|bez nadeje|vzdavam (to|se)|nic nema (smysl|cenu)|zbytecn\w* (se )?snazit|nema zmysel", None, False),
    ("missed_medication", r"(vynechal|vynechav|zapomel|zapomnel|zapomn\w*|prestal\w* (brat|uzivat)|nevzal|nebral\w*|vysadil|zabudol|zabudla)\w*(?=.*(tablet|lek|prask|davk|letrozol|kapecitabin|liek|tabletk))|(tablet|lek|prask|liek)\w*.*(vynechal|vynechav|zapomel|zapomn|nebral|nevzal|vysadil|zabudol|zabudla|neberu)", None, False),
    ("caregiver_strain", r"nevim,? jak to (mam )?zvladat|nezvladam|uz nemuzu|jsem (uplne |hrozne )?vycerpan|vycerpana|nespim|jsem na to sam|uz nevladzem|nevladzem|nevim si rady|nevim, co (s tim|mam delat)|uz to nedavam", None, False),
    ("port_redness", r"\bport\w*.*(zarud|cerven|bol|otok|otek|hnis|tepl)|(zarud|cerven|bol|otok|otek|hnis)\w*.*\bport", lambda segment: float(m.group(1)) if (m := re.search(r"(\d+)\s*cm", segment)) else True, True),
    ("nail_fold_inflammation", r"(nehet|nehtov|necht|paronych)\w*.*(zanic|zanet|zarud|otek|bol|hnis)|(zanic|zanet|zarud|otek|hnis)\w*.*(nehet|nehtov|necht)|paronych", None, True),
    ("skin_blisters", r"puchyr|pluzgier", None, True),
    ("tinnitus", r"pisk\w* (mi )?v us|piska (mi )?v us|hucen\w* v us|huci (mi )?v us|zvon\w* (mi )?v us|tinnit|sumi (mi )?v us|piskanie", None, True),
    ("neuropathy_function_loss", r"knofl|gombik|padaj\w* (mi )?(veci|z ruky|z ruk)|nemohu psat|nemuzu psat|neudrzim (v ruce|pero|hrnek|lzic)|nezapnu|tezko zapinam|nemuzu chodit kvuli brneni", None, True),
    ("neuropathy_persistent", r"(brn|mravenc|necitliv|tuhn)\w*.*(nemiz|pretrvav|uz ani mezi|porad|stale|nezmiz|nepresta)|(nemiz|pretrvav|nezmiz)\w*.*(brn|mravenc|necitliv)", None, True),
    ("cough_new", r"\bkasel|\bkaslu|\bkasle|\bkasla\b|\bkasl\b", None, True),
    ("pain_refractory", r"(bol|nrs).*((i|ani) po (prasku|leku|lecich|davce|davkach|tablet|oramorph|morfi|sos|zachran)|nepomah\w*|nezabir\w*|nepovol\w*)|((i|ani) po (prasku|leku|davce|davkach|tablet|oramorph|morfi)|nepovol\w*).*bol", None, False),
    ("vomiting", r"\b(vy)?zvrac|\bvrac(i|am|ia)|\bblink|\bblil|\bzvratk", None, True),
    ("anxiety", r"bojim (se|sa)|mam (velky )?strach|mam obavy|obavam (se|sa)|uzkost|panik|strach z\b", None, True),
    ("diarrhea", r"prujem|prujm|hnack|riedk\w* stolic|ridk\w* stolic|ridsi stolic|ridsi|redsi|rids", None, True),
    ("diarrhea_refractory", r"(i pres|navzdory|napriek|aj napriek) loperamid|loperamid\w* (moc |vubec |nic )?(nepomaha|nezabira|nepomohl|nezabral)", None, False),
    ("antiemetic_failure", r"(ondansetron|ondasetron|metoklopramid|antiemetik|prasky (na|proti) (zvraceni|nevolnost))\w* (moc |vubec |nic )?(nepomaha|nezabira|nepomohl|nezabral)", None, False),
    ("reduced_intake", r"jim jen suchar|skoro nejim|skoro neji\b|\bnejim\b|\bneji\b|moc toho nesnim|malo jim|nic nesnim|jen suchary|nechutna mi|skoro nic nesni", None, False),
]
_COMPILED = [(fact_type, re.compile(pattern), value_fn, negatable) for fact_type, pattern, value_fn, negatable in RULES]

_BLOOD = re.compile(r"\bkrev\b|\bkrv|krvav|krvac")
_STOOL_WORDS = re.compile(r"prujem|prujm|hnack|riedk|ridk|rids|redsi|stolic|na zachod|na wc")
_VOMIT_WORDS = re.compile(r"\b(vy)?zvrac|\bblink|\bblil|\bbleje|\bvrac|\bzvratk|\bvracal|\bgrcal|\bvomit")


def _spans(text: str, boundary: re.Pattern, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    end = len(text) if end is None else end
    spans, cursor = [], start
    for match in boundary.finditer(text, start, end):
        spans.append((cursor, match.start()))
        cursor = match.end()
    spans.append((cursor, end))
    return [(left, right) for left, right in spans if text[left:right].strip()]


def _negated(folded_segment: str, start: int, end: int) -> bool:
    return bool(_NEGATOR.search(folded_segment[:start]) or _NEGATOR_AFTER.search(folded_segment[end:]))


def lexicon_facts(text: str, source: str = "zprava", author: str = "pacient") -> tuple[list[Fact], list[str]]:
    """(facts, negated fact types) found in one free text."""
    folded = fold(text)
    facts: list[Fact] = []
    negations: list[str] = []
    for segment_start, segment_end in _spans(folded, _SENTENCE_END):
        segment = folded[segment_start:segment_end]
        quote = text[segment_start:segment_end].strip()

        def add(fact_type: str, value=True, certainty: str | None = None, period_h: float | None = None, quote_text: str = quote):
            facts.append(Fact(type=fact_type, value=value, certainty=certainty, period_h=period_h, quote=quote_text, source=source))

        sentence_stool = bool(_STOOL_WORDS.search(segment)) and not re.search(r"bez stolice|nebyl\w* na stolici", segment)
        sentence_vomit = bool(_VOMIT_WORDS.search(segment))
        for part_start, part_end in _spans(folded, _PART_END, segment_start, segment_end):
            part, part_quote = folded[part_start:part_end], text[part_start:part_end].strip()
            temperature = _temperature(part)
            if temperature is not None:
                add("temperature_c", temperature, "exact", quote_text=part_quote)
            count = _count(part)
            stool = bool(_STOOL_WORDS.search(part)) and not re.search(r"bez stolice|nebyl\w* na stolici", part)
            vomit = _VOMIT_WORDS.search(part)
            if stool and not count:
                count = (m := re.search(r"\b(\d+)\s*(riedk|ridk|stolic)", part)) and float(m.group(1))
            if not count:
                continue
            if not stool and not vomit:
                stool, vomit = sentence_stool and not sentence_vomit, sentence_vomit and not sentence_stool
            certainty = "approx" if re.search(r"asi|cca|mozna|kolem", part) else "exact"
            if stool:
                add("stool_count_above_normal", count, certainty, 24, quote if not _STOOL_WORDS.search(part) else part_quote)
            elif vomit and not (isinstance(vomit, re.Match) and _negated(part, vomit.start(), vomit.end())):
                add("vomiting_episodes_24h", count, certainty, 24, quote if not _VOMIT_WORDS.search(part) else part_quote)
        for fact_type, pattern, value_fn, negatable in _COMPILED:
            match = pattern.search(segment)
            if not match:
                continue
            if fact_type in ("edema", "calf_swelling_one_side") and re.search(r"nehet|nehtov|necht|palc|\bval\b|\bport", segment):
                continue
            if fact_type == "caregiver_strain" and author == "pacient":
                continue
            anchors = list(_BLOOD.finditer(segment)) if fact_type in ("blood_in_stool", "bleeding_site", "nosebleed_minutes") else list(pattern.finditer(segment))
            if negatable and all(_negated(segment, anchor.start(), anchor.end()) for anchor in anchors or [match]):
                if fact_type not in negations:
                    negations.append(fact_type)
                continue
            value = value_fn(segment) if value_fn else True
            if fact_type in ("nosebleed_minutes", "rescue_doses_per_day", "pain_nrs", "weight_change_kg", "blood_pressure") and value is None:
                continue
            if fact_type == "no_urine_hours":
                add(fact_type, value, "approx" if value else None)
            else:
                add(fact_type, value if value is not None else True)
    if re.search(r"plyny (uz |stale |porad )?odchaz|plyny odchadzaj", folded):
        negations.append("no_stool_no_gas")
    if re.search(r"\bnezvrac", folded):
        negations.append("vomiting_episodes_24h")
    return facts, negations


def questions(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE.finditer(text)]
