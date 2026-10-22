"""Neutral demo data for the Apps Store screenshots of l10n_hr_price_list (never a real company).

In a throwaway database with sale_management, stock and l10n_hr_price_list installed:

    SHOTS_PASSWORD=... odoo shell -d shots < demo_price_list.py

Then serve the database alone (e.g. --http-port=8070 --max-cron-threads=0), log in as admin with
SHOTS_PASSWORD and run screenshots.py; drop the database afterwards.
"""
import datetime
import os

company = env.company
eur = env.ref("base.EUR")
eur.active = True
company.write({
    "name": "Primjer d.o.o.",
    "street": "Trg primjera 1",
    "zip": "10000",
    "city": "Zagreb",
    "country_id": env.ref("base.hr").id,
    "email": "info@primjer.example",
    "currency_id": eur.id,
})
env.ref("base.user_admin").write({"name": "Ana Primjer", "tz": "Europe/Zagreb", "password": os.environ["SHOTS_PASSWORD"]})
env["ir.config_parameter"].set_param("web.base.url", "https://odoo.example.com")
env["ir.config_parameter"].set_param("web.base.url.freeze", "True")
env["res.config.settings"].create({"group_product_pricelist": True}).execute()

tax = env["account.tax"].create({"name": "25%", "amount": 25, "amount_type": "percent", "type_tax_use": "sale"})
Categ = env["product.category"]
lighting = Categ.create({"name": "Rasvjeta"})
cosmetics = Categ.create({"name": "Kozmetika"})
services = Categ.create({"name": "Usluge"})


def product(code, name, price, categ, brand=False, kind="consu", barcode=False):
    return env["product.template"].create({
        "default_code": code, "name": name, "list_price": price, "categ_id": categ.id,
        "price_list_brand": brand, "type": kind, "is_storable": kind == "consu",
        "taxes_id": [(6, 0, tax.ids)], "sale_ok": True, "barcode": barcode,
    })


lamp = product("ART-1", "Stolna svjetiljka", 40.00, lighting, "Primjer", barcode="3850000000017")
wall = product("ART-2", "Zidna svjetiljka", 64.00, lighting, "Primjer", barcode="3850000000024")
shampoo = product("ART-3", "Šampon 250 ml", 4.72, cosmetics, "Primjer", barcode="3850000000031")
product("USL-1", "Montaža rasvjete (po satu)", 24.00, services, kind="service")

stock = env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1).lot_stock_id
for tmpl, qty in ((lamp, 12), (shampoo, 40)):
    env["stock.quant"]._update_available_quantity(tmpl.product_variant_id, stock, qty)

pricelist = env["product.pricelist"].search([("company_id", "in", (company.id, False))], limit=1)
pricelist.currency_id = eur
env["product.pricelist.item"].create({
    "pricelist_id": pricelist.id,
    "applied_on": "2_product_category",
    "categ_id": lighting.id,
    "compute_price": "percentage",
    "percent_price": 20,
    "date_start": datetime.datetime(2026, 11, 30, 23, 0),  # 1 December, Zagreb
    "date_end": datetime.datetime(2026, 12, 31, 22, 59),
    "price_list_special_sale": "Zimsko sniženje",
})

shop = env["l10n_hr.price.list.location"].create({"object_type": "prodavaonica", "object_code": "P1"})
shop.action_publish()
# Products that existed on the reference day: the additional price of 10 September 2026.
env["l10n_hr.price.list.anchor"].search([("location_id", "=", shop.id)]).write({"date": datetime.date(2026, 9, 10)})
shampoo.list_price = 4.80
shop.action_publish()
wall.list_price = 60.00
shop.action_publish()
shop.write({"webhook_url": "https://www.example.com/price-list-webhook", "webhook_secret": "example-secret-0123456789"})
# For the picture only: example.com does not receive webhooks.
shop.version_ids.write({"webhook_state": "sent", "webhook_sent_at": datetime.datetime.now()})
env.cr.commit()
print("premises", shop.id, "pricelist", pricelist.id, "product", lamp.id)
