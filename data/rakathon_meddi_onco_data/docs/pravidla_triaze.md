# Pravidla triáže

Podle těchto pravidel je anotováno referenční vyhodnocení (ground truth). Vycházejí ze semaforové triáže onkologických pacientů (UKONS 24h Triage Tool), gradace nežádoucích účinků CTCAE v5 a pacientem hlášených výstupů PRO-CTCAE.

Tvrdá pravidla (část 3) určují **nejnižší přípustnou úroveň**: řešení smí situaci vyhodnotit výš, nikdy ne níž. Ground truth ve vývojové ani ve skryté testovací sadě žádné tvrdé pravidlo neporušuje. Části 4–6 popisují typické situace a kontext, kde rozhoduje klinický úsudek.

---

## 1. Úrovně a doporučený krok

| Úroveň | Krok pro pacienta (`doporuceny_krok`) | Upozornit tým | Typicky |
|---|---|---|---|
| 1 ZELENÁ | `dalsi_sledovani` – režimová doporučení, kdy se ozvat dřív | ne | Očekávané mírné obtíže (1. stupeň), stabilní stav |
| 2 ŽLUTÁ | `kontaktovat_tym` – tým se ozve | ano | 2. stupeň bez varovných příznaků, nepříznivý trend, neadherence, psychická zátěž, výpadek dat |
| 3 ORANŽOVÁ | `telekonzultace` – lékař ještě dnes | ano, s vysokou prioritou | 3. stupeň, 2. stupeň u rizikové léčby, hrozící dehydratace, podezření na závažnou toxicitu bez bezprostředního ohrožení |
| 4 ČERVENÁ | `neodkladna_pomoc` – ihned 155 / urgentní příjem | ano, okamžitě | Život ohrožující stav |

## 2. Pracovní doba a komu pacienta poslat (`doporuceny_kontakt`)

Monitorovací centrum pracuje **v pracovní dny 7:00–15:30**. Mimo tuto dobu je v akutních případech k dispozici **sloužící lékař MOÚ (724 590 848)** a kdykoli **155**.

| Úroveň | V pracovní době | Mimo pracovní dobu a o víkendu |
|---|---|---|
| 1 | Tým vidí záznam v přehledu | Totéž |
| 2 | Monitorovací centrum, vyřízení do konce následujícího pracovního dne | Monitorovací centrum následující pracovní den; pacient dostane instrukce, kdy volat dřív |
| 3 | Telekonzultace s lékařem MOÚ, kontakt do 2 hodin | Sloužící lékař MOÚ ihned |
| 4 | 155 / urgentní příjem; tým upozorněn do 15 minut | 155 / urgentní příjem, případně sloužící lékař MOÚ |

## 3. Tvrdá pravidla (vždy platí)

### Červená – úroveň 4
| Oblast | Pravidlo |
|---|---|
| Horečka | Teplota ≥ 38,0 °C nebo zimnice během chemoterapie nebo do 6 týdnů po ní |
| Dýchání | Dušnost v klidu, SpO2 < 90 %, náhle vzniklá dušnost s bolestí na hrudi nebo bušením srdce |
| Hrudník | Nově vzniklá bolest na hrudi |
| Neurologie | Zmatenost, porucha vědomí nebo probuditelnosti, epileptický záchvat, nová slabost končetin, porucha řeči |
| Krvácení | Krev ve stolici nebo zvratcích, černá stolice, krev v moči, krvácení z nosu > 20 minut, úraz hlavy na antikoagulaci |
| Průjem | ≥ 7 stolic nad normál za 24 h, nebo průjem s krví |
| Zvracení | > 5 epizod za 24 h, nebo neudrží tekutiny se známkami dehydratace |
| Dehydratace / oběh | Nemočí > 10 h, mdloba, systolický TK < 90 mmHg |
| Břicho | Zástava odchodu plynů a stolice se zvracením nebo kolikovitou bolestí |
| Tlak | TK ≥ 180/110, nebo vysoký tlak se silnou bolestí hlavy, poruchou zraku, řeči či bolestí na hrudi |
| Metabolismus | Zvracení + bolest břicha + zrychlené dýchání u diabetika nebo pacienta na imunoterapii (podezření na ketoacidózu) |
| Opioidy | Nově vzniklá nápadná spavost, nereagování nebo zpomalené dýchání |
| Psychika | Myšlenky na sebevraždu s plánem, úmyslem nebo prostředky |

### Oranžová – nejméně úroveň 3
| Oblast | Pravidlo |
|---|---|
| Celkový stav | Odpověď „5 = velmi špatně“ u „Jak se celkově cítíte?“ |
| Dýchání | SpO2 < 92 % nebo pokles o ≥ 3 body proti obvyklé hodnotě pacienta; nová ortopnoe (spí vsedě / na více polštářích) |
| Průjem | 4–6 stolic nad normál při imunoterapii, fluoropyrimidinech (5-FU, kapecitabin) nebo irinotekanu; jakýkoli průjem, který nereaguje na loperamid podle schématu |
| Průjem na imunoterapii | Jakýkoli průjem s bolestí břicha |
| Příjem a tekutiny | Neudrží tekutiny; nově zvládá jen tekutou stravu a bolest není kontrolovaná; málo močí nebo se mu točí hlava při vstávání při sníženém příjmu |
| Zvracení | 3–5 epizod za 24 h a zároveň neudrží tekutiny |
| Tlak | TK ≥ 160/100 při antiangiogenní léčbě (sunitinib, bevacizumab a podobně) |
| Krvácení | Jakékoli krvácení nebo nové modřiny na antikoagulaci |
| Žíly | Jednostranný otok a bolest lýtka (možná trombóza) – vždy s poučením o příznacích plicní embolie |
| Bolest | NRS ≥ 7, která nepovolí po záchranné (SOS) dávce |
| Mozkový nádor | Ranní bolest hlavy se zvracením |
| Imunoterapie | Velká žízeň, časté močení a hubnutí |
| Glykémie | Pod 4 mmol/l u pacienta na inzulinu |
| Psychika | Odpověď „Ano“ na „napadá mě, že bych si nejraději vzal/a život“; výroky beznaděje („nemá to cenu“) |
| Opakovaná eskalace | Stav se zhoršuje, přestože už je naplánované vyšetření – nečekat na termín |

## 4. Typické žluté situace (úroveň 2)

- Příznak 2. stupně bez varovných příznaků (nevolnost se sníženým příjmem jídla, zácpa ≥ 3 dny, afty omezující jídlo, paronychie, syndrom ruka-noha omezující činnosti).
- Průjem do 3 stolic nad normál **na imunoterapii** (u ostatní léčby je to úroveň 1).
- 3–5 epizod zvracení, pokud pacient pije.
- Opakovaně TK ≥ 140/90 (nejméně 3 měření), nebo hypotenze se závratí po vstávání.
- Glykémie > 15 mmol/l se žízní a častým močením – tým kontaktovat ještě týž den.
- Přetrvávající neuropatie mezi cykly nebo neuropatie omezující jemnou motoriku – předat lékaři **před další aplikací**.
- Nový tinnitus na cisplatině – předat před další dávkou.
- Otoky 2. stupně nebo přírůstek hmotnosti > 2 kg za 3 dny u kardiotoxické léčby (antracykliny, trastuzumab).
- Úbytek hmotnosti ≥ 5 % za měsíc, pokles soběstačnosti o dva stupně, postupný pokles příjmu.
- Bolest NRS 4–6, nebo potřeba ≥ 3 záchranných dávek analgetik denně.
- Smutek nebo úzkost středního stupně, vyčerpání pečující osoby, vynechávání léků.
- 3 nevyplněné check-iny za sebou (u stabilního pacienta). Po 1–2 vynechaných stačí připomenutí.

## 5. Kontext, který mění úroveň

| Kontext | Dopad |
|---|---|
| Den 7–14 po myelosupresivní chemoterapii (nadir) | Horečku nepodceňovat, pacienta poučit o měření teploty |
| Imunoterapie (anti-PD-1/PD-L1, anti-CTLA-4) | Imunitní toxicita může nastoupit kdykoli a rychle progredovat. Nový průjem, kašel, dušnost, žízeň nebo únava se vždy hlásí týmu |
| Fluoropyrimidiny, irinotekan | Průjem 2. stupně řeší lékař týž den. U irinotekanu se loperamid užívá, dokud pacient není 12 h bez průjmu – do té doby nejméně žlutá |
| Antikoagulace + interagující léky (např. kapecitabin a warfarin) | Krvácení posuzovat přísněji |
| Antiangiogenní léčba | Hypertenze, krvácení, riziko perforace |
| Pauza v cyklické léčbě (např. sunitinib 4/2) | Tlak klesá, léky na tlak nastavené na léčbu mohou způsobit hypotenzi |
| Chronická onemocnění (CHOPN, diabetes, srdeční selhání, onemocnění ledvin) | Hodnotit změnu proti obvyklému stavu pacienta, ne absolutní hodnotu (dušnost u CHOPN, saturace, glykémie) |
| Vysoký věk, život o samotě, nízká digitální gramotnost | Nižší práh pro eskalaci a ověření telefonem |
| Paliativní péče a dříve vyslovená přání | Přání je informace pro tým. Nikdy není důvodem nedoporučit pomoc – doporučit 24h linku paliativního týmu / hospice, při nedostupnosti 155 |

## 6. Obecná pravidla

1. **Trend.** Několik zhoršujících se záznamů za sebou může znamenat vyšší úroveň, i když jednotlivě vypadají nevinně (hmotnost, otoky, saturace, příjem, soběstačnost).
2. **Zpráva pacienta má přednost před dotazníkem.** Když si odporují, systém se doptá a do té doby počítá s horší variantou.
3. **Stav, který tým už řeší.** Po zásahu týmu (telekonzultace, hospitalizace) se zlepšující se stav hodnotí podle aktuálních údajů. Nový nebo zhoršený příznak se hodnotí znovu od začátku.
4. **Doplňující otázky.** Při nejasnosti se systém doptá. Do odpovědi platí vyšší z možných úrovní.
5. **Bez diagnózy a změny léčby.** Pacientovi systém neříká diagnózu a nemění léky ani dávky. Smí připomenout postup, který má pacient předem od lékaře (např. schéma loperamidu, „Paralen neužívat, dokud vás nevyšetří lékař“).
6. **Vysvětlitelnost.** Každé vyhodnocení uvádí klíčové nálezy a varovné příznaky, ze kterých vychází.
7. **Pečující.** Když vyplňuje blízká osoba, oslovovat ji a hodnotit i její zátěž.
