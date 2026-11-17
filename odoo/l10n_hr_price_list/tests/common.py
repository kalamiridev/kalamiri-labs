import base64
import csv
import io
import json

from odoo import Command

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.l10n_hr_price_list.models.price_list_version import COLUMNS, GOODS, SERVICES


class PriceListCommon(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The same results whatever languages the database has (names and messages).
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.company = cls.company_data["company"].with_env(cls.env)
        cls.company.partner_id.lang = "en_US"
        cls.company.write({"street": "Vukovarska 20", "city": "Osijek", "vat": "HR69114397826"})
        cls.tax_25 = cls.env["account.tax"].create({
            "name": "PDV 25%",
            "amount": 25.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "company_id": cls.company.id,
        })
        cls.tax_25_included = cls.env["account.tax"].create({
            "name": "PDV 25% (included)",
            "amount": 25.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "price_include_override": "tax_included",
            "company_id": cls.company.id,
        })
        cls.category = cls.env["product.category"].create({"name": "Published"})
        cls.subcategory = cls.env["product.category"].create({"name": "Sub", "parent_id": cls.category.id})
        cls.other_category = cls.env["product.category"].create({"name": "Not published"})
        cls.location = cls.env["l10n_hr.price.list.location"].create({
            "company_id": cls.company.id,
            "object_type": "servis",
            "object_code": "U-03",
            "category_ids": [Command.set(cls.category.ids)],
        })
        cls.service = cls._product("SRV-1", "Setup", 100.0, cls.tax_25, type="service")
        cls.goods = cls._product("GDS-1", "Sensor", 125.0, cls.tax_25_included, categ=cls.subcategory,
                                 barcode="3850000000008", price_list_brand="Acme")
        cls.hidden = cls._product("HID-1", "Internal", 10.0, cls.tax_25, categ=cls.other_category)
        cls.Version = cls.env["l10n_hr.price.list.version"]
        cls.Anchor = cls.env["l10n_hr.price.list.anchor"]

    @classmethod
    def _product(cls, code, name, price, tax, categ=None, type="consu", **values):
        return cls.env["product.product"].create({
            "default_code": code,
            "name": name,
            "type": type,
            "list_price": price,
            "taxes_id": [Command.set(tax.ids)],
            "categ_id": (categ or cls.category).id,
            **values,
        })

    def _lines(self, versions):
        """{name: line} of the files of the versions (a services file has no code)."""
        lines = {}
        for version in versions:
            content = base64.b64decode(version.file)
            self.assertTrue(content.startswith(b"\xef\xbb\xbf"), "UTF-8 with BOM")
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), delimiter=";")
            self.assertEqual(reader.fieldnames, COLUMNS[version.kind], "The prescribed columns in their order")
            lines.update({row["naziv"]: row for row in reader})
        return lines

    def _rows(self, versions):
        """{code: row} saved with the versions (also sent on the webhook)."""
        return {row["sifra"]: row for version in versions for row in json.loads(version.rows_json)}

    def _goods(self, versions):
        return versions.filtered(lambda version: version.kind == GOODS)

    def _services(self, versions):
        return versions.filtered(lambda version: version.kind == SERVICES)

    def _anchor(self, product, location=None):
        return self.Anchor.search([("product_id", "=", product.id), ("location_id", "=", (location or self.location).id)])
