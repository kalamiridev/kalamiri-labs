{
    "name": "Croatia - Public Price List for Consumers",
    "version": "19.0.2.10.0",
    "category": "Accounting/Localizations",
    "summary": "Machine-readable price lists of goods and services (CSV) with the base price, as required by NN 132/26",
    "description": """
Croatian traders that sell to consumers and have a website must publish their price
lists in machine-readable files and show the base price next to every price (Consumer
Protection Act; Pravilnik o isticanju bazne cijene proizvoda and Pravilnik o načinu
objave cjenika proizvoda, NN 132/26, from 17 November 2026).

* price lists per premises (shop, office, web shop…) or one for all premises, each with its
  own product categories (subcategories included; none: all sellable products), webhook and
  storage numbers; goods and services in separate files with the prescribed columns and
  file names (OIB, premises, ROBA/USLUGE, storage number, time),
* consumer price as on a quotation for a customer without a pricelist of their own: the default
  pricelist of the company (or the sales price), with the taxes of the product,
* special sales are pricelist rules (discount, period) with the name of the special sale; the
  price before the sale and the lowest price in the 30 days before it (from the published price
  lists) are sent on the webhook,
* base price and its date saved per premises at the first publication of the product;
  later price changes do not change it,
* a new version a minute after a change and, for rules with a period, every morning;
  replaced versions stay public,
* public pages without login: /cjenik, /cjenik/<premises label>/roba and /usluge (the
  current file, always on the same link), /cjenik/arhiva (all versions),
* optional webhook: every new version is sent to your website (JSON, HMAC-SHA256 signature).
""",
    "author": "Kalamiri d.o.o.",
    "website": "https://kalamiri.hr",
    "maintainer": "Kalamiri d.o.o.",
    "support": "info@kalamiri.com",
    "images": ["static/description/banner.png"],
    "license": "AGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir_cron.xml",
        "views/price_list_version_views.xml",
        "views/price_list_location_views.xml",
        "views/product_views.xml",
        "views/res_config_settings_views.xml",
        "views/product_pricelist_views.xml",
    ],
    "installable": True,
    "application": False,
}
