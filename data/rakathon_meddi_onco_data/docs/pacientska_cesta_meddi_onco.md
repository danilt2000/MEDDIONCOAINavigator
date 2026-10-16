# MEDDI Onco – pacientská cesta a místo pro AI řešení

## Co je MEDDI Onco

Telemedicínská platforma pro podporu onkologických pacientů, sester a lékařů. Referenčním pracovištěm je Masarykův onkologický ústav, kde je MEDDI Onco v klinické praxi od roku 2020.

## Pacientská cesta dnes

1. **Příchod do onkologického centra** – pacient dostane diagnózu.
2. **Úvod do telemedicíny** – informační leták a nasměrování do Centra digitální medicíny.
3. **Onboarding** – personál představí aplikaci, pomůže s registrací a nasimuluje požadavek, testovací chat, videohovor a oznámení.
4. **Domácí fungování** – pacient vytváří požadavky kdykoli, vyplňuje dotazníky, posílá fotografie, čte vzdělávací materiály, dostává lékařské zprávy a výsledky.
5. **Monitorovací centrum** přijme požadavek, třídí ho podle priority a typu a buď ho vyřeší, nebo přidělí sestře či lékaři.
6. **Sestra / lékař** rozhodne, odpoví, přepošle zpět nebo přeřadí jinému specialistovi. Komunikace probíhá chatem, videem nebo telefonem; z aplikace lze vystavit eRecept.

Platforma už dnes podporuje sledování nežádoucích účinků (nevolnost, bolest, únava, kožní reakce aj.), fotodokumentaci, automatická upozornění pro sestry a lékaře, psychoonkologický screening a sledování paliativních pacientů (bolest, účinnost analgezie, duševní zdraví).

## Kam se napojuje AI řešení

```
Pacient (aplikace MEDDI Onco)
   │  check-in: dotazník + volný text + měření (tlakoměr, teploměr, váha…) + foto
   ▼
AI vrstva (řešení týmu)
   │  1. načte kontext: léčba, cyklus, léky, laboratoř, předchozí check-iny, události
   │  2. vyhodnotí úroveň 1–4 + zdůvodnění, případně se doptá
   │  3. odpoví pacientovi srozumitelným dalším krokem
   ▼
Monitorovací centrum MEDDI Onco
   │  úroveň 2–4 → požadavek s prioritou + souhrn pro lékaře
   ▼
Sestra / lékař → rozhodnutí, kontakt pacienta, záznam do udalosti_tymu
```

## Technická integrace

**Během Rakathonu nebude k dispozici API MEDDI Onco.** Týmy pracují s daty z tohoto balíčku. Bod zadání „integrace přes SDK či API“ prosím řešte návrhem, ne napojením:

- Postavte řešení nad datovým modelem z balíčku (pacient, léčba, léky, laboratoř, události týmu, check-iny s vyplněnými dotazníky). Je navržený tak, aby odpovídal tomu, co MEDDI Onco o pacientovi eviduje.
- Oddělte vrstvu, která data načítá a zapisuje (adaptér), od samotné logiky. V prototypu může adaptér číst soubory JSON; v ostrém provozu se nahradí voláním MEDDI.
- Popište, jaká volání by řešení potřebovalo, například: načtení kontextu pacienta, příjem nového vyplněného dotazníku (událost / webhook), vytvoření požadavku s prioritou do monitorovacího centra, odeslání zprávy pacientovi, uložení souhrnu pro lékaře.
- Výstupy (úroveň, zdůvodnění, souhrn) navrhněte jako strukturovaná data, která jde snadno zobrazit v MEDDI.

## Provoz

- **Monitorovací centrum:** pracovní dny 7:00–15:30.
- **Mimo pracovní dobu (15:30–7:00):** v akutních případech sloužící lékař MOÚ, tel. 724 590 848.
- **Akutní potíže kdykoli:** Rychlá záchranná služba 155. Aplikace podle vlastního upozornění není určena ke konzultaci neodkladných stavů.
- **Cílové doby odezvy:** viz `pravidla_triaze.md` (žlutá do konce následujícího pracovního dne, oranžová do 2 h v pracovní době).
- **Infrastruktura:** MEDDI běží na AWS se servery v Evropě. Ostré řešení musí jít provozovat v tomto prostředí (data zůstávají v EU, žádné ukládání u třetích stran). Pro prototyp nad syntetickými daty můžete použít libovolný jazykový model; v prezentaci uveďte, jak by se řešení provozovalo v AWS v EU.
