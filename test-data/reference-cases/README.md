# Reference Cases Dataset

Tento maly dataset slouzi jako prvni rucne kuratorovany zaklad pro `Novu_Builder`.

Zdroj:
- lokalni repo `D:\Git\GitHub_Desktop\ZBORADWEB_v002`

Ucel:
- overeni vyberu `primary photo`
- overeni vyberu `analysis reference photo`
- prvni validace serveroveho navrhu zakazky
- zaklad pro budouci seed/import do backendu

Pravidla teto prvni verze:
- dataset je maly a rucne vybrany
- kazdy case ma 3 az 5 fotek
- u kazde fotky je uvedeno, zda ma byt ocekavane hlavni nebo referencni pro analyzu
- manifesty jsou zatim rucne psane, bez automatickeho parseru webu

Struktura:
- jeden adresar = jedna testovaci zakazka
- `manifest.json` = metadata a ocekavani
- `foto_*.jpg` = zdrojove referencni fotky

Pozdeji:
- automaticky import z `ZBORADWEB_v002`
- vice kategorii a edge cases
- benchmark nad vyberem referencni fotky
