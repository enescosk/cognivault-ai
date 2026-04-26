# External Intent Training Guide

The external resolver needs two kinds of data:

## 1. Entity Lexicon

Use this when a user names a company/place.

Required fields:

- `canonical_name`: official display name
- `aliases`: common user spellings
- `type`: `hospital`, `bank`, `gym`, `consultancy`, `clinic`, etc.
- `locations`: district/city hints
- `official_url`: official source URL
- `phone`: public official phone
- `address`: public official address
- `services`: searchable services/branches, such as `MR`, `Radyoloji`, `Göz Hastalıkları`

Example:

```json
{
  "canonical_name": "Medistate Çekmeköy Hastanesi",
  "aliases": ["medistate", "medistate çekmeköy", "özel medistate çekmeköy hastanesi"],
  "type": "hospital",
  "locations": ["Çekmeköy", "İstanbul"],
  "official_url": "https://www.medistate.com.tr/hastanelerimiz/cekmekoy-hastanesi",
  "phone": "444 44 13",
  "address": "Merkez, Erenler Cd No:16, 34782 Çekmeköy / İstanbul",
  "services": ["MR", "Radyoloji", "Göz Hastalıkları", "Ağız ve Diş Sağlığı"]
}
```

## 2. Intent/Category Taxonomy

Use this when the user does not name a company and only describes a need.

Required fields:

- `category`: normalized need
- `intent`: normalized purpose
- `keywords`: words users may write
- `google_place_query_template`: query sent to Google Places

Example:

```json
{
  "category": "MR görüntüleme",
  "intent": "MR randevusu",
  "keywords": ["mr", "emar", "mr çekimi", "manyetik rezonans", "radyoloji"],
  "google_place_query_template": "{category} {location}"
}
```

## Good Training Examples

- `medistate çekmeköy mr randevusu alacaktım`
  - company: `Medistate Çekmeköy Hastanesi`
  - location: `Çekmeköy`
  - category: `MR görüntüleme`
  - purpose: `MR randevusu`

- `bostancı civarında diş doktoru randevusu istiyorum`
  - company: null
  - location: `Bostancı`
  - category: `diş doktoru`
  - purpose: `diş doktoru muayenesi`

- `ataşehir florence nightingale ile ilgili göz doktoruna muayene istiyorum`
  - company: `Ataşehir Florence Nightingale Hastanesi`
  - location: `Ataşehir`
  - category: `göz doktoru`
  - purpose: `göz doktoru muayenesi`

## Rule

Company/place is never a category. If a user writes only a need such as `diş doktoru`, store it as `category`, not `company`.
