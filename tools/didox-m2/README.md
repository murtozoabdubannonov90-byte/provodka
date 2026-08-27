# SOLIDUM — M-2 ishonchnoma quvuri (Didox)

DSKEYS sertifikatini o'qiydi, oxirgi ishonchnomadan ishonchli shaxs
ma'lumotlarini oladi va yangi M-2 ishonchnomani **Didox orqali** yuboradi.
Word fayl yaratmaydi.

## O'rnatish (bir marta)

```bat
cd tools\didox-m2
pip install -r requirements.txt
copy config.example.json config.json
notepad config.json
```

`config.json` da to'ldiriladigan joylar:

| Kalit | Ma'nosi |
|---|---|
| `keys_dir` | DSKEYS papkasi, masalan `E:\\DSKEYS` |
| `docs_dir` | Ishonchnomalar papkasi |
| `keys_md` | `kalitlar.md` qayerga yozilsin |
| `didox.base_url` | `https://api-partners.didox.uz` (test: `https://testapi3.didox.uz`) |
| `didox.token` | Didox partner token (akkaunt menejeridan olinadi) |
| `didox.endpoints` | Aniq yo'llar — api-docs.didox.uz dan tekshiring |

> `config.json`, `state.json` va `templates/*.json` git'ga tushmaydi —
> ular ichida tashkilot ma'lumotlari bo'ladi.

## Kunlik ishlatish

```bat
run.bat
```

yoki qadam-baqadam:

```bat
python run.py keys                       ::  1. sertifikat -> kalitlar.md
python run.py last                       ::  2. oxirgi ishonchnoma -> ishonchli shaxs
python run.py fetch-sample --id <DOC_ID> ::  3. Didox'dan namuna (bir marta)
python run.py build                      ::  4. yangi M-2 (yuborilmaydi)
python run.py send --confirm --sign      ::  5. yuborish va imzolash
```

## Bosqichlar haqida

**1. `keys`** — avval E-IMZO ilovasining lokal API'siga ulanadi
(`ws://127.0.0.1:64646`), u ishlamasa `keys_dir` papkasini skanerlaydi.
STIR bo'yicha filtrlab, `kalitlar.md` ga faqat quyidagilarni yozadi:
F.I.Sh., berilgan sana, tugash sanasi, fayl nomi, to'liq yo'l.
**Parol so'ralmaydi va hech qayerga yozilmaydi.**

**2. `last`** — `docs_dir` ichidan eng oxirgi ishonchnomani topadi
(`.docx`, `.xlsx`, `.pdf`, `.txt`, `.json`), ishonchli shaxsning
F.I.Sh., lavozimi va pasport seriya-raqamini **o'zgartirmasdan** oladi,
oldingi hujjat raqamini aniqlab keyingisini hisoblaydi. Natija
`state.json` da saqlanadi. Biror maydon avtomatik topilmasa, shu faylda
qo'lda to'g'rilash mumkin.

**3. `fetch-sample`** — Didox JSON sxemasi taxmin qilinmaydi. Sizning
akkauntingizdagi haqiqiy ishonchnoma yuklab olinib
`templates/doverennost.sample.json` ga saqlanadi, undan
`templates/field_map.json` (maydon -> JSON yo'l xaritasi) avtomatik
yasaladi. Xarita eski hujjatdagi qiymatlarni qidirish orqali quriladi,
topilmagani kalit nomlari bo'yicha taxmin qilinadi va ekranda `!!`
belgisi bilan ko'rsatiladi — ularni qo'lda to'g'rilash kerak.

Token hali yo'q bo'lsa: eski ishonchnomani Didox veb-interfeysidan JSON
qilib eksport qiling va `python run.py remap --file <fayl.json>` deng.

**4. `build`** — namunadan nusxa olib, faqat xaritadagi maydonlarni
almashtiradi: beruvchi (STIR 312386763), oluvchi (STIR 304390390),
tovar, bugungi sana, +30 kun muddat, raqam = oldingisi + 1. Ishonchli
shaxs maydonlari eski hujjatdagidek qoladi. Sana formati namunadagiga
moslashtiriladi. Hujjat `out_dir` ga yoziladi va ekranda ko'rsatiladi —
**yuborilmaydi**.

**5. `send`** — `--confirm` bo'lmasa faqat ko'rsatadi. `--dry-run` bilan
so'rov tanasini yubormasdan ko'rish mumkin. `--sign` qo'shilsa, E-IMZO
orqali PKCS#7 imzo yasaladi; **parolni E-IMZO ilovasining o'z oynasi
so'raydi**, bu skript parolni ko'rmaydi.

## Tekshirilmagan joylar

Quvur Linux'da sun'iy ma'lumotlar bilan uchdan-uchgacha sinovdan
o'tkazildi. Sizning muhitingizda tekshirilishi kerak:

- E-IMZO lokal API javob formati (ilova ishga tushirilgan holda);
- Didox endpoint yo'llari va so'rov/javob sxemasi — `didox.endpoints`
  ni api-docs.didox.uz bo'yicha solishtiring;
- imzo yuborish formati (`{"sign": <pkcs7_base64>}`) — Didox
  hujjatlarida boshqacha bo'lishi mumkin.

Har uchalasi ham `config.json` va `didox.py` orqali o'zgartiriladi,
qolgan kodga tegmaydi.
