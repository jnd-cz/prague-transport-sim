# Tatra T3 — pražské tramvaje

**Česky** · [English](README.en.md) · [Pro vývojáře](DEVELOPING.md)

Řízení tramvaje Tatra T3 v 3D Praze postavené ze skutečných dat, na linkách 9, 17, 22, 23 a 37 (linky 17
a 22 se zaměřenými ulicemi): OpenStreetMap (kolejová síť, silnice, zeleň), Digitální technická mapa Prahy
(zaměřené ulice, dopravní vrstva DI pro koleje), 3D budovy a mosty IPR Praha, lidarový terén a jízdní řád
PID GTFS.

## Spuštění

```bash
python tools/serve.py 8742
```

Otevřete http://localhost:8742. Nic se nesestavuje: jsou to prosté moduly ES, knihovna Three.js se načítá z CDN.

Čerstvý klon nejdřív potřebuje herní data: [Set up](DEVELOPING.md#set-up).

<!-- help -->

## Hra

### Vaše směna

- Linku vyberete v menu (každá linka načítá vlastní svět). Označníky uvádějí denní linky, které na
  zastávce staví; tramvaje těchto linek jedou před vámi.
- Zastávky mají skutečné časy odjezdů. Otevřete dveře, počkejte na nástup a odjeďte včas; předčasný odjezd
  stojí nejvíc bodů. Zastávky na znamení (✋) můžete projet, když nikdo nečeká.
- Zastávku obsloužíte, když tramvaj stojí v místě určeném podle čela vozu:
  - **U nástupiště dlouhého aspoň 15 m,** je-li v datech: celá souprava stojí podél něj, konec soupravy nejvýše
    3 m před začátkem nástupiště a čelo nejvýše 4 m za jeho koncem. Za první soupravou tak může obsloužit
    zastávku druhá, na delším nástupišti i dvě soupravy 2×T3 za sebou (asi tři čtvrtiny zastávek). U nástupiště
    kratšího než souprava stačí čelo od 8 m před jeho koncem do 4 m za ním.
  - **Jinde:** čelo od 20 m před označníkem do 12 m za ním.
  - **Návěstidlo těsně za zastávkou:** čelo nejvýše 0,5 m před ním.
- Bod zastavení je označník: do 3 m od něj získáte bonus 15 bodů za přesnost. Zastavit o kousek dál se stává
  i ve skutečnosti a cestující přesto nastoupí a vystoupí, proto do 4 m za označníkem hra nic nestrhne; přejetí
  o více než 4 m stojí 20 bodů, i když zastávku obsloužíte. Zastavení dál vzadu v povoleném místě se netrestá.
- Cestující: počítadlo ve voze (běžná obsaditelnost 110, nejvýše 160 na vůz). Poptávka se řídí denní dobou:
  ranní (7–9:30) a odpolední (15:30–17:30) špička přivádí davy, v noci je klid; v přeplněném voze trvá nástup
  déle a při plném vozu zůstanou cestující čekat na další spoj.
- Změna linky: spoj může na trase linky a na konečné změnit číslo (linka 9 pokračuje na Nákladovém nádraží Žižkov jako 10):
  všichni vystoupí, přepnou se směrové tabule i údaje na obrazovce a tramvaj odjíždí jako 10.

### Klávesy

| klávesa | co dělá |
|---|---|
| `W` / `↑` | k jízdě (stupně J1–J5; pokročilé: ťuknutí o stupeň, držením dál) |
| `S` / `↓` | k brzdě (B1–B5) |
| `Mezerník` | nouzová a kolejnicové brzdy (držet) |
| `N` nebo `0` | obě šlapky volné (výběh) |
| `1`–`5` | jízdní stupeň; se `Shift` brzdný |
| `R` | zabrzdit a odbrzdit zajišťovací brzdu (pokročilé ovládání) |
| `A` | pískování (držet) |
| `D` | dveře |
| `B` | zvonec |
| `Y` | tlačítko **Výhybka**: proud přes kontakt (držet) |
| `C` | odpojení topení (držet pod kontaktem, pro průjezd bez proudu) |
| `X` | přestavit výhybku stavěcím klíčem (stojící vůz) |
| `H` / `K` / `F` | topení sedaček v salónu / kalorifer / klapka odpadního tepla |
| `Q` / `E` nebo `←` / `→` | pohled z levého / pravého okna (držet) |
| `G` | přiblížit pohled ze stanoviště třikrát, jako když se řidič zahledí do dálky: přečtete návěst na 75 m (držet, i v pauze) |
| `Z` | pravé zrcátko zapnout a vypnout |
| `V` | pohled ze stanoviště řidiče nebo zvenku |
| `O` | autopilot zapnout a vypnout |
| `M` | zvuk zapnout a vypnout |
| `P` / `Esc` | pauza |
| `F9` | nahlásit problém |

Bdělostní pedál, je-li v menu zapnutý, je držený `Shift`.

### Jízda

- **Výzbroj TR 37 vozu T3:** dvě šlapky bez aretace. Jízdní stupeň (J1–J5) nastaví proud, který zrychlovač
  drží postupem přes svých 99 poloh (odporníky do 75, šuntování při 80–95); brzdný stupeň (B1–B5) nastaví
  brzdný proud; elektrodynamická brzda slábne pod ≈6 km/h, kde nastupují čelisťové brzdy (částečně na
  stupních 3–4, plně od stupně 5 nebo se zajišťovací brzdou); konec zdvihu brzdové šlapky přidá kolejnicové brzdy.
  Otevřené dveře nebo brzdová šlapka mimo nulu vypínají trakci. Hned po jízdě se brzda buduje pomalu a stupeň
  5 pak přivede čelisti za jízdy: mezi jízdou a brzdou vyčkejte 2–3 s kvůli vrácení zrychlovače do základní
  polohy. Sloupec šlapek na panelu řidiče ukazuje šlapku (jízda nahoru, brzda dolů, P zabrzděno) a zrychlovač.
- **Zrychlovač** (žlutý sloupec vedle šlapek, dole poloha 1, nahoře 99) se točí jen svým řídicím motorkem, nejvýš
  asi 20 poloh za sekundu, a řídí ho omezovací relé podle proudu: při jízdě vyřazuje odpory, tím rychleji, čím
  vyšší je stupeň. Po puštění šlapky drží malý proud přípravy, takže se s klesající rychlostí vrací (asi 31 při
  20 km/h, 50 při 30 km/h) a při jízdě ze svahu zase stoupá; při brzdění drží proud stupně: čím vyšší stupeň,
  tím níž stojí. Při jízdě znamená vysoko málo odporu, při brzdění naopak hodně.
- **Napájení:** napětí v troleji klesá s vaším odběrem, se vzdáleností od měnírny a s odběrem jiných tramvají na
  stejném napájení (odpory vedení jsou odhad, pozice měníren z OSM). Na odporech to sílu nezmění, jen zrychlovač
  stojí výš; nad nimi slabá trolej znamená menší tah a nižší nejvyšší rychlost. Elektrodynamické brzdě je jedno.
  Motorgenerátor s oběma ventilátory je na jedné hřídeli a jeho sériový motor se točí podle napětí: proto
  tón klesne, když se rozjíždíte, a klesne i přidržením čelistí na dynamu; palubních 26 V regulátor drží.
  Informační panel ukazuje napětí, měnírnu, palubní napětí a otáčky.
- **Ovládání** (menu): *Jednoduché* posouvá páku po stupních (W/S, 1–5, Shift+1–5) a šlapky ovládá jako
  řidič, stojící vůz samo zabrzdí; *Pokročilé* ovládá přímo šlapky (ťuknutí o stupeň, držením dál rychlostí
  20°/s; držené klávesy se zastaví na brzdném stupni 5) a R zabrzdí a odbrzdí zajišťovací brzdu; po
  zabrzdění se čelisti plně uvolní až jízdní šlapkou. Mezerník je v obou nouzová brzda.
- Prázdný vůz zrychluje podle stupně 0,6–1,8 m/s², plný pomaleji; gravitace na sklonech (Chotkova ~7 %),
  odpor v obloucích, couvání po uvolnění brzdy v kopci, boční pohodlí v obloucích.
- Počasí: sucho / déšť / podzimní listí určuje adhezi kola a kolejnice. Příliš velký proud protočí kola,
  příliš silná brzda je zablokuje (ploché body). Pískujte držením A; nouzová brzda pískuje sama a její
  magnetické kolejnicové brzdy na adhezi nezávisí.
- Rychlosti: 50 km/h, pokud traťová rychlost neříká jinak, nejvýše 65 km/h tramvaje T3. Každý oblouk dovolí √(a·R)
  s nevyrovnaným bočním zrychlením 0,8 m/s², nejméně 15 km/h, není-li trať značena níž. Výhybka proti hrotu je 15 km/h
  od jazyků po srdcovku, ať je postavená kamkoli, dokud ji nemine zadní čelo vlaku. Ve smyčce je 15 km/h od výhybky
  do smyčky po výhybku ze smyčky. Označník zastávky, kde vlak nestaví, projede čelo nejvýše 30 km/h (místo s omezenou
  rychlostí: vlak smí zrychlit, jakmile ho čelo mine). Oblouky na vlastním tělese jsou
  převýšené (do 100 mm, u zastávek a konečných bez převýšení); tramvaj i pohled se do nich naklánějí.
- Soupravy: většina linek jezdí dvouvozovými soupravami T3 (2 × 15,2 m přes spřáhla, oba vozy poháněné, šest
  dveří); na lince 23 jezdí sólo historický vůz. „Souprava“ v menu to změní. Každý vůz sleduje kolej na
  vlastních podvozcích.

### Výhybky

- Každá rozjezdová výhybka (pojížděná proti hrotům) má pracovní trolejový kontakt (žlutý štítek, bílá tabulka s černým trojúhelníkem),
  který ovládá sběrač: projeďte pod ním s proudem pro odbočení, nebo bez proudu pro jízdu rovně — i hned za
  zastávkou, u návěstidla nebo do kopce (odhadnout to patří k umění řidiče).
- Proud teče i při tlačítku **Výhybka** (Y, jako na T3SUCS: jen bez jízdy a se zrychlovačem do polohy 30, tedy
  asi do 20 km/h) a — v zimě — topením, pokud při průjezdu pod
  kontaktem bez proudu nedržíte odpojení topení (C).
- Kontakty jsou ~22 m před výhybkou, nikdy však tam, kde tramvaj stojí se sběračem u zastávky nebo návěstidla.
  Sjezdové výhybky (pojížděné po hrotech, kde se koleje spojují) nic nepotřebují; kolejová křížení nejsou výhybky.
- Červené LED návěstidlo před každou výhybkou ukazuje postavení jazyků (šipka vlevo či vpravo, svislý pruh rovně)
  a bliká, když je výhybka uzamčená. Když to nevyjde, zastavte a použijte stavěcí klíč (X).
- Rychlostní výhybky R07 (Kotlářka, linka 9) a R09 (Podolské nábřeží, linka 17) mají svá návěstidla: číselnou
  tabulku, výzvové návěstidlo, vjezdové pražcové návěstidlo a bílou LED šipku nad číslem. Bez přihlášení číslo
  nesvítí a výhybka se projíždí jako ostatní, 15 km/h.

### Návěstidla

- Pražská tramvajová návěstidla (čtyři světla: tři nahoře, jedno dole): dvě krajní horní = stůj; horní
  prostřední + dolní = volno rovně; horní levé nebo pravé + dolní = volno vlevo nebo vpravo; blikající volno
  znamená, že končí.
- Výzvové návěstidlo pod ním má tři LED pruhy (\ | /): pruh směru, kterým pojedete, se rozsvítí žlutě, jakmile
  je tramvaj zjištěna, a těsně před volnem bliká. Předvěsti se žlutým štítkem „P“ stojí před návěstidly
  skrytými za obloukem.
- Křižovatky: každé návěstidlo patří k řadiči křižovatky s pevným cyklem (tramvaje rovně v obou směrech, fáze
  pro odbočení, příčná ulice) a preferencí tramvají; řídí se jím i protijedoucí tramvaje. Příčná doprava jede
  skutečnou příčnou ulicí a stojí u své čáry, dokud má tramvaj volno.
- Splítka v Letenské (pod budovou u Malostranského náměstí): oba směry sdílejí ~65 m koleje. Návěstidla na obou
  koncích pouštějí do úseku vždy jeden směr, za vjíždějící tramvají se vrátí na stůj a druhou stranu drží, dokud
  se úsek neuvolní, a ještě 6 s poté. Řídí se jimi i protijedoucí tramvaje.

### Topení

Topení je podle příručky DPP k T3SUCS: sedačky v salónu 0/1/2 (H: tři sedačky vpravo i vlevo / všechny),
kalorifer na stanovišti řidiče 0–3 (K: vypnuto / neohřátý vzduch / polovina topnic / plný výkon) a klapka, která pouští odpadní
teplo z odporníků zrychlovače do salónu (F). Informační panel ukazuje teplotu venku, v salónu a na stanovišti.
Venkovní teplota: Praha teď nebo pevný zimní / podzimní / letní den (menu). Prochladlí cestující (< 12 °C)
a horko, které jste způsobili, stojí body; otevřenými dveřmi teplo uniká; v létě si cestující otevírají okna.

### Rozhlížení

- Držením Q / E (nebo ← / →) se díváte levým / pravým oknem; pravé zpětné zrcátko (Z zapíná a vypíná) ukazuje
  bok soupravy a dveře. Roste s oknem prohlížeče a zorné pole se nemění.
- **Pohled zvenku** (V): kamera obíhá kolem tramvaje. Tažením ji otáčíte a nakláníte, kolečkem nebo dvěma prsty
  přibližujete, dvojklik ji vrátí za tramvaj.

### Provoz

- Na stejné koleji jedou před vámi další tramvaje (staví na zastávkách a před červenou: držte odstup) a po
  protější koleji tramvaje v protisměru; každá nese linku, která na té zastávce opravdu staví, a za poslední
  zastávkou společnou s vaší linkou odbočí (zmizí).
- Auta jezdí v pruzích podél kolejí po skutečném tvaru silnic a v jednosměrkách i po okolní silniční síti, přes
  křižovatky pokračují dál. Na křižovatkách dávají přednost, drží odstup, řadí se za tramvají na společné koleji
  a staví chodcům; tramvaje staví za auty na své koleji.
- Chodci chodí po chodnících a mimo koleje. Vše se plynule objevuje a mizí.
- Překážky: zaparkovaná auta zasahující do průjezdného průřezu (zazvoňte) a přecházející chodci.

### Město

- Terén: koridor trati je zaříznutý do lidarového terénu; opěrné zdi tam, kde trať vede v zářezu ve svahu
  (Chotkova), Most Legií na mostovce s pilíři.
- Značky: klasické červené pražské označníky; rychlostní návěsti podle předpisu D 1/2 (omezení rychlosti černým
  číslem na žluté, rychlostník bílým na černé, předzvěstní trojúhelník, „r“ oblouku o malém poloměru, nebezpečné
  stoupání a klesání), dvakrát větší než skutečné, aby se daly přečíst na obrazovce. Tabulky
  kontaktů. Přechody
  jsou namalované tam, kde jsou zmapované (ne přes koleje). Návěstidla a značky stojí mimo vozovku: na trakčních
  stožárech, zavěšené na příčných lanech vedle troleje nebo u obrubníku — ne na nástupištích.
- Trolejové vedení: příčná lana kotvená na stožárech u obrubníku (mezi vozovkou a chodníkem), na růžicích ve zdi,
  kde stojí blízko budova, nebo výložník, kde na jedné straně není místo; v obloucích hustěji. Stromy v ulicích
  jsou prořezané tak, aby nezasahovaly do žádné koleje.
- Budovy mají textury podle typu (starý činžák, panelák, kostel, průmyslová hala, prosklená kancelář). Skutečné 3D
  mosty určují výšku mostovky a podjezdnou výšku pod konstrukcemi (i pod zastřešením stanic).

### Volby v menu

- Automatické výhybky (palubní počítač staví každou výhybku rádiem místo trolejových kontaktů); přehled výkonu
  (FPS, doba snímku, volání kreslení, trojúhelníky, paměť JS).
- Model tramvaje: podrobný a pohyblivý (spojení „Tatra T3“ od SimonStrikesBack, CC BY 4.0, a „Tatra T3“ od
  Jakuba Váji (conflig), CC BY-NC 4.0, obojí na Sketchfabu; celek CC BY-NC 4.0): dveře, sběrač, brzdová světla
  a čelisti kolejnicových brzd se řídí hrou, druhý vůz soupravy visí na spřáhle; podrobný klasický (samotný model
  od conflig, CC BY-NC 4.0, stáhne se při výběru); nebo vestavěný jednoduchý.

### Na telefonu nebo tabletu

Tlačítka na obrazovce, na dotykové obrazovce zobrazená automaticky, přepínaná 🎮 v menu (pamatuje si je
zařízení). Posílají klávesy klávesnice:

- řada nad panelem řidiče: ▼ brzda, 0 neutrál, ▲ jízda (po stupni), STOP (nouzová brzda, držet) a tlačítko
  bdělosti, je-li ta volba zapnutá;
- levý sloupec: dveře, zvonec, písek (držet), pohled vlevo / vpravo (držet), 🔍 přiblížení (držet), pohled, zrcátko, pauza;
- ⋯ pro ostatní: zajišťovací brzda (pokročilé ovládání), kontakt výhybky, stavěcí klíč, odpojení topení, topení, autopilot,
  zvuk, ⚑ hlášení.

Na malé obrazovce jsou panel řidiče a horní lišta menší a mapka je skrytá.

## Autopilot

Zaškrtněte v menu „Autopilot — jen se dívat na jízdu“ nebo během směny stiskněte **O**. Plánuje rychlost podle
omezení, zastávek, návěstidel, překážek a tramvaje před sebou, volí sílu potřebnou na sklonu a nechává výzbroj
ovládat šlapky jako pečlivý řidič (pokročilý model: na rovině rozjíždí na stupních 1–3, brzdí po stupních, do zastávky
jednou křivkou a bez návratu na jízdní šlapku, pokud před ním nestojí tramvaj, ve stání zabrzdí zajišťovací brzdou, stupně
1–4 jen do 2,5 s po jízdě), obsluhuje dveře, odjíždí včas, zvoní, pískuje na kluzké koleji a pod kontakty odebírá proud
pro odbočení (přepínačem výhybek, když jede dost pomalu, jinak krátkým impulsem jízdní šlapky) nebo jede bez proudu (rovně).
Klávesou **V** přepnete na pohled zvenku. Řízení převezme
kterákoli klávesa kontroléru nebo dveří (W/S/mezerník/N/D/R, 0–5), v ovládání zvoleném v menu; O je předá zpět
autopilotu.

## Jazyk

Rozhraní i tato nápověda jsou česky nebo anglicky (Nastavení → Jazyk v menu; prohlížeč si volbu pamatuje).

<!-- /help -->

## Licence

Kód: GNU GPL v3 ([LICENSE](LICENSE)). Modely a textury: [ASSETS.md](ASSETS.md) (podrobný model T3 je CC BY-NC 4.0). Zdroje dat a jejich uvedení: [NOTICE.md](NOTICE.md).

Data © přispěvatelé OpenStreetMap (ODbL); jízdní řád PID GTFS, data.pid.cz (CC BY 4.0);
terén ČÚZK DMR 5G (CC BY 4.0); 3D budovy, opěrné zdi a stromy: datový podklad © IPR Praha (CC BY 4.0).
