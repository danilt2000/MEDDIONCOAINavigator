# MEDDI Onco – rozšířená sada pro testování (100 pacientů)

Doplněk k hlavnímu datovému balíčku. Obsahuje **100 fiktivních pacientů**, kteří vznikli automatickými obměnami 14 pacientů z hlavní sady (ONC-001 až ONC-018). Každý ze 14 scénářů je tu 7× nebo 8×.

> Všechna data jsou smyšlená. Formát je stejný jako v hlavní sadě (popis polí najdete v jejím README).

## Co se v obměnách mění
- jméno, věk, kraj, výška a hmotnost,
- období sledování (posun o celé týdny, takže dny v týdnu a pracovní doba zůstávají stejné),
- naměřené hodnoty a výsledky laboratoře v běžném rozmezí (náhodný šum),
- texty zpráv v běžných dnech; asi u třetiny pacientů jsou zprávy psané bez diakritiky a hovorově,
- asi 12 % běžných dnů chybí (pacient nevyplnil).

## Co zůstává stejné
- diagnóza, léčba, léky a jejich dávkování,
- klíčové okamžiky (zhoršení, hospitalizace, zásahy týmu) a jejich načasování,
- správné vyhodnocení klíčových okamžiků – je převzaté z původního scénáře.

## K čemu sadu použít
- k testování na větším počtu pacientů: zbytečné poplachy, různé formulace zpráv, chybějící dny,
- ne jako náhradu hlavní sady: klinických situací je pořád 14 typů, jen ve více variantách.

Pole `vychazi_ze_scenare` u každého pacienta říká, ze kterého pacienta hlavní sady obměna vychází. Pole `nazev_scenare` popisuje scénář, jen pro orientaci.

Rozložení úrovní: 752× zelená, 262× žlutá, 92× oranžová, 43× červená (1 149 záznamů).
