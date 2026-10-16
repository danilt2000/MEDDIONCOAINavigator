# MEDDI Onco – data pro Rakathon

Datový balíček k zadání MEDDI Onco. Obsahuje **14 fiktivních onkologických pacientů** s kompletním kontextem léčby a s časovou osou domácího sledování. Pacienti vyplňují **stejné dotazníky, jaké dnes používá MEDDI Onco**, posílají zprávy a měří si teplotu, tlak, saturaci nebo váhu. Ke každému záznamu je **referenční vyhodnocení (ground truth)**: úroveň závažnosti, doporučený další krok a zdůvodnění.

> **Všechna data jsou smyšlená.** Žádný záznam nepochází od skutečného pacienta.

---

## 1. Obsah balíčku

```
README.md                           ← tento soubor
docs/
  pravidla_triaze.md                ← úrovně závažnosti, pracovní doba, pravidla eskalace
  dotazniky_definice.json           ← přesné znění dotazníků MEDDI Onco (otázky, odpovědi, barvy, upozornění)
  vzorove_souhrny_pro_lekare.md     ← jak má vypadat souhrn pro lékaře
  pacientska_cesta_meddi_onco.md    ← jak MEDDI Onco funguje a kam se řešení napojuje
pacienti/ONC-xxx.json               ← vstup: jeden pacient = jeden soubor
ground_truth/ONC-xxx.json           ← reference: vyhodnocení každého záznamu pacienta
```

Vše je ve formátu JSON (UTF-8). Porota má navíc **skrytou testovací sadu** 6 dalších pacientů se stejnou strukturou, na které se finální řešení otestují. Laďte řešení na principy, ne na tato konkrétní data.

---

## 2. Jak balíček pokrývá zadání

| Zadání: řešení… | Co k tomu v balíčku najdete |
|---|---|
| pravidelně a srozumitelně zjišťuje stav pacienta, symptomy, jejich intenzitu a vývoj | Dotazníky, které MEDDI Onco dnes používá (`docs/dotazniky_definice.json`), a 3–6 týdnů vyplněných záznamů u každého pacienta. Můžete z nich vyjít, nebo navrhnout vlastní způsob dotazování (např. konverzační) |
| pracuje s kontextem léčby, léky a zdravotními údaji | U každého pacienta diagnóza, režim a cykly léčby, všechny léky, komorbidity, laboratoř, vyšetření a záznamy týmu |
| je integrováno do MEDDI Onco přes SDK či API | Během Rakathonu API k dispozici není. Integraci navrhněte nad datovým modelem z balíčku – viz `docs/pacientska_cesta_meddi_onco.md` |
| rozpozná rizikové změny a rozdělí situace do úrovní závažnosti | 4 úrovně a pravidla v `docs/pravidla_triaze.md`; ke každému záznamu pole `uroven`, `klicove_nalezy` a `varovne_priznaky` |
| doporučí pacientovi jasný další krok | Pole `doporuceny_krok` (další sledování / kontaktovat tým / telekonzultace / neodkladná pomoc), `doporuceny_kontakt` a vzorová odpověď `doporuceni_pro_pacienta` |
| při rizikovém vývoji upozorní zdravotnický tým | Pole `upozornit_tym`; pracovní doba monitorovacího centra v `docs/pravidla_triaze.md` |
| vytvoří pro lékaře stručný souhrn vývoje | `docs/vzorove_souhrny_pro_lekare.md` – čtyři vzorové souhrny a zásady |
| nestanoví diagnózu, nemění léčbu, počítá s dohledem, vysvětlitelností a bezpečnou eskalací | Část 6 tohoto README a `docs/pravidla_triaze.md` |

---

## 3. Pacienti

| ID | Pacient | Diagnóza a léčba | Co scénář testuje |
|---|---|---|---|
| ONC-001 | Ž 48 | Karcinom prsu, AC chemoterapie | Horečka v období poklesu bílých krvinek (červená) |
| ONC-002 | M 63 | Karcinom sigmatu, FOLFOX | Průjem u diabetika na metforminu; narůstající neuropatie před aplikací |
| ONC-004 | Ž 41 | Melanom, ipilimumab + nivolumab | Rychlé zhoršení imunitní kolitidy během 2 dnů |
| ONC-005 | M 72 | Karcinom prostaty, hormonální léčba | Stabilní pacient, falešné poplachy, pozvolný vzestup tlaku |
| ONC-007 | Ž 55 | Karcinom prsu HER2+, trastuzumab | Plíživé známky srdečního selhání (váha, otoky, dušnost vleže) |
| ONC-008 | M 58 | Lymfom, R-CHOP | Vysoký cukr po kortikoidech, zácpa, infekce portu |
| ONC-009 | M 61 | Karcinom ledviny, sunitinib | Vysoký tlak, kožní toxicita, nízký tlak v pauze léčby |
| ONC-010 | Ž 64 | Malobuněčný karcinom plic, chemo + imunoterapie | Nekontrolované zvracení → dehydratace; píše dcera |
| ONC-011 | M 52 | Karcinom orofaryngu, chemoradioterapie | Afty a bolest při polykání, hubnutí, dehydratace; dotazník bolesti |
| ONC-013 | M 70 | Karcinom rekta, kapecitabin + warfarin | Průjem, léková interakce, krvácení |
| ONC-014 | Ž 76 | Karcinom žaludku, paliativní péče | Vyplňuje dcera; bolest a SOS dávky, spavost na opioidech, dříve vyslovená přání, vyčerpání pečující; ESAS |
| ONC-016 | Ž 50 | Karcinom prsu, letrozol | Bolest kloubů, vynechávání léků, deprese, myšlenky na smrt |
| ONC-017 | M 57 | Karcinom plic EGFR+, osimertinib | Nízkorizikový pacient, který přestane odpovídat |
| ONC-018 | M 69 | Karcinom tlustého střeva, FOLFIRI + bevacizumab | **Slovenština**, zpráva odporuje dotazníku, nízká digitální gramotnost |

Rozložení úrovní: 115× zelená, 37× žlutá, 13× oranžová, 6× červená (171 záznamů). Odpovídá realitě – většina záznamů je běžná, rizikových je málo.

---

## 4. Jak data používat

**Přehrávejte chronologicky.** V okamžiku každého záznamu smí řešení vidět jen to, co bylo známo do té chvíle: dřívější záznamy, laboratoř a události týmu s dřívějším datem a časem. Budoucí hospitalizaci nebo výsledek vyšetření v tu chvíli znát nemůže.

**Vstup:** `pacienti/ONC-xxx.json`.
**Výstup na každý záznam:** úroveň 1–4, doporučený krok a kontakt, zda upozornit tým, srozumitelná odpověď pacientovi a zdůvodnění pro lékaře. Podle potřeby souhrn pro lékaře.
**Reference:** `ground_truth/ONC-xxx.json` – záznamy se spárují přes `checkin_id`.

**Jak bude porota hodnotit** (na skryté sadě):
- zachycení všech červených a oranžových situací – podhodnocení červené je nejzávažnější chyba,
- počet zbytečných eskalací,
- správné nasměrování podle pracovní doby,
- srozumitelnost pro pacienta a vysvětlitelnost pro lékaře,
- kvalita souhrnu pro lékaře.

### Dotazníky
Barvy a upozornění u odpovědí jsou převzaté z aplikace MEDDI Onco a hodnotí **každou odpověď samostatně**. Nevidí léčbu, trend, měření ani zprávu pacienta. Stejná teplota nebo stejný průjem proto může podle kontextu znamenat jinou úroveň než barva odpovědi. Barvy berte jako jeden ze vstupů, ne jako výsledek.

| Dotazník | Kdy ho pacienti vyplňují |
|---|---|
| Nežádoucí účinky onkologické léčby | Při každém záznamu |
| Psychoonkologický screening MOÚ | Na začátku, zhruba po 14 dnech a při zhoršení psychiky |
| Bolest po nastavení analgetické terapie | Pacienti, kterým se nastavuje léčba bolesti (ONC-011, ONC-014) |
| ESAS | 1× týdně u paliativních pacientů (ONC-014) |

Směr škál: „Jak se celkově cítíte?“ 1 = nejlépe, 5 = velmi špatně. ESAS, bolest a psychoonkologický screening: nízké číslo = nejméně potíží; výjimkou je „Zvládání situace“, kde vysoké číslo = zvládám dobře.

---

## 5. Datový slovník

### Pacient (`pacienti/ONC-xxx.json`)

| Pole | Popis |
|---|---|
| `patient_id` | ID pacienta |
| `nazev_scenare` | Krátký popis scénáře (jen pro orientaci, reálný systém ho nemá) |
| `obdobi_sledovani` | Datum od–do |
| `demografie` | Věk, pohlaví, jazyk (`cs`/`sk`), kraj, domácnost, digitální gramotnost, kdo vyplňuje |
| `diagnoza` | Diagnóza, kód MKN-10, stadium, biomarkery, datum diagnózy |
| `ecog_vychozi` | Výkonnostní stav ECOG na začátku sledování (0 = plně aktivní, 4 = upoutaný na lůžko) |
| `komorbidity`, `alergie` | Seznamy |
| `predem_vyslovena_prani` | Dříve vyslovené přání (jen u některých pacientů) |
| `antropometrie` | Výška, výchozí hmotnost, BMI |
| `lecba` | Záměr, režim, léčiva a dávky, délka cyklu, data 1. dne jednotlivých cyklů |
| `leky` | Všechny léky: dávka, frekvence, indikace, `typ` (onkologicky / podpurny / chronicky / rezim), od–do, `pri_potizich` (užívá se jen při potížích) |
| `laboratore` | Výsledky odběrů s referenčními mezemi a příznakem `L` (nízká) / `H` (vysoká) |
| `vysetreni` | Další vyšetření (ECHO, CT, MR, hemokultury) |
| `udalosti_tymu` | Co udělal zdravotnický tým: telekonzultace, změna léčby, hospitalizace, propuštění |
| `checkiny` | Záznamy domácího sledování (viz níže) |

### Záznam (`checkiny`)

| Pole | Popis |
|---|---|
| `checkin_id` | ID záznamu |
| `datum`, `cas`, `den_sledovani` | Kdy pacient záznam odeslal (den 1 = začátek sledování) |
| `cyklus`, `den_cyklu` | Cyklus léčby a den v cyklu (den 1 = aplikace); `null` u kontinuální léčby |
| `stav` | `vyplneno` / `nevyplneno` (pacient neodpověděl) |
| `vyplnil` | Pacient, nebo blízká osoba |
| `dotazniky` | Vyplněné dotazníky: otázka, odpověď, barva odpovědi a upozornění, které se pacientovi zobrazilo |
| `vitalni_funkce` | Naměřené hodnoty a jejich zdroj (teploměr, tlakoměr, oxymetr, váha, glukometr) |
| `zprava_pacienta` | Zpráva, kterou pacient poslal s dotazníkem. Může mít překlepy, být bez diakritiky, slovensky – a může dotazníku odporovat |
| `prilohy` | Popis fotografie, kterou pacient přiložil |

### Ground truth (`ground_truth/ONC-xxx.json`)

| Pole | Popis |
|---|---|
| `checkin_id`, `patient_id` | Ke kterému záznamu vyhodnocení patří |
| `uroven` | 1 zelená, 2 žlutá, 3 oranžová, 4 červená |
| `doporuceny_krok` | `dalsi_sledovani` / `kontaktovat_tym` / `telekonzultace` / `neodkladna_pomoc` |
| `upozornit_tym` | Zda upozornit zdravotnický tým |
| `doporuceny_kontakt` | Na koho pacienta nasměrovat podle úrovně a času (monitorovací centrum / sloužící lékař MOÚ / 155) |
| `klicove_nalezy` | Co je v záznamu podstatné |
| `varovne_priznaky` | Varovné příznaky, které vedly k eskalaci |
| `zduvodneni` | Klinické zdůvodnění pro lékaře |
| `doporuceni_pro_pacienta` | Vzorová odpověď pacientovi |

---

## 6. Povinná pravidla řešení

1. **Nestanovuje diagnózu a nemění léčbu.** Ve zdůvodnění pro lékaře smí napsat „podezření na…“, pacientovi ale nesděluje diagnózu a nemění léky ani dávky. Smí připomenout postup, který má pacient předem od lékaře (např. schéma léku na průjem).
2. **Při pochybnosti eskaluje.** Nejistota se řeší vyšší úrovní nebo doplňující otázkou, nikdy nižší úrovní.
3. **Nepodhodnotí tvrdá pravidla** z `docs/pravidla_triaze.md` (část 3).
4. **Pracuje s kontextem a trendem**, ne jen s jednou odpovědí.
5. **Zpráva pacienta má přednost před dotazníkem.** Když si odporují, doptá se a do té doby počítá s horší variantou.
6. **Je vysvětlitelné.** Každé vyhodnocení uvádí, z čeho vychází, aby ho lékař ověřil za pár sekund.
7. **Lidský dohled.** Úrovně 2–4 vždy končí u zdravotníka. Systém pacienta nikdy jen „neuklidní“ místo předání.
8. **Respektuje pracovní dobu.** Monitorovací centrum funguje v pracovní dny 7:00–15:30. Mimo ni pacienta s oranžovou úrovní nasměruje na sloužícího lékaře MOÚ (724 590 848), s červenou na 155.
9. **Ochrana údajů.** MEDDI běží na AWS se servery v Evropě. Ostré řešení musí jít provozovat tam. Pro prototyp nad těmito smyšlenými daty můžete použít jakýkoli jazykový model; v prezentaci ukažte, jak by řešení běželo v AWS v EU, a do modelu posílejte jen nezbytné údaje.
