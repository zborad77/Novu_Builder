# AI Vision Module

Tento modul pripravuje backend na pozdejsi napojeni skutecne vision AI bez bourani stavajici aplikace.

## Aktualni stav

- API route pro analyzu uz negeneruje vysledek natvrdo sama.
- Route vola samostatnou vrstvu `server/ai/analysisService.js`.
- Aktivni provider se ridi promennou `AI_ANALYSIS_PROVIDER`.
- Aktualne je hotovy provider `mock`.
- Provider `openai` je pripraveny jako integracni bod, ale zatim zamerne vraci chybu `not implemented`.

## Vstup do analyzy

Sluzba dostava:

- `project`
- `photos`

To znamena, ze pozdeji pujde do provideru predat:

- metadata projektu
- seznam realnych fotek
- GPS / adresu
- pripadne rucni popis od technika

## Ocekavany vystup provideru

Kazdy provider ma vratit jednotny objekt:

- `providerKey`
- `jobType`
- `objectType`
- `surfaceCondition`
- `recommendedScope`
- `estimatedAreaSqm`
- `areaConfidence`
- `maskPolygon`
- `materials`
- `workflow`
- `modelName`
- `modelVersion`

Na tento format je uz napojena persistence do `analysis_jobs` a `analysis_results`.

## Dalsi krok pro realne AI

Az budeme zapojovat skutecny vision model, udelame:

1. nahravani realnych obrazku do storage
2. predani URL nebo binary vstupu provideru
3. implementaci `openaiVisionProvider`
4. pripadne druhy CV provider pro segmentaci / masku

## Proc je to dobre

- backend route zustava jednoducha
- AI logika je oddelena od databaze
- provider se da menit bez zasahu do UI
- muzeme mit `mock`, `openai` i dalsi vision provider vedle sebe
