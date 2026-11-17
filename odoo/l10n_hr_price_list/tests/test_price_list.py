import base64
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta
from unittest.mock import patch

import requests
from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

from .common import PriceListCommon

LOGGER = "odoo.addons.l10n_hr_price_list.models"
POST = f"{LOGGER}.price_list_version.requests.post"
PREFIX = "69114397826_servis_Vukovarska 20 Osijek_U-03"


@freeze_time("2026-11-17 06:00:00")  # 07:00 in Zagreb
@tagged("post_install", "-at_install")
class TestPriceList(PriceListCommon):

    def test_first_publication(self):
        """Goods and services in separate files: the prescribed columns in their order and the prescribed
        file names (NN 132/26)."""
        versions = self.location._publish()
        goods, services = self._goods(versions), self._services(versions)
        self.assertEqual((goods.number, services.number), (1, 2))
        self.assertEqual(goods.name, f"{PREFIX}_ROBA_001_20261117_0700.csv")
        self.assertEqual(services.name, f"{PREFIX}_USLUGE_002_20261117_0700.csv")
        self.assertEqual(self.location.name, "servis_Vukovarska 20 Osijek_U-03")
        self.assertTrue(goods.is_current and services.is_current)
        self.assertEqual((goods.line_count, services.line_count), (1, 1))
        self.assertEqual(set(self._lines(versions)), {"Setup", "Sensor"}, "Subcategories in, other categories out")
        self.assertEqual(self._lines(services)["Setup"], {
            "naziv": "Setup",
            "maloprodajna_cijena_eur": "125,00",
            "posebni_oblik_prodaje": "ne",
            "bazna_cijena_eur": "125,00",
        })
        self.assertEqual(self._lines(goods)["Sensor"], {
            "naziv": "Sensor",
            "sifra": "GDS-1",
            "marka": "Acme",
            "neto_kolicina": "",
            "jedinica_mjere": self.goods.uom_id.with_context(lang=self.location._lang()).name,
            "maloprodajna_cijena_eur": "125,00",
            "posebni_oblik_prodaje": "ne",
            "cijena_za_jedinicu_mjere_eur": "",
            "barkod": "3850000000008",
            "ean_barkod": "3850000000008",
            "bazna_cijena_eur": "125,00",
        })
        row = self._rows(services)["SRV-1"]
        self.assertEqual((row["datum_bazne_cijene"], row["naziv_posebnog_oblika_prodaje"]), ("17.11.2026", ""),
                         "Not in the file, sent on the webhook")
        anchor = self._anchor(self.service)
        self.assertEqual((anchor.price, anchor.date), (125.0, date(2026, 11, 17)))
        self.assertEqual(anchor.product_tmpl_id, self.service.product_tmpl_id)
        self.assertIn(anchor, self.service.product_tmpl_id.price_list_anchor_ids)
        self.assertTrue(self.goods.product_tmpl_id.price_list_published)
        self.assertFalse(self.hidden.product_tmpl_id.price_list_published)

    def test_barcode_not_ean(self):
        self.goods.barcode = "INT-0042"
        line = self._lines(self._goods(self.location._publish()))["Sensor"]
        self.assertEqual((line["barkod"], line["ean_barkod"]), ("INT-0042", ""))

    def test_net_quantity_and_unit_price(self):
        if "base_unit_id" not in self.env["product.product"]._fields:
            self.skipTest("eCommerce is not installed")
        litre = self.env["website.base.unit"].sudo().create({"name": "l"})
        self.goods.write({"base_unit_count": 0.5, "base_unit_id": litre.id})
        line = self._lines(self._goods(self.location._publish()))["Sensor"]
        self.assertEqual((line["neto_kolicina"], line["jedinica_mjere"]), ("0,5", "l"))
        self.assertEqual(line["cijena_za_jedinicu_mjere_eur"], "250,00")

    def test_new_version_only_on_change(self):
        first = self.location._publish()
        self.assertFalse(self.location._publish(), "Nothing changed: no new version")
        with freeze_time("2026-11-18 05:30:00"):
            self.assertFalse(self.location._publish(), "Not every day: only when something changed")
            self.service.list_price = 120.0
            second = self.location._publish()
        self.assertEqual(len(second), 1, "Only the price list that changed")
        self.assertEqual(second.number, 3)
        self.assertEqual(second.name, f"{PREFIX}_USLUGE_003_20261118_0630.csv")
        self.assertTrue(second.is_current)
        self.assertFalse(self._services(first).is_current)
        self.assertTrue(self._goods(first).is_current, "The goods price list did not change")
        line = self._lines(second)["Setup"]
        self.assertEqual(line["maloprodajna_cijena_eur"], "150,00")
        self.assertEqual(line["bazna_cijena_eur"], "125,00", "The base price does not follow the price")
        self.assertEqual(self._lines(self._services(first))["Setup"]["maloprodajna_cijena_eur"], "125,00", "Old file unchanged")

    def test_kind_changes_with_product_type(self):
        self.location._publish()
        self.service.type = "consu"
        versions = self.location._publish()
        self.assertEqual(self._services(versions).line_count, 0, "A price list that had lines is published empty")
        self.assertEqual(set(self._lines(self._goods(versions))), {"Setup", "Sensor"})

    def test_new_product_gets_its_own_date(self):
        self.location._publish()
        with freeze_time("2026-12-02 06:00:00"):
            self._product("NEW-1", "New sensor", 40.0, self.tax_25)
            version = self.location._publish()
        self.assertEqual(self._lines(version)["New sensor"]["bazna_cijena_eur"], "50,00")
        rows = self._rows(version)
        self.assertEqual(rows["NEW-1"]["datum_bazne_cijene"], "02.12.2026")
        self.assertEqual(rows["GDS-1"]["datum_bazne_cijene"], "17.11.2026")

    def test_reference_day_price_by_admin(self):
        self.Anchor.create({
            "location_id": self.location.id, "product_id": self.service.id, "price": 110.0, "date": date(2026, 9, 10),
        })
        services = self._services(self.location._publish())
        self.assertEqual(self._lines(services)["Setup"]["bazna_cijena_eur"], "110,00")
        self.assertEqual(self._rows(services)["SRV-1"]["datum_bazne_cijene"], "10.09.2026")

    def test_base_price_admin_only(self):
        self.location._publish()
        user = new_test_user(
            self.env, login="price_list_seller",
            groups="base.group_user,account.group_account_manager,product.group_product_manager",
        )
        anchor = self._anchor(self.service).with_user(user)
        self.assertEqual(anchor.price, 125.0, "Everybody sees it")
        with self.assertRaises(AccessError):
            anchor.price = 1.0
        self.service.with_user(user).list_price = 90.0  # ordinary changes still work

    def test_two_premises(self):
        """Each premises: its own categories, numbers and base prices."""
        webshop = self.env["l10n_hr.price.list.location"].create({
            "company_id": self.company.id,
            "object_type": "webshop",
            "object_code": "02",
            "category_ids": [Command.set((self.category | self.other_category).ids)],
        })
        self.location._publish()
        self.service.list_price = 120.0
        self.location._publish()
        versions = webshop._publish()
        self.assertEqual(versions.mapped("number"), [1, 2], "Own storage numbers")
        self.assertEqual(self._goods(versions).name, "69114397826_webshop_Vukovarska 20 Osijek_02_ROBA_001_20261117_0700.csv")
        lines = self._lines(versions)
        self.assertEqual(set(lines), {"Setup", "Sensor", "Internal"})
        self.assertEqual(lines["Setup"]["maloprodajna_cijena_eur"], "150,00")
        self.assertEqual(lines["Setup"]["bazna_cijena_eur"], "150,00", "Own base price")
        self.assertEqual(self._lines(self.location._current_version("services"))["Setup"]["bazna_cijena_eur"], "125,00")

    def test_all_premises(self):
        self.location.write({"all_premises": True, "object_type": False})
        self.assertEqual(self.location.name, "ZA_SVA_PRODAJNA_MJESTA")
        goods = self._goods(self.location._publish())
        self.assertEqual(goods.name, "69114397826_ZA_SVA_PRODAJNA_MJESTA_ROBA_001_20261117_0700.csv")

    def test_natural_person(self):
        """A craft: the registration number instead of the OIB."""
        self.company.write({"price_list_natural_person": True, "company_registry": "97123456"})
        goods = self._goods(self.location._publish())
        self.assertEqual(goods.name, "97123456_servis_Vukovarska 20 Osijek_U-03_ROBA_001_20261117_0700.csv")
        self.company.company_registry = False
        with self.assertRaisesRegex(UserError, "Company Registry"):
            self.location._publish()

    def test_sales_price_with_taxes_and_zero_price(self):
        """Pricelists turned off: the sales price with taxes (also when a pricelist has a rule for the
        product); a product without a price is not published."""
        self.env["product.pricelist"].create({
            "name": "Consumers",
            "item_ids": [Command.create({
                "applied_on": "0_product_variant", "product_id": self.service.id,
                "compute_price": "fixed", "fixed_price": 80.0,
            })],
        })
        self._product("FREE-1", "Free", 0.0, self.tax_25)
        versions = self.location._publish()
        lines = self._lines(versions)
        self.assertEqual(lines["Setup"]["maloprodajna_cijena_eur"], "125,00")
        self.assertNotIn("Free", lines, "A product without a price is not published")
        self.assertEqual(self._rows(versions)["SRV-1"]["prodajna_cijena_bez_pdv_eur"], "100,00")

    def test_without_categories_all_sellable_products(self):
        no_category = self._product("NOC-1", "Without category", 20.0, self.tax_25, categ_id=False)
        self.service.sale_ok = False
        self.location.category_ids = False
        self.env.invalidate_all()
        self.assertTrue(no_category.price_list_published, "Shown on the product")
        self.assertFalse(self.service.price_list_published, "Not sellable")
        versions = self.location._publish()
        lines = self._lines(versions)
        self.assertLessEqual({"Sensor", "Internal", "Without category"}, set(lines), "Every category and none")
        self.assertNotIn("Setup", lines)
        self.assertEqual(lines["Without category"]["maloprodajna_cijena_eur"], "25,00")

    def _pricelist(self):
        """The pricelist of a customer without one of their own, with Pricelists turned on (Sales settings)."""
        self.env["res.config.settings"].create({"group_product_pricelist": True}).execute()
        pricelist = self.location._default_pricelist()
        self.assertTrue(pricelist, "Turning Pricelists on gives the company a pricelist")
        return pricelist

    def _sale(self, pricelist, name="Autumn sale", start=None, end=None, product=None):
        return self.env["product.pricelist.item"].create({
            "pricelist_id": pricelist.id,
            "applied_on": "0_product_variant",
            "product_id": (product or self.goods).id,
            "compute_price": "percentage",
            "percent_price": 20.0,
            "date_start": start,
            "date_end": end,
            "price_list_special_sale": name,
        })

    def _publish_on(self, day, price):
        with freeze_time(f"{day} 05:00:00"):
            self.goods.list_price = price  # tax included: the consumer price
            return self.location._publish()

    def test_default_pricelist(self):
        """Prices as on a quotation for a customer without a pricelist of their own; a rule without the
        name of a special sale is a regular price (also for the base price and the price without taxes)."""
        pricelist = self._pricelist()
        pricelist.item_ids = [Command.create({
            "applied_on": "0_product_variant", "product_id": self.service.id,
            "compute_price": "fixed", "fixed_price": 80.0,
        })]
        versions = self.location._publish()
        service = self._lines(versions)["Setup"]
        self.assertEqual(service["maloprodajna_cijena_eur"], "100,00", "Rule price with taxes")
        self.assertEqual((service["posebni_oblik_prodaje"], service["bazna_cijena_eur"]), ("ne", "100,00"))
        self.assertEqual(self._rows(versions)["SRV-1"]["prodajna_cijena_bez_pdv_eur"], "80,00", "Regular price")
        self.assertEqual(self._lines(versions)["Sensor"]["maloprodajna_cijena_eur"], "125,00", "No rule")
        pricelist.action_archive()  # as when Pricelists are turned off
        self.assertEqual(self._lines(self.location._publish())["Setup"]["maloprodajna_cijena_eur"], "125,00")

    def test_special_sale_rule(self):
        """A rule with the name of a special sale and a period: the special sale price while it runs, the
        price before it and the lowest price in the 30 days before it (also from the price list that was
        current when the 30 days began) on the webhook."""
        pricelist = self._pricelist()
        self._publish_on("2026-10-01", 105.0)  # current on 20.10., when the 30 days begin
        self._publish_on("2026-11-01", 125.0)
        self._publish_on("2026-11-10", 120.0)
        self._publish_on("2026-11-15", 125.0)
        rule = self._sale(pricelist, start=datetime(2026, 11, 19, 0, 0), end=datetime(2026, 11, 30, 22, 59))
        with freeze_time("2026-11-19 05:00:00"):
            goods = self._goods(self.location._publish())
        line = self._lines(goods)["Sensor"]
        self.assertEqual(line["maloprodajna_cijena_eur"], "100,00", "20 % off the sales price")
        self.assertEqual(line["posebni_oblik_prodaje"], "da")
        self.assertEqual(line["bazna_cijena_eur"], "105,00", "The base price does not change")
        row = self._rows(goods)["GDS-1"]
        self.assertEqual(row["naziv_posebnog_oblika_prodaje"], "Autumn sale")
        self.assertEqual(row["cijena_prije_posebnog_oblika_prodaje_eur"], "125,00")
        self.assertEqual(row["najniza_cijena_30_dana_eur"], "105,00")
        self.assertNotIn("najniza_cijena_30_dana_eur", self._rows(self.location._current_versions())["SRV-1"],
                         "Only during a sale")
        content = base64.b64decode(goods.file).decode("utf-8-sig")
        self.assertNotIn("_product_id", content)
        self.assertNotIn("Autumn sale", content, "The name of the sale is not a prescribed column")

        with freeze_time("2026-11-25 05:00:00"):  # renamed while it runs: the same sale
            rule.price_list_special_sale = "Autumn sale -20%"
            row = self._rows(self.location._publish())["GDS-1"]
        self.assertEqual((row["cijena_prije_posebnog_oblika_prodaje_eur"], row["najniza_cijena_30_dana_eur"]), ("125,00", "105,00"))
        with freeze_time("2026-12-01 05:00:00"):  # the morning after the end
            line = self._lines(self.location._publish())["Sensor"]
        self.assertEqual((line["posebni_oblik_prodaje"], line["maloprodajna_cijena_eur"]), ("ne", "125,00"))

    def test_special_sale_older_price_lists_not_counted(self):
        pricelist = self._pricelist()
        self._publish_on("2026-09-01", 105.0)
        self._publish_on("2026-10-15", 125.0)  # current on 18.10.: the 105,00 before it does not count
        self._sale(pricelist)
        row = self._rows(self.location._publish())["GDS-1"]
        self.assertEqual((row["cijena_prije_posebnog_oblika_prodaje_eur"], row["najniza_cijena_30_dana_eur"]), ("125,00", "125,00"))

    def test_special_sale_from_earlier_version_with_goods_and_services(self):
        """Versions published before goods and services had separate files (no kind) count too, also when
        their rows have no product key (before 19.0.2.7.0)."""
        pricelist = self._pricelist()
        versions = self.location._publish()
        legacy = self._goods(versions)
        rows = [{key: value for key, value in row.items() if key != "_product_id"} for row in json.loads(legacy.rows_json)]
        legacy.sudo().write({"kind": False, "rows_json": json.dumps(rows)})
        self._sale(pricelist)
        self.assertEqual(self._rows(self.location._publish())["GDS-1"]["cijena_prije_posebnog_oblika_prodaje_eur"], "125,00")

    def test_earlier_version_with_goods_and_services_is_current_until_replaced(self):
        self.location._publish()
        self.Version.sudo().search([("location_id", "=", self.location.id)]).kind = False
        self.assertEqual(self.location._current_versions().mapped("number"), [2], "The last one with both")
        new = self.location._publish()
        self.assertEqual(new.mapped("kind"), ["goods", "services"])
        self.assertEqual(self.location._current_versions(), new)

    def test_new_product_on_special_sale(self):
        """First published during a special sale: the base price is the regular price."""
        self._sale(self._pricelist(), name="Opening sale")
        goods = self._goods(self.location._publish())
        line = self._lines(goods)["Sensor"]
        self.assertEqual((line["maloprodajna_cijena_eur"], line["bazna_cijena_eur"]), ("100,00", "125,00"))
        row = self._rows(goods)["GDS-1"]
        self.assertEqual((row["cijena_prije_posebnog_oblika_prodaje_eur"], row["najniza_cijena_30_dana_eur"]), ("0,00", "0,00"))

    def test_new_product_on_special_sale_regular_rule(self):
        """During a special sale the regular price is the price of the default pricelist without the rules
        of special sales: a rule without a name counts, the sales price only when there is none."""
        pricelist = self._pricelist()
        pricelist.item_ids = [Command.create({
            "applied_on": "0_product_variant", "product_id": self.goods.id,
            "compute_price": "fixed", "fixed_price": 90.0,
        })]
        self._sale(pricelist)  # newer, so it applies first
        goods = self._goods(self.location._publish())
        line = self._lines(goods)["Sensor"]
        self.assertEqual((line["maloprodajna_cijena_eur"], line["posebni_oblik_prodaje"]), ("100,00", "da"))
        self.assertEqual(line["bazna_cijena_eur"], "90,00", "The regular price of the pricelist")
        self.assertEqual(self._rows(goods)["GDS-1"]["prodajna_cijena_bez_pdv_eur"], "72,00", "Tax included: 90,00")

    def test_special_sale_two_premises(self):
        pricelist = self._pricelist()
        webshop = self.env["l10n_hr.price.list.location"].create({
            "company_id": self.company.id, "object_type": "webshop", "object_code": "02",
            "category_ids": [Command.set(self.category.ids)],
        })
        self._sale(pricelist)
        for location in self.location | webshop:
            line = self._lines(location._publish())["Sensor"]
            self.assertEqual((line["posebni_oblik_prodaje"], line["maloprodajna_cijena_eur"]), ("da", "100,00"))

    def test_pricelist_rule_change_triggers_check(self):
        pricelist = self._pricelist()
        cron = self.env.ref("l10n_hr_price_list.ir_cron_price_list_publish")
        triggers = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])
        self.env.cr.precommit.data.pop("l10n_hr_price_list.triggered", None)  # a new transaction
        self._sale(pricelist)
        self.assertTrue(self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]) - triggers)
        other = self.env["product.pricelist"].create({"name": "Other", "item_ids": [Command.create({
            "applied_on": "3_global", "compute_price": "percentage", "percent_price": 10.0,
        })]})
        triggers = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])
        self.env.cr.precommit.data.pop("l10n_hr_price_list.triggered", None)  # a new transaction
        other.unlink()  # its rules are deleted by the database
        self.assertTrue(self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]) - triggers)

    def test_archived_and_not_sellable_left_out(self):
        self.goods.active = False
        self.service.sale_ok = False
        self.assertFalse(self.location._publish(), "Nothing to publish")
        self.goods.active = True
        self.location._publish()
        self.goods.active = False
        versions = self.location._publish()
        self.assertEqual(versions.mapped("line_count"), [0], "The goods price list is replaced by an empty one")

    def test_file_name_parts(self):
        self.location.write({"object_type": "web_shop", "address": "Ilica 15/2  Zagreb", "object_code": "01"})
        self.assertEqual(self.location.name, "web-shop_Ilica 15-2 Zagreb_01")
        self.assertTrue(self.location.url.endswith("/cjenik/01"))
        self.assertTrue(self.location._current_url("goods").endswith("/cjenik/01/roba"))
        self.location.address = False
        self.assertEqual(self.location.name, "web-shop_Vukovarska 20 Osijek_01")

    def test_file_name_change_is_new_version(self):
        self.location._publish()
        self.location.object_code = "U-04"
        versions = self.location._publish()
        self.assertEqual(self._goods(versions).name, "69114397826_servis_Vukovarska 20 Osijek_U-04_ROBA_003_20261117_0700.csv")

    def test_missing_settings(self):
        self.company.write({"street": False, "city": False, "vat": False})
        with self.assertRaisesRegex(UserError, r"Tax ID \(OIB\) of the company, Address of Premises"):
            self.location._publish()
        with mute_logger(f"{LOGGER}.price_list_version"):
            self.Version._cron_publish()  # logged, not raised
        self.assertFalse(self.location.version_ids)

    def test_replaced_kept_15_days(self):
        """A price list stays public while current and 15 days after it was replaced (article 3(6))."""
        first = self._services(self.location._publish())
        with self.assertRaises(UserError):
            first.unlink()
        with self.assertRaises(UserError):
            self.location.unlink()
        with freeze_time("2026-12-20 06:00:00"):  # replaced after a month: still 15 days from now
            self.service.list_price = 120.0
            second = self.location._publish()
            with self.assertRaises(UserError):
                first.unlink()
        with freeze_time("2027-01-05 06:00:00"):
            first.unlink()
            with self.assertRaises(UserError):
                second.unlink()

    def test_change_triggers_check(self):
        cron = self.env.ref("l10n_hr_price_list.ir_cron_price_list_publish")
        triggers = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])
        self.env.cr.precommit.data.pop("l10n_hr_price_list.triggered", None)  # a new transaction
        self.service.list_price = 99.0
        self.service.barcode = "3850000000015"
        new = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]) - triggers
        self.assertEqual(new.call_at, datetime(2026, 11, 17, 6, 1), "One check per transaction")

    def test_company_change_triggers_check(self):
        cron = self.env.ref("l10n_hr_price_list.ir_cron_price_list_publish")
        triggers = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])
        self.env.cr.precommit.data.pop("l10n_hr_price_list.triggered", None)  # a new transaction
        self.company.vat = "HR33392005961"
        self.assertTrue(self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]) - triggers, "Part of the file name")

    def test_publish_does_not_schedule_another_check(self):
        """Saving the base prices while publishing must not schedule the cron again."""
        cron = self.env.ref("l10n_hr_price_list.ir_cron_price_list_publish")
        triggers = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)])
        self.env.cr.precommit.data.pop("l10n_hr_price_list.triggered", None)  # a new transaction
        self.location._publish()
        self.assertTrue(self._anchor(self.service))
        self.assertFalse(self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id)]) - triggers)

    def test_cron(self):
        self.Version._cron_publish()
        self.Version._cron_publish()
        self.assertEqual(self.location.version_ids.sorted("number").mapped("number"), [1, 2])
        self.assertEqual(set(self.location.version_ids.mapped("webhook_state")), {"none"})


@freeze_time("2026-11-17 06:00:00")
@tagged("post_install", "-at_install")
class TestPriceListWebhook(PriceListCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.location.write({"webhook_url": "https://www.example.com/hook", "webhook_secret": "s3cret"})

    def _response(self, status=200):
        response = requests.Response()
        response.status_code = status
        response.url = "https://www.example.com/hook"
        return response

    def test_sent_signed(self):
        with patch(POST, return_value=self._response()) as post:
            self.Version._cron_publish()
        versions = self.location.version_ids
        self.assertEqual(set(versions.mapped("webhook_state")), {"sent"})
        self.assertEqual(post.call_count, 2, "Goods and services")
        self.assertEqual(post.call_args.args[0], "https://www.example.com/hook")
        payloads = []
        for call in post.call_args_list:
            body = call.kwargs["data"]
            signature = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
            self.assertEqual(call.kwargs["headers"]["X-Price-List-Signature"], f"sha256={signature}")
            payloads.append(json.loads(body))
        goods, services = payloads
        self.assertEqual(goods["event"], "price_list.published")
        self.assertEqual(goods["premises_label"], "U-03")
        self.assertEqual((goods["kind"], goods["number"]), ("goods", 1))
        self.assertEqual((services["kind"], services["number"]), ("services", 2))
        version = self._goods(versions)
        self.assertEqual(goods["file_name"], version.name)
        self.assertTrue(goods["current_url"].endswith("/cjenik/U-03/roba"))
        self.assertEqual(goods["published_at"], "2026-11-17T07:00:00+01:00")
        self.assertEqual(base64.b64decode(goods["content_base64"]), base64.b64decode(version.file))
        self.assertEqual(goods["rows"][0]["prodajna_cijena_bez_pdv_eur"], "100,00", "Tax included: price without it")
        self.assertNotIn("_product_id", goods["rows"][0], "Saved with the rows, not sent")
        row = services["rows"][0]
        self.assertEqual((row["sifra"], row["maloprodajna_cijena_eur"]), ("SRV-1", "125,00"), "Code also of a service")
        self.assertEqual(row["prodajna_cijena_bez_pdv_eur"], "100,00", "Sales price without VAT")
        self.assertNotIn("prodajna_cijena_bez_pdv", base64.b64decode(version.file).decode("utf-8-sig"),
                         "Not in the prescribed file")

    def test_webhook_per_premises(self):
        other = self.env["l10n_hr.price.list.location"].create({
            "company_id": self.company.id,
            "object_type": "webshop",
            "object_code": "02",
            "category_ids": [Command.set(self.category.ids)],
            "webhook_url": "https://shop.example.com/hook",
        })
        with patch(POST, return_value=self._response()) as post:
            self.Version._cron_publish()
        self.assertEqual(sorted(c.args[0] for c in post.call_args_list),
                         ["https://shop.example.com/hook"] * 2 + ["https://www.example.com/hook"] * 2)
        self.assertNotIn("X-Price-List-Signature", [
            c.kwargs["headers"] for c in post.call_args_list if c.args[0].startswith("https://shop")
        ][0])
        self.assertEqual(set(other.version_ids.mapped("webhook_state")), {"sent"})

    @mute_logger(f"{LOGGER}.price_list_version")
    def test_error_retried_in_order(self):
        with patch(POST, side_effect=requests.ConnectionError("down")):
            self.Version._cron_publish()
            self.service.list_price = 120.0
            self.Version._cron_publish()
        versions = self.location.version_ids.sorted("number")
        self.assertEqual(versions.mapped("webhook_state"), ["error", "pending", "pending"], "Stops at the first error")
        self.assertIn("down", versions[0].webhook_error)
        cron = self.env.ref("l10n_hr_price_list.ir_cron_price_list_publish")
        retry = self.env["ir.cron.trigger"].search([("cron_id", "=", cron.id), ("call_at", "=", datetime(2026, 11, 17, 7, 0))])
        self.assertTrue(retry, "Tried again in an hour")
        self.env.invalidate_all()  # nothing computed yet, as after a restart: the versions are read together
        with patch(POST, return_value=self._response()) as post:
            self.Version._cron_publish()
        self.assertEqual(versions.mapped("webhook_state"), ["sent", "sent", "sent"])
        self.assertEqual([json.loads(c.kwargs["data"])["number"] for c in post.call_args_list], [1, 2, 3])

    @mute_logger(f"{LOGGER}.price_list_version")
    def test_redirect_is_error(self):
        """A redirect is not followed (a redirected POST becomes a GET) and is not a success."""
        with patch(POST, return_value=self._response(301)) as post:
            self.Version._cron_publish()
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        version = self._goods(self.location.version_ids)
        self.assertEqual(version.webhook_state, "error")
        self.assertIn("301", version.webhook_error)

    @mute_logger(f"{LOGGER}.price_list_version")
    def test_http_error(self):
        with patch(POST, return_value=self._response(500)):
            self.Version._cron_publish()
        self.assertEqual(self._goods(self.location.version_ids).webhook_state, "error")

    def test_webhook_set_later_sends_current(self):
        self.location.webhook_url = False
        versions = self.location._publish()
        self.assertEqual(set(versions.mapped("webhook_state")), {"none"})
        self.location.webhook_url = "https://www.example.com/hook"
        self.assertEqual(set(versions.mapped("webhook_state")), {"pending"})

    def test_webhook_admin_only(self):
        user = new_test_user(self.env, login="price_list_manager", groups="base.group_user,account.group_account_manager")
        self.location.with_user(user).object_type = "salon"  # other settings: account managers
        with self.assertRaises(AccessError):
            self.location.with_user(user).write({"webhook_url": "https://evil.example.com"})

    def test_publish_now(self):
        with patch(POST, return_value=self._response()):
            action = self.location.action_publish()
        self.assertIn("New price list published", action["params"]["message"])
        self.assertIn("_ROBA_001_", action["params"]["message"])
        with patch(POST, return_value=self._response()):
            action = self.location.action_publish()
        self.assertIn("No changes", action["params"]["message"])
