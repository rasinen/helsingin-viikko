# Helsingin viikko

Joka sunnuntai-iltana noin kello 18–19 (Suomen aikaa) tämä palvelu kokoaa **seuraavan viikon** (maanantaista sunnuntaihin) tapahtumat Helsingistä ja sääennusteen. Se lähettää sinulle sähköpostin ja julkaisee saman viikon selaimessa avattavalle sivulle.

Mitään tapahtumaa ei piiloteta. Jos peukutat, järjestys vain muuttuu: pitämäsi asiat nousevat ylemmäs.

## Mitä viestissä ja sivulla on

- Viikon sää, päivä kerrallaan.
- Osio sinulle. Aluksi, ennen kymmentä peukutusta, siinä on sekalainen näyte ja tapahtumat ovat muuten kellonajan mukaan. Sen jälkeen osio on nimeltään **Sinulle suositeltua**.
- Jokainen päivä ja oma osio tapahtumille, jotka kestävät useamman päivän (esimerkiksi näyttelyt). Niitä ei toisteta joka päivän kohdalla.
- Kaupungin listassa on yli tuhat riviä viikossa, myös palvelukeskusten ryhmiä. Sähköpostiin mahtuu päivän kiinnostavimmat. **Koko lista on verkkosivulla**, ja sitä voi rajata.

Pysyvät näyttelyt, jotka kestävät yli viisi kuukautta, jätetään pois. Ne eivät ole tämän viikon ohjelmaa.

## Näin muutat asetuksia ilman koodaamista

1. Avaa projekti GitHubissa.
2. Klikkaa tiedostoa `config.json`.
3. Klikkaa kynän kuvaa (Edit).
4. Muuta haluamasi kohdat. Tallenna vihreällä **Commit changes** -painikkeella.

Tiedoston kentät:

| Kenttä | Merkitys |
| --- | --- |
| `interested_topics` | Sanat, joita haluat nostaa. Esimerkiksi `"musiikki"`. Voit lisätä tai poistaa rivejä. Älä poista lainausmerkkejä tai pilkkuja sokkona. |
| `excluded_topics` | Sanat, joita haluat laskea alemmas. Tapahtumia ei silti poisteta. |
| `free_only` | `true` = sähköposti ja sivun oletus näyttävät maksuttomat. `false` = kaikki. |
| `recommendation_count` | Montako tapahtumaa "Sinulle suositeltua" -listassa. Oletus 8. |
| `novelty_ratio` | Kuinka suuri osa suosituksista on aiheita, joita et ole vielä arvioinut. `0.2` tarkoittaa noin viidennestä. |
| `email_per_day` | Montako tapahtumaa yhdeltä päivältä mahtuu sähköpostiin. Oletus 10. Iso luku tekee viestistä pitkän, ja puhelin saattaa näyttää vain alun. |
| `email_spanning_limit` | Montako koko viikon tapahtumaa sähköpostiin. Oletus 8. |

Sähköpostiosoitetta **ei** kirjoiteta tähän tiedostoon. Se on tallennettu erikseen salaisuudeksi.

## Näin opettat suodatinta

Jokaisen tapahtuman alla on kolme valintaa:

- **Pidän**
- **Ei kiinnosta**
- **Menen tai kävin** — tämä painaa eniten

Saman tapahtuman uusi valinta korvaa vanhan. Ennen kymmentä selkeää valintaa sivu ei väitä oppineensa mitään.

Noin viidesosa suosituspaikoista on tapahtumia, joiden aiheita et ole vielä arvioinut. Ne on merkitty sanoilla **Uutta sinulle**.

Kun avaat tapahtuman linkin sähköpostista, välissä käydään pienessä palvelussa ja käynti lasketaan **pieneksi plussaksi** (selvästi heikompi kuin peukku). Varsinainen sivu aukeaa heti perään.

### Mitä suodatin on oppinut

Sivun alaosassa on linkki **Mitä suodatin on oppinut**. Siellä näet, mitkä asiat nostavat ja mitkä laskevat pisteitä, sekä peukutusten määrän.

### Oppimisen nollaus

Samalla sivulla on painike **Nollaa oppiminen**. Se pyytää varmistuksen ja pyyhkii peukutukset. Seuraava viikkokirje aloittaa alusta.

Nollaus ja peukut sivulla toimivat, kun olet avannut sivun sähköpostin linkistä ainakin kerran. Linkki on henkilökohtainen. Älä lähetä viestiä eteenpäin, jos et halua muiden peukuttavan puolestasi.

## Näin käynnistät ajon itse

Ajon ei tarvitse odottaa sunnuntaita.

1. Avaa projekti GitHubissa.
2. Valitse ylhäältä **Actions**.
3. Valitse vasemmalta **Helsingin viikko**.
4. Paina **Run workflow** ja sitten vihreää painiketta.

Muutaman minuutin päästä sivusto päivittyy. Sähköposti lähtee, jos Gmail-salaisuudet on tallennettu (ohje alla).

## Jos viesti ei tule

1. Katso roskaposti ja tarjoukset-kansio.
2. Avaa GitHubissa **Actions** ja uusin ajo. Vihreä merkki tarkoittaa, että ajo onnistui. Punainen merkki avautuu klikkaamalla, ja ylimmästä virheestä näkee, mikä vaihe epäonnistui.
3. Jos teksti kertoo, että salaisuudet puuttuvat, tee alla oleva Gmail-osio.
4. Jos sää tai tapahtumat puuttuvat vain osittain, viesti lähtee silti ja kertoo mitä puuttui. Jos molemmat epäonnistuvat, viestiä ei lähetetä ja ajo näkyy punaisena.
5. Jos peukutuksia ei saatu haettua, viesti käyttää viimeksi tallennettua järjestystä tai kellonaikaa. Siitä kerrotaan viestissä.

## Yksityisyys

Verkkosivu ja tämä projekti ovat julkisia, jotta sivu voidaan näyttää ilmaiseksi. **Peukutuksesi ja opitut painot eivät ole sivulla eivätkä tässä projektissa.** Ne ovat erillisessä tallennuksessa, johon vain sinun linkkisi avaa henkilökohtaisen järjestyksen.

Ilman sähköpostin linkkiä sivu näyttää tapahtumat kellonajan mukaan. Asetuksissa mainitut aiheet näkyvät, koska ne ovat tässä `config.json`-tiedostossa.

Vaihtoehto: jos koko sivu pitäisi olla vain sinulle, projekti pitäisi muuttaa yksityiseksi. Ilmaisessa GitHubissa yksityisen projektin sivua ei voi julkaista. Siksi sivu on julkinen ja maku pidetään erillään.

## Gmail-salasana lähetykseen

Viesti lähtee oman Gmail-tilisi kautta. Tavallinen Gmail-salasana ei käy. Tarvitaan erillinen **sovelluksen salasana**. Sitä ei saa kirjoittaa tähän keskusteluun eikä `config.json`-tiedostoon.

1. Avaa [Google-tilin suojaus](https://myaccount.google.com/security).
2. Kohdassa **Kaksivaiheinen vahvistus** ota vahvistus käyttöön, jos se ei jo ole. Google voi pyytää puhelinta.
3. Avaa [sovellusten salasanat](https://myaccount.google.com/apppasswords). Jos linkki ei aukea, hae tilin haulla sanat "sovelluksen salasanat".
4. Anna nimeksi `Helsingin viikko` ja luo salasana. Google näyttää 16 merkkiä. Kopioi ne.
5. Avaa GitHubissa projekti → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
6. Lisää kolme salaisuutta yksi kerrallaan. Nimi pitää olla täsmälleen tämä:

| Nimi | Arvo |
| --- | --- |
| `SMTP_USER` | Gmail-osoitteesi, esimerkiksi oma nimi ja `@gmail.com` |
| `SMTP_PASSWORD` | äskeinen 16 merkin salasana, ilman välilyöntejä |
| `EMAIL_TO` | osoite, johon viikkokirje tulee |

7. Käynnistä ajo kohdan "Näin käynnistät ajon itse" mukaan.

## Palautteiden tallennus (Cloudflare)

Peukutukset eivät mahdu pelkälle staattiselle sivulle. Ne tallentuvat ilmaiseen Cloudflare-palveluun. Tili riittää, mutta tarvitaan vielä yksi avain, jotta sunnuntaiajo saa luvan tallentaa. Avainta ei saa kirjoittaa tähän keskusteluun eikä `config.json`-tiedostoon.

1. Avaa [API-avaimet](https://dash.cloudflare.com/profile/api-tokens).
2. Paina **Create Token**.
3. Etsi rivi **Edit Cloudflare Workers** ja paina **Use template**.
4. Paina **Continue to summary** ja sitten **Create Token**.
5. Kopioi avain heti. Cloudflare näyttää sen vain kerran.
6. Avaa GitHubissa projekti → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
7. Nimeksi täsmälleen `CLOUDFLARE_API_TOKEN` ja arvoksi äskeinen avain. Tallenna.
8. Kirjoita keskusteluun: avain on tallennettu. Älä liitä itse avainta.

Sen jälkeen viikkokirjeen peukut ja sivun painikkeet alkavat tallentua. Avain pysyy samana, kunhan Gmailin sovellussalasanaa ei vaihdeta. Jos vaihdat sen, päivitä vanha `SMTP_PASSWORD`-salaisuus. Seuraava ajo tekee palautteille uuden avaimen itse.
