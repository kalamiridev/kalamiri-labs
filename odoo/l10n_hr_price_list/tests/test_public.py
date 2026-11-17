from urllib.parse import quote

from odoo import Command
from odoo.tests import HttpCase, tagged

from .common import PriceListCommon


@tagged("post_install", "-at_install")
class TestPriceListPublic(PriceListCommon, HttpCase):

    def setUp(self):
        super().setUp()
        self.authenticate(None, None)  # public visitor of this database
        # Premises of other companies of the test database are not part of the test.
        self.env["l10n_hr.price.list.location"].sudo().search([("id", "!=", self.location.id)]).active = False

    def test_public_without_login(self):
        old = self._services(self.location._publish())
        self.service.list_price = 120.0
        current = self.location._publish()
        goods = self.location._current_version("goods")

        response = self.url_open("/cjenik")
        self.assertEqual(response.status_code, 200)
        self.assertIn(current.name, response.text)
        self.assertIn(goods.name, response.text)
        self.assertIn('href="/cjenik/U-03/usluge"', response.text, "The stable link of the current file")
        self.assertNotIn(old.name, response.text)

        response = self.url_open("/cjenik/U-03")
        self.assertEqual(response.status_code, 200, "By premises label")
        self.assertIn(current.name, response.text)

        # A changed price list on the same address (NN 132/26, article 6(2)).
        response = self.url_open("/cjenik/U-03/usluge", allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(quote(current.name), response.headers["Content-Disposition"])
        self.assertIn("150,00", response.content.decode("utf-8-sig"))
        self.assertIn("Sensor", self.url_open("/cjenik/U-03/roba").content.decode("utf-8-sig"))

        response = self.url_open(f"/cjenik/{quote(current.name)}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("150,00", response.content.decode("utf-8-sig"))

        response = self.url_open(f"/cjenik/{quote(old.name)}")
        self.assertEqual(response.status_code, 200, "Replaced versions stay public")
        self.assertIn("125,00", response.content.decode("utf-8-sig"))

        response = self.url_open("/cjenik/arhiva")
        self.assertEqual(response.status_code, 200)
        self.assertIn(old.name, response.text)
        self.assertIn(current.name, response.text)

        self.assertEqual(self.url_open("/cjenik/nothing.csv").status_code, 404)
        self.assertEqual(self.url_open("/cjenik/U-03/other").status_code, 404)

    def test_two_premises_listed(self):
        webshop = self.env["l10n_hr.price.list.location"].create({
            "company_id": self.company.id,
            "object_type": "webshop",
            "object_code": "02",
            "category_ids": [Command.set(self.category.ids)],
        })
        office = self.location._publish()
        shop = webshop._publish()
        response = self.url_open("/cjenik")
        for version in office | shop:
            self.assertIn(version.name, response.text)
        response = self.url_open("/cjenik/02/roba")
        self.assertIn(quote(self._goods(shop).name), response.headers["Content-Disposition"])

    def test_archived_premises_not_listed(self):
        versions = self.location._publish()
        self.location.active = False
        self.assertEqual(self.url_open("/cjenik").status_code, 404)
        self.assertEqual(self.url_open(f"/cjenik/{quote(versions[0].name)}").status_code, 200, "Files stay public")
