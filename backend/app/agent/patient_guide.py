PATIENT_TEXTS: dict[str, dict[str, str]] = {
    "kdy_volat": {
        "cs": "Volejte ihned 155 (mimo pracovní dobu případně sloužícího lékaře 724 590 848), pokud máte: teplotu 38 °C a víc "
        "nebo zimnici během chemoterapie či do 6 týdnů po ní, dušnost v klidu, novou bolest na hrudi, zmatenost, záchvat, "
        "novou slabost rukou nebo nohou, krev ve stolici, zvratcích nebo moči, černou stolici, 7 a více stolic denně navíc, "
        "zvracení víc než 5× za den, neudržíte tekutiny, nemočíte déle než 10 hodin nebo omdlíte. Nečekejte do rána.",
        "sk": "Volajte ihneď 155 (mimo pracovného času prípadne službukonajúceho lekára 724 590 848), ak máte: teplotu 38 °C "
        "a viac alebo zimnicu počas chemoterapie či do 6 týždňov po nej, dýchavičnosť v pokoji, novú bolesť na hrudi, zmätenosť, "
        "záchvat, novú slabosť rúk alebo nôh, krv v stolici, zvratkoch alebo moči, čiernu stolicu, 7 a viac stolíc denne navyše, "
        "zvracanie viac ako 5× za deň, neudržíte tekutiny, nemočíte dlhšie ako 10 hodín alebo odpadnete. Nečakajte do rána.",
    },
    "kontakty": {
        "cs": "Monitorovací centrum pracuje v pracovní dny od 7:00 do 15:30. Mimo tuto dobu volejte v akutních případech "
        "sloužícího lékaře na čísle 724 590 848. Při ohrožení života volejte kdykoli 155. Chat ani dotazník neslouží "
        "k přivolání pomoci v neodkladných situacích.",
        "sk": "Monitorovacie centrum pracuje v pracovné dni od 7:00 do 15:30. Mimo tohto času volajte v akútnych prípadoch "
        "službukonajúceho lekára na čísle 724 590 848. Pri ohrození života volajte kedykoľvek 155. Chat ani dotazník "
        "neslúžia na privolanie pomoci v neodkladných situáciách.",
    },
    "horecka": {
        "cs": "Horečka během chemoterapie může znamenat, že tělo má málo bílých krvinek, které ho chrání, a potřebuje okamžité "
        "vyšetření. Při teplotě 38 °C a víc nebo při zimnici nečekejte do rána a volejte ihned. Paralen neužívejte, dokud vás "
        "nevyšetří lékař, protože by horečku jen zakryl.",
        "sk": "Horúčka počas chemoterapie môže znamenať, že telo má málo bielych krviniek, ktoré ho chránia, a potrebuje okamžité "
        "vyšetrenie. Pri teplote 38 °C a viac alebo pri zimnici nečakajte do rána a volajte ihneď. Paralen neužívajte, kým vás "
        "nevyšetrí lekár, pretože by horúčku iba zakryl.",
    },
    "mereni_teploty": {
        "cs": "Mezi 7. a 14. dnem po chemoterapii je obranyschopnost těla nejslabší. V tu dobu si měřte teplotu ráno i večer "
        "a pokaždé, když je vám zima, třesete se nebo se necítíte dobře.",
        "sk": "Medzi 7. a 14. dňom po chemoterapii je obranyschopnosť tela najslabšia. Vtedy si merajte teplotu ráno aj večer "
        "a zakaždým, keď je vám zima, trasiete sa alebo sa necítite dobre.",
    },
    "prujem": {
        "cs": "Při průjmu pijte často po malých doušcích, třeba vodu, čaj nebo neperlivou minerálku. Pokud máte od lékaře schéma "
        "léku na průjem, užívejte ho přesně podle něj. Ozvěte se týmu, když máte 4 a více stolic denně navíc, průjem s bolestí "
        "břicha nebo průjem nepovoluje. Při krvi ve stolici, 7 a více stolicích navíc, závratích nebo když málo močíte, "
        "volejte ihned 155.",
        "sk": "Pri hnačke pite často po malých dúškoch, napríklad vodu, čaj alebo neperlivú minerálku. Ak máte od lekára schému "
        "lieku na hnačku, užívajte ho presne podľa nej. Ozvite sa tímu, keď máte 4 a viac stolíc denne navyše, hnačku s bolesťou "
        "brucha alebo hnačka neustupuje. Pri krvi v stolici, 7 a viac stoliciach navyše, závratoch alebo keď málo močíte, "
        "volajte ihneď 155.",
    },
    "zvraceni": {
        "cs": "Při nevolnosti a zvracení pijte po lžičkách nebo malých doušcích a jezte málo a často. Léky proti nevolnosti užívejte "
        "tak, jak je máte předepsané. Když zvracíte 3–5× za den, dejte vědět týmu. Když zvracíte víc než 5× za den nebo "
        "neudržíte žádné tekutiny, volejte ihned.",
        "sk": "Pri nevoľnosti a zvracaní pite po lyžičkách alebo malých dúškoch a jedzte málo a často. Lieky proti nevoľnosti "
        "užívajte tak, ako ich máte predpísané. Keď zvraciate 3–5× za deň, dajte vedieť tímu. Keď zvraciate viac ako 5× za deň "
        "alebo neudržíte žiadne tekutiny, volajte ihneď.",
    },
    "afty": {
        "cs": "Při aftech si po jídle vyplachujte ústa, používejte měkký kartáček a jezte měkká jídla bez kyselého a ostrého. "
        "Pokud vám afty brání v jídle nebo pití, ozvěte se týmu. Když nezvládnete pít, volejte ještě dnes.",
        "sk": "Pri aftách si po jedle vyplachujte ústa, používajte mäkkú kefku a jedzte mäkké jedlá bez kyslého a štipľavého. "
        "Ak vám afty bránia v jedle alebo pití, ozvite sa tímu. Keď nezvládnete piť, volajte ešte dnes.",
    },
    "bolest": {
        "cs": "Léky na bolest užívejte přesně podle rozpisu od lékaře, včetně dávek při bolesti. Dávky ani jejich počet sami neměňte. "
        "Když potřebujete záchrannou dávku 3× a víc za den nebo bolest nepovolí ani po ní, ozvěte se týmu; v paliativní péči "
        "volejte 24h linku paliativního týmu nebo hospice, a když se nedovoláte, 155.",
        "sk": "Lieky na bolesť užívajte presne podľa rozpisu od lekára, vrátane dávok pri bolesti. Dávky ani ich počet sami nemeňte. "
        "Keď potrebujete záchrannú dávku 3× a viac za deň alebo bolesť nepovolí ani po nej, ozvite sa tímu; v paliatívnej "
        "starostlivosti volajte 24h linku paliatívneho tímu alebo hospicu, a keď sa nedovoláte, 155.",
    },
    "spavost_opioidy": {
        "cs": "Pokud je váš blízký po lécích na bolest nápadně spavý, nejde ho probudit, nereaguje nebo dýchá pomalu, volejte ihned 155.",
        "sk": "Ak je váš blízky po liekoch na bolesť nápadne ospalý, nedá sa zobudiť, nereaguje alebo dýcha pomaly, volajte ihneď 155.",
    },
    "nalada": {
        "cs": "Smutek, úzkost nebo pocit, že je toho moc, k léčbě často patří a není to selhání. Řekněte o tom týmu, může vám "
        "zprostředkovat psychologa. Pokud máte myšlenky, že byste si chtěli ublížit nebo vzít život, volejte ihned 155 "
        "nebo Linku první psychické pomoci 116 123 (nonstop).",
        "sk": "Smútok, úzkosť alebo pocit, že je toho priveľa, k liečbe často patria a nie je to zlyhanie. Povedzte o tom tímu, "
        "môže vám sprostredkovať psychológa. Ak máte myšlienky, že by ste si chceli ublížiť alebo vziať život, volajte ihneď 155.",
    },
    "pecujici": {
        "cs": "Péče o blízkého je náročná. Pokud jste vyčerpaní, nespíte nebo nevíte, jak dál, řekněte to týmu. Může zajistit "
        "pomoc, například domácí hospic, paliativní tým nebo sociální pracovnici.",
        "sk": "Starostlivosť o blízkeho je náročná. Ak ste vyčerpaní, nespíte alebo neviete, ako ďalej, povedzte to tímu. Môže "
        "zabezpečiť pomoc, napríklad domáci hospic, paliatívny tím alebo sociálnu pracovníčku.",
    },
    "leky_a_davky": {
        "cs": "Navigátor nemění léky ani dávky. Může vám připomenout jen to, co máte předepsané od lékaře, přesně podle rozpisu. "
        "O každé další dávce nebo změně rozhoduje lékař, proto se v takovém případě obraťte na tým.",
        "sk": "Navigátor nemení lieky ani dávky. Môže vám pripomenúť iba to, čo máte predpísané od lekára, presne podľa rozpisu. "
        "O každej ďalšej dávke alebo zmene rozhoduje lekár, preto sa v takom prípade obráťte na tím.",
    },
    "diagnoza": {
        "cs": "Chat neurčuje diagnózu. Co vaše potíže znamenají, posoudí lékař. Navigátor vám pomůže popsat potíže a předat je týmu "
        "monitorovacího centra, který se vám ozve.",
        "sk": "Chat neurčuje diagnózu. Čo vaše ťažkosti znamenajú, posúdi lekár. Navigátor vám pomôže opísať ťažkosti a odovzdať "
        "ich tímu monitorovacieho centra, ktorý sa vám ozve.",
    },
    "dych_hrudnik": {
        "cs": "Dušnost v klidu, náhlá dušnost s bolestí na hrudi nebo bušením srdce a nová bolest na hrudi jsou důvodem volat "
        "ihned 155. Pokud nově spíte vsedě nebo na více polštářích, ozvěte se ještě dnes týmu.",
        "sk": "Dýchavičnosť v pokoji, náhla dýchavičnosť s bolesťou na hrudi alebo búšením srdca a nová bolesť na hrudi sú dôvodom "
        "volať ihneď 155. Ak novo spíte posediačky alebo na viacerých vankúšoch, ozvite sa ešte dnes tímu.",
    },
    "krvaceni": {
        "cs": "Krev ve stolici, zvratcích nebo moči, černá stolice nebo krvácení z nosu déle než 20 minut jsou důvodem volat "
        "ihned 155. Při léčbě na ředění krve hlaste týmu i menší krvácení nebo nové modřiny.",
        "sk": "Krv v stolici, zvratkoch alebo moči, čierna stolica alebo krvácanie z nosa dlhšie ako 20 minút sú dôvodom volať "
        "ihneď 155. Pri liečbe na riedenie krvi hláste tímu aj menšie krvácanie alebo nové modriny.",
    },
    "mezitim": {
        "cs": "Než se vám tým ozve: pijte, odpočívejte, měřte si teplotu a mějte telefon u sebe. Zapište si, kdy potíže začaly "
        "a jaké léky jste vzali. Pokud se stav zhorší, nečekejte a volejte.",
        "sk": "Kým sa vám tím ozve: pite, odpočívajte, merajte si teplotu a majte telefón pri sebe. Zapíšte si, kedy ťažkosti "
        "začali a aké lieky ste užili. Ak sa stav zhorší, nečakajte a volajte.",
    },
    "zacpa": {
        "cs": "Při zácpě pijte dostatek tekutin, hýbejte se, jak to jde, a užívejte projímadla podle rozpisu. Bez stolice 3 dny "
        "a víc hlaste týmu. Když neodcházejí plyny ani stolice a k tomu zvracíte nebo máte křečovitou bolest břicha, volejte ihned 155.",
        "sk": "Pri zápche pite dostatok tekutín, hýbte sa, ako sa dá, a užívajte preháňadlá podľa rozpisu. Bez stolice 3 dni "
        "a viac hláste tímu. Keď neodchádzajú plyny ani stolica a k tomu zvraciate alebo máte kŕčovitú bolesť brucha, volajte ihneď 155.",
    },
}
