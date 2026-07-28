# manifest.json schema

Each exported product folder contains a `manifest.json` that maps to WooCommerce fields.

## Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version (`1.0`) |
| `slug` | string | Folder-safe product identifier |
| `locale` | string | Always `he` |
| `direction` | string | Always `rtl` |
| `source_url` | string | Manufacturer page URL |
| `woocommerce` | object | WooCommerce field mapping |
| `seo` | object | Hebrew SEO metadata |
| `images` | array | WebP image metadata |
| `variants` | array | AI variant folder IDs (compare mode) |
| `primary_model` | string | Selected AI model |

## woocommerce object

```json
{
  "name": "Hebrew product title",
  "description_file": "copy/product-description.html",
  "short_description_file": "copy/short-description.txt",
  "status": "draft",
  "attributes": [{"name": "Voltage", "value": "12V"}]
}
```

## images array item

```json
{
  "file": "images/01-hero.webp",
  "alt": "Hebrew alt text",
  "format": "webp",
  "has_alpha": true,
  "needs_review": false
}
```

## WooCommerce sync

Use `POST /api/jobs/{id}/sync-woocommerce` with site credentials, or call
`app.integrations.woocommerce.sync_product_to_woocommerce()` directly.
