# MVP Datovy Model a API

Tento dokument popisuje nejjednodussi pouzitelnou backendovou kostru pro prvni verzi produktu FotoNabidka.

Cil:

- vedet, jaka data budeme ukladat
- vedet, jak spolu budou souviset
- vedet, jake endpointy budeme potrebovat pro prvni funkcni tok

Prvni funkcni tok:

`zalozit projekt -> nahrat fotky -> spustit analyzu -> zobrazit vysledek -> upravit a nacenit`

## 1. Co patri do MVP

Do prvni verze budeme resit jen tyto oblasti:

- firma a uzivatele
- projekt
- fotografie projektu
- AI analyza
- cenove varianty
- firemni cenik materialu a reference dodavatelu

Nebudeme zatim resit:

- plnohodnotny CRM modul
- slozite workflow schvalovani
- fakturaci
- dashboardy
- pokrocile integrace

## 2. Hlavni entity

## 2.1 Organization

Predstavuje firmu, ktera system pouziva.

Hlavni pole:

- `id`
- `name`
- `ico`
- `email`
- `phone`
- `default_currency`
- `created_at`
- `updated_at`

Poznamka:

Jedna firma muze mit vice uzivatelu, projektu a cenovych nastaveni.

## 2.2 User

Uzivatel prihlaseny do systemu.

Hlavni pole:

- `id`
- `organization_id`
- `email`
- `password_hash`
- `full_name`
- `role`
- `is_active`
- `created_at`
- `updated_at`

Doporucene role pro MVP:

- `admin`
- `manager`
- `field_worker`

## 2.3 Client

Klient, pro ktereho se nabidka vytvari.

Hlavni pole:

- `id`
- `organization_id`
- `full_name`
- `company_name`
- `email`
- `phone`
- `notes`
- `created_at`
- `updated_at`

Poznamka:

Pro prvni verzi muze byt klient velmi jednoduchy. Nechceme hned stavet rozsahle CRM.

## 2.4 Project

Zakladni obchodni jednotka systemu.

Jeden projekt reprezentuje jednu poptavku nebo jednu pripravovanou nabidku.

Hlavni pole:

- `id`
- `organization_id`
- `client_id`
- `created_by_user_id`
- `title`
- `description`
- `status`
- `property_type`
- `repair_scope`
- `location_lat`
- `location_lng`
- `address_label`
- `created_at`
- `updated_at`

Navrh stavu projektu:

- `draft`
- `uploaded`
- `processing`
- `analysed`
- `quoted`
- `sent`

Poznamka:

- `property_type` bude zatim predvyplneny AI nebo uzivatelem
- `repair_scope` znamena napriklad `cleaning`, `local_repair`, `full_reconstruction`

## 2.5 ProjectPhoto

Fotografie navazane na projekt.

Hlavni pole:

- `id`
- `project_id`
- `storage_key`
- `preview_storage_key`
- `ai_input_storage_key`
- `original_filename`
- `mime_type`
- `file_size`
- `width`
- `height`
- `preview_file_size`
- `preview_width`
- `preview_height`
- `ai_input_file_size`
- `ai_input_width`
- `ai_input_height`
- `processing_status`
- `taken_at`
- `exif_lat`
- `exif_lng`
- `sort_order`
- `created_at`

Poznamka:

Fotky budou fyzicky ulozene v object storage, v databazi budeme drzet metadata a odkaz na ulozeny soubor.
Pro kazdou fotku chceme drzet tri varianty:

- `original` pro archiv a pripadne prepocty
- `preview` pro rychle zobrazeni v UI
- `ai_input` pro levnejsi a rychlejsi AI zpracovani

## 2.6 AnalysisJob

Zaznam o tom, ze byla spustena nebo probiha AI analyza.

Hlavni pole:

- `id`
- `project_id`
- `status`
- `job_type`
- `requested_by_user_id`
- `started_at`
- `finished_at`
- `error_message`
- `created_at`

Navrh stavu:

- `queued`
- `running`
- `completed`
- `failed`

Poznamka:

Tato entita je dulezita pro fronty a pozdejsi asynchronni zpracovani.

## 2.7 AnalysisResult

Vysledek AI analyzy k projektu.

Hlavni pole:

- `id`
- `project_id`
- `analysis_job_id`
- `object_type`
- `surface_condition`
- `recommended_scope`
- `estimated_area_sqm`
- `area_confidence`
- `mask_polygon_json`
- `materials_suggestion_json`
- `workflow_suggestion_json`
- `model_name`
- `model_version`
- `created_at`

Poznamka:

- `mask_polygon_json` ulozi oblast urcenou AI
- `materials_suggestion_json` a `workflow_suggestion_json` nechame v MVP jako JSON

## 2.8 PricingProfile

Nastaveni firmy pro vypocet cen.

Hlavni pole:

- `id`
- `organization_id`
- `name`
- `hourly_rate`
- `daily_rate`
- `margin_economy_pct`
- `margin_standard_pct`
- `margin_premium_pct`
- `vat_pct`
- `currency`
- `is_default`
- `created_at`
- `updated_at`

Poznamka:

Firma muze mit vice profilu, ale pro MVP bude aktivni vzdy jeden vychozi profil.

## 2.9 MaterialCatalog

Interni firemni katalog materialu.

Hlavni pole:

- `id`
- `organization_id`
- `name`
- `category`
- `unit`
- `default_unit_price`
- `default_supplier_id`
- `is_active`
- `notes`
- `created_at`
- `updated_at`

Poznamka:

Tady bude firma drzet vlastni "pravdu" o tom, jake materialy pouziva a jaka je jeji vychozi cena.

## 2.10 Supplier

Seznam dodavatelu nebo stavebnich obchodu, ze kterych lze brat referencni ceny.

Hlavni pole:

- `id`
- `organization_id`
- `name`
- `code`
- `website_url`
- `integration_type`
- `is_active`
- `contact_name`
- `contact_email`
- `created_at`
- `updated_at`

Poznamka:

Pro MVP muze byt `integration_type` jen `manual`, pozdeji `csv_import` nebo `api`.

## 2.11 SupplierMaterialPrice

Referencni cena konkretniho materialu od konkretniho dodavatele.

Hlavni pole:

- `id`
- `material_catalog_id`
- `supplier_id`
- `supplier_product_name`
- `supplier_sku`
- `unit`
- `unit_price`
- `currency`
- `availability_status`
- `source_type`
- `source_url`
- `valid_from`
- `valid_to`
- `last_seen_at`
- `created_at`
- `updated_at`

Poznamka:

Tyto ceny slouzi jako reference. Finalni cena v nabidce muze byt jina podle firmy nebo kalkulanta.

## 2.12 QuoteVariant

Jedna cenova varianta pro projekt.

Hlavni pole:

- `id`
- `project_id`
- `analysis_result_id`
- `pricing_profile_id`
- `variant_type`
- `labor_cost`
- `material_cost`
- `other_cost`
- `margin_pct`
- `total_ex_vat`
- `vat_amount`
- `total_inc_vat`
- `created_at`
- `updated_at`

Varianty pro MVP:

- `economy`
- `standard`
- `premium`

## 2.13 QuoteItem

Jednotlive polozky uvnitr cenove varianty.

Hlavni pole:

- `id`
- `quote_variant_id`
- `item_type`
- `name`
- `description`
- `quantity`
- `unit`
- `unit_price`
- `total_price`
- `material_catalog_id`
- `supplier_id`
- `price_source`
- `is_manual_override`
- `ai_suggested_unit_price`
- `supplier_reference_unit_price`
- `company_default_unit_price`
- `sort_order`
- `created_at`
- `updated_at`

Typy polozek:

- `labor`
- `material`
- `transport`
- `other`

Poznamka:

Tohle je dulezity zaklad pro budouci workflow:

- AI navrhne material a mnozstvi
- system si muze pamatovat referencni cenu od dodavatele
- firma ma vlastni katalogovou cenu
- kalkulant muze polozku rucne prepsat

## 3. Vazby mezi entitami

Jednoduse receno:

- jedna `organization` ma vice `users`
- jedna `organization` ma vice `clients`
- jedna `organization` ma vice `projects`
- jedna `organization` ma vice `material_catalog` polozek
- jedna `organization` ma vice `suppliers`
- jeden `project` ma vice `project_photos`
- jeden `project` muze mit vice `analysis_jobs`
- jeden `project` muze mit vice `analysis_results`
- jeden `project` ma vice `quote_variants`
- jedna `quote_variant` ma vice `quote_items`
- jeden `material_catalog` muze mit vice `supplier_material_prices`

Prakticky pro MVP budeme vetsi cast logiky brat takto:

- projekt ma jednu aktualni AI analyzu
- projekt ma tri aktualni cenove varianty

## 4. Minimalni databazove tabulky pro prvni implementaci

Pokud bychom to chteli osekat na nejnutnejsi minimum, prvni verze backendu potrebuje:

- `organizations`
- `users`
- `clients`
- `projects`
- `project_photos`
- `analysis_jobs`
- `analysis_results`
- `pricing_profiles`
- `material_catalog`
- `suppliers`
- `supplier_material_prices`
- `quote_variants`
- `quote_items`

## 5. API pro prvni verzi

API budeme drzet jednoduche a citelne.

## 5.1 Auth

### `POST /auth/login`

Pouziti:

- prihlaseni uzivatele

Request:

```json
{
  "email": "user@firma.cz",
  "password": "tajneheslo"
}
```

Response:

```json
{
  "accessToken": "jwt-token",
  "user": {
    "id": "usr_123",
    "fullName": "Jan Novak",
    "role": "manager",
    "organizationId": "org_123"
  }
}
```

### `GET /auth/me`

Pouziti:

- zjisteni, kdo je aktualne prihlasen

## 5.2 Projects

### `GET /projects`

Pouziti:

- seznam projektu pro kancelarsky web

Priklady query parametru:

- `status`
- `search`
- `page`
- `limit`

### `POST /projects`

Pouziti:

- zalozeni noveho projektu z mobilu nebo z kancelare

Request:

```json
{
  "title": "Fasada domu Novak",
  "description": "Znecistena severni stena a lokalni praskliny",
  "clientId": "cli_123",
  "locationLat": 50.087,
  "locationLng": 14.421
}
```

Response:

```json
{
  "id": "prj_123",
  "status": "draft"
}
```

### `GET /projects/:projectId`

Pouziti:

- detail projektu

Vraci:

- zakladni data projektu
- klienta
- fotky
- posledni analyzu
- cenove varianty

### `PATCH /projects/:projectId`

Pouziti:

- uprava nazvu, popisu, klienta, stavu a dalsich editovatelnych poli

## 5.3 Photos

### `POST /projects/:projectId/photos`

Pouziti:

- upload jedne nebo vice fotografii

Format:

- `multipart/form-data`

Pole:

- `files[]`
- volitelne `takenAt`
- volitelne `sortOrder`

Response:

```json
{
  "uploaded": [
    {
      "id": "pho_123",
      "storageKey": "projects/prj_123/photo_1.jpg",
      "processingStatus": "ready",
      "variants": {
        "preview": {
          "storageKey": "projects/prj_123/preview/photo_1.jpg"
        },
        "aiInput": {
          "storageKey": "projects/prj_123/ai/photo_1.jpg"
        }
      }
    }
  ]
}
```

### `GET /projects/:projectId/photos`

Pouziti:

- seznam fotek k projektu

### `DELETE /projects/:projectId/photos/:photoId`

Pouziti:

- smazani fotky z projektu

Poznamka:

V praxi doporucuji radeji soft delete nebo skryti, ne tvrde mazani hned od zacatku.

## 5.4 Analysis

### `POST /projects/:projectId/analysis`

Pouziti:

- rucni spusteni AI analyzy

Response:

```json
{
  "jobId": "job_123",
  "status": "queued"
}
```

### `GET /projects/:projectId/analysis`

Pouziti:

- vraci posledni dostupny vysledek analyzy

### `GET /analysis-jobs/:jobId`

Pouziti:

- zjisteni stavu konkretni AI ulohy

Response:

```json
{
  "id": "job_123",
  "status": "running"
}
```

## 5.5 Quote variants

### `POST /projects/:projectId/quote-variants/recalculate`

Pouziti:

- prepocet tri cenovych variant po analyzach nebo po editaci projektu

Response:

```json
{
  "variants": [
    {
      "variantType": "economy",
      "totalIncVat": 51200
    },
    {
      "variantType": "standard",
      "totalIncVat": 64800
    },
    {
      "variantType": "premium",
      "totalIncVat": 82900
    }
  ]
}
```

### `GET /projects/:projectId/quote-variants`

Pouziti:

- nacteni aktualnich cenovych variant

### `PATCH /quote-variants/:variantId`

Pouziti:

- rucni uprava varianty v kancelarskem rozhrani

## 6. Doporuceny detail projektu pro frontend

Pro kancelarsky frontend je nejprijemnejsi, kdyz detail projektu vrati vse pohromade.

Priklad odpovedi:

```json
{
  "id": "prj_123",
  "title": "Fasada domu Novak",
  "status": "analysed",
  "description": "Znecistena severni stena a lokalni praskliny",
  "client": {
    "id": "cli_123",
    "fullName": "Petr Novak",
    "email": "petr@novak.cz"
  },
  "location": {
    "lat": 50.087,
    "lng": 14.421,
    "addressLabel": "Praha 1"
  },
  "photos": [
    {
      "id": "pho_123",
      "url": "signed-url"
    }
  ],
  "latestAnalysis": {
    "objectType": "facade",
    "surfaceCondition": "damaged",
    "recommendedScope": "local_repair",
    "estimatedAreaSqm": 42.5,
    "areaConfidence": 0.71
  },
  "quoteVariants": [
    {
      "id": "qv_1",
      "variantType": "economy",
      "totalIncVat": 51200
    }
  ]
}
```

## 7. Pravidla pro prvni implementaci

Pri implementaci doporucuji drzet tyto zasady:

- backend ma byt jednoduchy a citelny
- AI analyza je asynchronni
- cenove varianty se pocitaji serverove
- frontend nikdy nema pocitat finalni cenu sam
- soubory jdou do object storage, ne primo do databaze
- polygon a AI doporuceni mohou byt v MVP ulozene jako JSON

## 8. Co bude nasledovat po tomto dokumentu

Po schvaleni tohoto navrhu budou dalsi logicke kroky:

1. Navrhnout fyzickou strukturu backendu.
2. Vybrat ORM a pripravit databazove schema.
3. Zavest prvni endpointy pro `projects` a `photos`.
4. Napojit kancelarsky frontend na nova data.

Tento dokument je zamerne jednoduchy. Ma byt opora pro dalsi krok, ne konecna enterprise specifikace.
