# Javni cjenik za potrošače (l10n_hr_price_list)

Modul za Odoo 19 (Community i Enterprise). Sam sastavlja i objavljuje cjenike robe i usluga za potrošače u CSV
datotekama, za svaki vaš objekt, s **baznom cijenom** uz svaku cijenu, kako traže Zakon o zaštiti potrošača i
pravilnici Ministarstva gospodarstva (NN 132/26, primjena od **17. 11. 2026.**). Vi upišete objekt i stavite
poveznice na svoju web stranicu; sve ostalo ide samo.

## Što propis traži i što radi modul

Obveza vrijedi za prodaju **potrošačima** (B2C), za sve koji imaju web stranicu. Propisi (NN 132/2026):
*Pravilnik o isticanju bazne cijene proizvoda* i *Pravilnik o načinu objave cjenika proizvoda*. Ranije odluke
Vlade o „dodatnoj cijeni” (NN 75/25, 101/26, 110/26) prestale su važiti 17. 11. 2026.

| Propis traži | Modul |
|---|---|
| cjenik u CSV ili XML datoteci, javno, bez prijave i bez zapreka za automatsko preuzimanje | objavljuje ga na javnoj poveznici ili šalje na vaš web |
| zaseban cjenik robe i cjenik usluga, propisani stupci propisanim redom | dvije datoteke po objektu, točno propisani stupci |
| zaseban cjenik za svako prodajno mjesto ili jedan za sva (isti cjenik svugdje) | jedan objekt = jedan cjenik; ili jedan objekt *Sva prodajna mjesta* |
| naziv datoteke: OIB (obrt: matični broj), prodajno mjesto, roba/usluge, broj pohrane, vrijeme | sastavlja ga sam iz podataka tvrtke i objekta |
| bazna cijena uz svaku cijenu (cijena 2. 5. 2025. za hranu, piće, kozmetiku, sredstva za čišćenje, toaletne potrepštine i proizvode za kućanstvo, 10. 9. 2026. za ostalo, ili pri prvoj ponudi nakon toga) | upiše je sama pri prvoj objavi; kasnije se ne mijenja |
| oznaka je li cijena iz posebnog oblika prodaje (akcije) | iz pravila cjenika s nazivom akcije |
| izmijenjen cjenik najkasnije do 11:00 na dan izmjene, na istoj adresi | minutu nakon promjene; trenutna datoteka uvijek na istoj poveznici |
| zamijenjeni cjenik dostupan 15 dana | arhiva; verzija se ne može obrisati dok je trenutna i 15 dana nakon zamjene |

## Brzi početak

„Administrator“ je korisnik s pravom *Administracija: Postavke*.

1. **Instalirajte** modul: *Aplikacije* → potražite „Public Price List“ → *Aktiviraj*. Treba aplikacija
   Računovodstvo.
2. **Podaci tvrtke:** u tvrtki mora biti **OIB** (*Porezni broj*). Ako je trgovac **obrt** (fizička osoba):
   *Računovodstvo → Konfiguracija → Postavke → Javni cjenik* → kvačica **Fizička osoba (obrt)**, a u tvrtki
   upisan **Matični broj** – tada naziv datoteke počinje matičnim brojem.
3. **Dodajte objekt:** *Računovodstvo → Konfiguracija → Objekti javnog cjenika* → **Novi**:
   - **Oblik objekta** – npr. `prodavaonica`, `ured`, `servis`, `salon`, za internetsku trgovinu `webshop`;
   - **Adresa objekta** – samo ako nije adresa sjedišta tvrtke, npr. `Ilica 150 Zagreb`;
   - **Oznaka objekta** – vaša oznaka (npr. oznaka poslovnog prostora iz internog akta, `P-01`) ili `01`;
   - **Kategorije proizvoda** – neobavezno: prazno znači svi proizvodi za prodaju; odaberite kategorije ako
     neke proizvode ne prodajete potrošačima;
   - **Sva prodajna mjesta** – samo ako na svim prodajnim mjestima imate isti cjenik: tada je jedan objekt
     dovoljan, a oblik i adresa ne trebaju.

   Spremite. Cjenici se objave za minutu (ili odmah gumbom **Objavi cjenik sada**, koji javi i ako nešto
   nedostaje).
4. **Dopunite proizvode:** na proizvodu, kartica *Opći podaci*, odjeljak **Javni cjenik**: **Marka** za robu;
   na proizvodu još **Interna oznaka** (šifra) i **Barkod** ako ih imate.
5. **Ispravite bazne cijene** za proizvode koje ste nudili na referentni dan (vidi *Bazne cijene*).
6. **Stavite poveznice na web:** „Cjenik robe” i „Cjenik usluga” na `…/cjenik/<oznaka objekta>/roba` i
   `…/usluge`, „Arhiva cjenika“ na `…/cjenik/arhiva` (vidi *Objava na vašoj web stranici*).

Provjera: na objektu gumb **Verzije** → zadnja verzija → preuzmite datoteku. Prvog dana zbog dopuna nastane
nekoliko verzija; to je u redu.

## Odakle su cijene

Cijena u cjeniku je cijena s PDV-om kakvu Odoo stavlja na ponudu i račun građaninu:

- **Prodajna cijena** proizvoda s njegovim *Prodajnim porezima*, ili
- ako su uključeni **Cjenici** (*Prodaja → Konfiguracija → Postavke → Cjenici*): cijena iz **zadanog cjenika**,
  tj. cjenika koji Odoo daje kupcu iz Hrvatske bez vlastitog cjenika. To je obično prvi na popisu
  *Prodaja → Proizvodi → Cjenici*; ako je neki cjenik ograničen na grupu država u kojoj je Hrvatska, prednost
  ima on.

Na objektu se cijene ne postavljaju. Okrugla cijena s PDV-om: prodajnu cijenu upišite tako da s PDV-om bude
okrugla (npr. 39,92 € + 25 % = 49,90 €) ili koristite porez uključen u cijenu.

**Roba ili usluga** određuje *Vrsta proizvoda*: *Usluga* ide u cjenik usluga, sve ostalo u cjenik robe.

## Svakodnevni rad

Ne treba ništa raditi. Odoo objavljuje novu verziju cjenika koji se promijenio:

| Što se dogodi | Kada se objavi |
|---|---|
| promijenite cijenu, naziv, šifru, barkod, porez ili kategoriju proizvoda | za minutu (obično 1–4 minute) |
| dodate novi proizvod za prodaju | za minutu, s baznom cijenom i današnjim datumom |
| dodate, promijenite ili obrišete pravilo cjenika (akciju) | za minutu |
| počne ili završi akcija s razdobljem važenja | ujutro (5–6 h), puno prije roka u 11:00 |

Bez promjena nova verzija ne nastaje. Objavu odmah radi gumb **Objavi cjenik sada** na objektu.

## Akcije (posebni oblici prodaje)

Akcija se radi kao inače u Odoo-u, **pravilom cjenika**: prodajna cijena proizvoda ostaje redovna, a pravilo
daje popust u zadanom razdoblju. Isto pravilo vrijedi na ponudama i računima, pa je cijena svugdje ista.
Treba aplikacija **Prodaja** s uključenim **Cjenicima**.

1. *Prodaja → Proizvodi → Cjenici* → **zadani cjenik** (obično prvi na popisu, vidi *Odakle su cijene*) →
   kartica **Prodajne cijene** → **Dodaj stavku** (ili na proizvodu, kartica **Cijene**).
2. U pravilu: **Primijeni na** (proizvod, kategorija ili sve), **Vrsta cijene** *Popust* i postotak (ili
   fiksna cijena), **Razdoblje važenja** (od 00:00 do 23:59) i **Posebni oblik prodaje** – naziv akcije, npr.
   `Jesensko sniženje`.
3. Spremite. Cjenik prikazuje akcijsku cijenu od početka akcije, a ujutro nakon kraja opet redovnu cijenu.

**Primjer:** stolna svjetiljka ima *Prodajnu cijenu* 40,00 € (bez PDV-a, uz porez 25 %), kao i 10. 9. 2026.
U zadani cjenik dodate pravilo:

| Polje | Vrijednost |
|---|---|
| Primijeni na | Proizvod: *Stolna svjetiljka* |
| Vrsta cijene | Popust, `20` % |
| Razdoblje važenja | 1. 12. 2026. 00:00 – 31. 12. 2026. 23:59 |
| Posebni oblik prodaje | `Zimsko sniženje` |

Od 1. 12. ujutro redak svjetiljke u cjeniku robe glasi:

| Stupac | Prije akcije | Za vrijeme akcije |
|---|---|---|
| `maloprodajna_cijena_eur` | 50,00 | **40,00** (32,00 € + PDV) |
| `posebni_oblik_prodaje` | ne | **da** |
| `bazna_cijena_eur` | 50,00 | 50,00 (ne mijenja se) |

Ponuda građaninu u prosincu ima istu cijenu (32,00 € + PDV), a 1. 1. 2027. ujutro cjenik je opet na 50,00.

- Pravilo **bez** naziva akcije je redovna cijena za potrošače, a ne akcija. Redovna cijena je cijena iz
  zadanog cjenika bez pravila s nazivom akcije (bez Cjenika: *Prodajna cijena*).
- **Mnogo artikala:** jedno pravilo za njihovu kategoriju; ako nisu u jednoj kategoriji, pravila uvezite iz
  tablice: popis cjenika → označite zadani cjenik → **⚙ Radnje → Izvoz** s poljima *ID* i iz *Pravila
  cjenika*: *Primijeni na*, *Proizvod*, *Izračunaj cijenu*, *Postotak cijena*, *Datum početka*, *Datum
  završetka*, *Posebni oblik prodaje*; u tablici *ID* samo u prvom retku, ispod jedan redak po artiklu; zatim
  **⚙ → Uvoz zapisa**. Postojeća pravila ostaju.
- **Najniža cijena u 30 dana prije akcije** (mora stajati uz akcijsku cijenu u prodaji i na webu): modul je
  računa iz objavljenih cjenika i šalje webhookom; u propisanoj datoteci nema tog stupca.
- Računi napravljeni izravno u Računovodstvu (bez ponude) ne koriste cjenike – tako radi Odoo. Za akcijske
  artikle radite ponudu i iz nje račun.

## Bazne cijene

- Pri **prvoj objavi** proizvod dobije baznu cijenu: svoju trenutnu cijenu s **današnjim** datumom
  (za vrijeme akcije redovnu cijenu, vidi *Akcije*). To je ispravno za proizvode uvedene nakon referentnog dana.
- Za proizvode koje ste nudili na **referentni dan** administrator na proizvodu (odjeljak **Javni cjenik**,
  popis baznih cijena) upiše cijenu s PDV-om toga dana i datum:
  - **2. 5. 2025.** za hranu, piće, kozmetiku, sredstva za čišćenje, toaletne potrepštine i proizvode za
    kućanstvo; ako je tada bila akcija, najnižu cijenu u 30 dana prije te akcije;
  - **10. 9. 2026.** za ostalu robu i usluge; ako je tada bila akcija, prethodnu (redovnu) cijenu.
- Kasnije promjene cijene baznu cijenu **ne mijenjaju**; promijeniti je može samo administrator. Svaki objekt
  ima svoje bazne cijene.
- Datum bazne cijene nije stupac propisane datoteke; vidi se na proizvodu i šalje webhookom (npr. za natpis
  „Cijena na 10. 9. 2026.” na webu).
- Bazna cijena ne ističe se za cijene uređene posebnim propisima, popuste za pojedine skupine kupaca ili načine
  plaćanja, personalizirane i dinamičke cijene ni na automatima. Takve proizvode ne stavljajte u kategorije
  objekta.

## Objava na vašoj web stranici

Propis traži da su cjenici na vašoj web stranici, da je izmijenjen cjenik na **istoj adresi** i da je zamijenjeni
cjenik dostupan još 15 dana. Dvije mogućnosti:

**A) Poveznica na Odoo** – na web stavite poveznice na Odoo (Odoo mora biti dostupan s interneta barem za put
`/cjenik`):

| Adresa | Što vraća |
|---|---|
| `https://<vaš Odoo>/cjenik/<oznaka objekta>/roba` | trenutni cjenik robe objekta (npr. `/cjenik/01/roba`), uvijek na istoj adresi |
| `https://<vaš Odoo>/cjenik/<oznaka objekta>/usluge` | trenutni cjenik usluga objekta |
| `https://<vaš Odoo>/cjenik/<oznaka objekta>` | popis trenutnih cjenika objekta |
| `https://<vaš Odoo>/cjenik` | popis trenutnih cjenika svih objekata |
| `https://<vaš Odoo>/cjenik/arhiva` | sve verzije (arhiva) |

**B) Webhook** – svaka nova verzija šalje se na vaš web, koji je objavi sam (i čuva arhivu). Administrator na
objektu upiše **Adresu webhooka** i **Tajni ključ webhooka**; tehnički opis je u *Za programere*.

## Više objekata

- Svaki objekt (prodavaonica, salon, web shop…) ima svoje datoteke, poveznice, brojeve pohrane i bazne cijene.
  Primjer: salon (`salon`, oznaka `01`, kategorija *Usluge salona*) i web shop (`webshop`, oznaka `02`,
  kategorija *Kozmetika*).
- Isti cjenik na svim prodajnim mjestima: jedan objekt s kvačicom **Sva prodajna mjesta**
  (datoteka `…_ZA_SVA_PRODAJNA_MJESTA_…`).
- Cijene su iste u svim objektima (zadani cjenik).

## Što ako…

- **Cjenik se ne objavljuje** – na objektu **Objavi cjenik sada**; poruka kaže što nedostaje (npr. OIB tvrtke
  ili adresa).
- **Proizvod nije u cjeniku** – mora biti aktivan, s kvačicom **Prodaja** i cijenom većom od 0; ako objekt ima
  kategorije, mora biti u jednoj od njih (ili podkategoriji).
- **Nema cjenika usluga (ili robe)** – objekt nema nijedan takav proizvod; datoteka nastane kad ga dobije.
- **Akcija nije u cjeniku** – pravilo mora biti u **zadanom** cjeniku, s nazivom u **Posebni oblik prodaje**,
  razdoblje važenja mora biti počelo, a Cjenici uključeni.
- **Kriva bazna cijena ili datum** – administrator je ispravi na proizvodu (odjeljak **Javni cjenik**).
- **Objekt se zatvara** – arhivirajte ga; objavljeni cjenici ostaju javni.
- **Webhook: Greška** – razlog piše na verziji (**Verzije**); Odoo pokušava ponovno svaki sat.
- **Akcija je počela, a cjenik se nije promijenio** – jutarnju provjeru radi zakazana akcija *Javni cjenik:
  objava promjena* (*Postavke → Tehnički → Zakazane akcije*, uz način rada za programere). Ako je **Zadnji
  datum izvršenja** star, ne rade sve zakazane akcije Odoo-a, ne samo cjenik. Česti uzrok: Odoo radi bez
  workera (`workers = 0`) i baza se restartala – zakazane akcije tada mogu stati do ponovnog pokretanja Odoo-a.
  Za produkciju Odoo preporučuje `workers` ≥ 2 i praćenje (npr. upozorenje kad je zadnje izvršenje zakazanih
  akcija starije od 15 minuta). Do tada: **Objavi cjenik sada** na objektu.

## Ograničenja

- **Jedna cijena za sve objekte** (zadani cjenik): objekti s različitim cijenama istog proizvoda (npr. lanac
  u kojem svaka trgovina u blagajni ima svoj cjenik) nisu podržani.
- **Promocije iz *Popusti i vjernost*** (npr. „2+1“, popust na košaricu) su uvjeti na narudžbi, ne cijena
  proizvoda, pa se u cjeniku ne vide.
- **Odoo web trgovina sa zasebnim cjenikom za web:** objavljuju se cijene zadanog cjenika, ne cjenika web
  trgovine.
- **Najnižu cijenu u 30 dana** uz akcijsku cijenu ističete vi (modul je šalje webhookom; računa se iz cjenika
  objavljenih ovim modulom).
- **Cijene koje nisu unaprijed određene** (izrada po specifikaciji): objavite elemente cijene kao zasebne
  proizvode (sat rada, m², dolazak).
- **Neto količina i cijena za jedinicu mjere** (po kg ili l) pune se samo uz eCommerce (*Postavke → Web
  stranica → Referentna cijena proizvoda*, pa na proizvodu osnovna jedinica i količina); stupac *jedinica
  mjere* je tada ta osnovna jedinica, inače jedinica mjere proizvoda.
- **EAN barkod** je barkod proizvoda kad je ispravan EAN-13 ili EAN-8; inače je barkod samo u stupcu *barkod*.
- Datoteka je **CSV** (pravilnik dopušta i XML).

## Prijevod na hrvatski

Svi tekstovi modula (polja, gumbi, poruke, javne stranice) prevedeni su na hrvatski (`i18n/hr.po`), pojmovima
iz pravilnika (bazna cijena, prodajno mjesto, broj pohrane, posebni oblik prodaje). Prijevodi se učitavaju pri
instalaciji i nadogradnji. Ako ste hrvatski dodali nakon instalacije modula: *Postavke → Jezici* → ažurirajte
**Hrvatski**.

## Za programere

**Datoteke** (Pravilnik o načinu objave cjenika proizvoda, čl. 3 i 6): CSV, UTF-8 s BOM-om, točka sa zarezom,
decimalni zarez; za svaki objekt cjenik robe i cjenik usluga, iste strukture za sve objekte. Naziv:
`OIB_oblik_adresa_oznaka_ROBA|USLUGE_broj pohrane_GGGGMMDD_SSMM.csv`, npr.
`12345678903_servis_Vukovarska 20 Osijek_U-03_USLUGE_015_20261201_0745.csv`; za sva prodajna mjesta
`12345678903_ZA_SVA_PRODAJNA_MJESTA_ROBA_016_20261201_0745.csv`. Obrt: matični broj umjesto OIB-a. Broj
pohrane po objektu, +1 za svaku verziju (robe ili usluga).

Stupci cjenika robe, ovim redom:

| Stupac | Sadržaj |
|---|---|
| `naziv`, `sifra`, `marka` | naziv (hrvatski ako je uključen), interna oznaka, marka |
| `neto_kolicina`, `jedinica_mjere` | osnovna količina i jedinica (eCommerce), inače prazno i jedinica mjere proizvoda |
| `maloprodajna_cijena_eur`, `posebni_oblik_prodaje` | cijena za potrošača s PDV-om; `da` (akcija) ili `ne` |
| `cijena_za_jedinicu_mjere_eur` | cijena po osnovnoj jedinici (eCommerce) |
| `barkod`, `ean_barkod` | barkod; isti barkod ako je ispravan EAN-13/EAN-8 |
| `bazna_cijena_eur` | bazna cijena objekta |

Stupci cjenika usluga: `naziv`, `maloprodajna_cijena_eur`, `posebni_oblik_prodaje`, `bazna_cijena_eur`.

**Webhook:** `POST` s JSON tijelom na adresu objekta, za svaku novu verziju, redom od najstarije neposlane:

```json
{
  "event": "price_list.published",
  "company": "Primjer d.o.o.",
  "company_vat": "HR12345678903",
  "premises": "servis_Vukovarska 20 Osijek_U-03",
  "premises_label": "U-03",
  "kind": "services",
  "number": 15,
  "file_name": "12345678903_servis_Vukovarska 20 Osijek_U-03_USLUGE_015_20261201_0745.csv",
  "published_at": "2026-12-01T07:45:00+01:00",
  "url": "https://odoo.example.com/cjenik/12345678903_servis_Vukovarska%2020%20Osijek_U-03_USLUGE_015_20261201_0745.csv",
  "current_url": "https://odoo.example.com/cjenik/U-03/usluge",
  "content_type": "text/csv; charset=utf-8",
  "content_base64": "77u/bmF6aXY7...",
  "rows": [
    {"naziv": "Servis", "sifra": "U-1", "maloprodajna_cijena_eur": "125,00", "posebni_oblik_prodaje": "ne",
     "bazna_cijena_eur": "125,00", "naziv_posebnog_oblika_prodaje": "", "datum_bazne_cijene": "10.09.2026",
     "prodajna_cijena_bez_pdv_eur": "100,00"}
  ]
}
```

- `kind` je `goods` (roba) ili `services` (usluge). `content_base64` je propisana datoteka (objavite je takvu
  kakva jest, trenutnu uvijek na istoj adresi). `rows` su njezini retci za prikaz na webu, uz `sifra` (i za
  usluge), `naziv_posebnog_oblika_prodaje`, `datum_bazne_cijene`, `prodajna_cijena_bez_pdv_eur` (redovna cijena
  bez PDV-a, npr. za tvrtke), a za vrijeme akcije i `cijena_prije_posebnog_oblika_prodaje_eur` i
  `najniza_cijena_30_dana_eur`.

Redak u `rows` cjenika robe za vrijeme akcije (primjer iz poglavlja *Akcije*):

```json
{
  "naziv": "Stolna svjetiljka",
  "sifra": "ART-1",
  "marka": "Primjer",
  "neto_kolicina": "",
  "jedinica_mjere": "kom",
  "maloprodajna_cijena_eur": "40,00",
  "posebni_oblik_prodaje": "da",
  "cijena_za_jedinicu_mjere_eur": "",
  "barkod": "",
  "ean_barkod": "",
  "bazna_cijena_eur": "50,00",
  "naziv_posebnog_oblika_prodaje": "Zimsko sniženje",
  "datum_bazne_cijene": "10.09.2026",
  "prodajna_cijena_bez_pdv_eur": "40,00",
  "cijena_prije_posebnog_oblika_prodaje_eur": "50,00",
  "najniza_cijena_30_dana_eur": "50,00"
}
```

Na webu uz akcijsku cijenu (40,00 €) prikažite najnižu cijenu u 30 dana prije akcije (50,00 €) i baznu cijenu,
npr. „Zimsko sniženje: 40,00 € · najniža cijena u 30 dana prije akcije: 50,00 € · bazna cijena: 50,00 €“.
- Uz tajni ključ zaglavlje `X-Price-List-Signature: sha256=<HMAC-SHA256 tijela>`; web ga mora provjeriti.
- Odgovor 2xx = primljeno (*Webhook: Poslano*); preusmjeravanja se ne slijede. Kod greške Odoo pokušava ponovno
  za sat vremena. Kad se webhook upiše naknadno, šalju se trenutne verzije. Web mora sam čuvati i objaviti
  zamijenjene verzije najmanje 15 dana nakon zamjene.

**Kod:**

- Ovisi samo o `account`; eCommerce (`base_unit_id`, `base_unit_count`) koristi ako je instaliran.
- Modeli: `l10n_hr.price.list.location` (objekt), `l10n_hr.price.list.version` (verzija: `kind` roba/usluge,
  broj pohrane, datoteka kao privitak, `checksum`, `rows_json`, stanje webhooka; verzije prije 19.0.2.10.0
  nemaju `kind` i imaju robu i usluge zajedno), `l10n_hr.price.list.anchor` (bazna cijena po objektu i
  varijanti; mijenja je samo `base.group_system`). Predložak proizvoda: `price_list_brand`,
  `price_list_anchor_ids`. Pravilo cjenika: `price_list_special_sale`. Tvrtka: `price_list_natural_person`.
- Cijena: `_default_pricelist()` (`_get_country_pricelist_multi` za državu tvrtke; ništa kad su Cjenici
  isključeni) i `_compute_price_rule`; pravilo s nazivom = `da`. Redovna cijena (bazna cijena proizvoda
  objavljenog prvi put za vrijeme akcije, `prodajna_cijena_bez_pdv_eur`) = isti cjenik bez pravila s nazivom
  (kontekst `l10n_hr_price_list_regular_price` u `_get_applicable_rules`). Cijena prije akcije i najniža cijena
  (`_special_sale_prices`) iz `rows_json` verzija iste vrste i starijih zajedničkih (retci spremaju
  `_product_id`, koji se ne objavljuje i nije u `checksum`; starije verzije po šifri).
- Objava (`_publish`): nova verzija robe ili usluga kad se promijeni SHA-256 njezinih redaka (uključujući
  vrijednosti webhooka) ili OIB-a i prodajnog mjesta; cjenik nastaje kad ima redaka, a poslije se objavljuje i
  prazan. Cron *Javni cjenik: objava promjena* svaki dan u 04:00 UTC (početak i kraj pravila s razdobljem);
  promjene proizvoda, kategorija, objekata, tvrtke, baznih cijena, cjenika i pravila zakažu ga za minutu
  (jednom po transakciji), neuspjeli webhook za sat vremena. Verzije se spremaju prije slanja webhooka.
- Proširenja na objektu: `_row(product, price, anchor, special_sale)`, `_kind`, `_default_pricelist`, `_prices`,
  `_products`.
- Testovi: `--test-tags /l10n_hr_price_list`.
