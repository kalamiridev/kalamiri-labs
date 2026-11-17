import base64
import csv
import hashlib
import io
import json
import logging
import re
from collections import defaultdict
from datetime import timedelta
from typing import NamedTuple
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.tools.barcode import check_barcode_encoding

from .price_list_version import (
    BASE_PRICE_DATE_COLUMN, CODE_COLUMN, COLUMNS, GOODS, KIND_FILE_NAME, KIND_URL, KINDS, LOWEST_PRICE_COLUMN,
    NET_COLUMN, PRICE_BEFORE_SALE_COLUMN, PRODUCT_KEY, SERVICES, SPECIAL_SALE_NAME_COLUMN, format_amount,
    format_date, local_now, local_time, parse_amount, public_rows,
)

# The lowest price before a special sale is looked up in these days before it.
LOWEST_PRICE_DAYS = 30


class Price(NamedTuple):
    consumer: float  # with taxes: from the default pricelist or the sales price, as on a quotation
    regular: float  # with taxes: the same without the rules of special sales
    net: float  # the regular price without taxes
    special_sale: str  # name of the special sale of the pricelist rule, or ""

_logger = logging.getLogger(__name__)


def file_name_part(value):
    """A part of the prescribed file name: no separators (_) or path characters."""
    return re.sub(r"\s+", " ", re.sub(r"[_/\\]+", "-", value or "")).strip()


def format_quantity(value):
    """1,5 or 2 (no trailing zeros)."""
    return f"{value:g}".replace(".", ",")


# The premises part of the file name of a price list that applies at all premises (article 6(4)).
ALL_PREMISES = "ZA_SVA_PRODAJNA_MJESTA"


class L10nHrPriceListLocation(models.Model):
    _name = "l10n_hr.price.list.location"
    _description = "Price List Premises"
    _order = "company_id, object_code, id"

    name = fields.Char(compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True, default=lambda self: self.env.company,
    )
    all_premises = fields.Boolean(
        string="All Premises",
        help="The same price list (products and prices) at all your premises: one price list named "
        "ZA_SVA_PRODAJNA_MJESTA instead of one per premises.",
    )
    object_type = fields.Char(
        string="Type of Premises",
        help="Part of the file name, e.g. prodavaonica, ured, servis, salon or webshop.",
    )
    address = fields.Char(
        string="Address of Premises",
        help="Part of the file name, e.g. Ilica 150 Zagreb. Empty: street and city of the company.",
    )
    object_code = fields.Char(
        string="Premises Label",
        required=True,
        default="01",
        help="Your label of the premises (e.g. P-01, U-03), or 01 if you have none: part of the file name and of "
        "the public link of its price list, /cjenik/<label>.",
    )
    category_ids = fields.Many2many(
        "product.category",
        "l10n_hr_price_list_location_category_rel",
        "location_id",
        "category_id",
        string="Product Categories",
        help="Optional. Active sellable products of these categories and their subcategories are published. "
        "Empty: all active sellable products.",
    )
    webhook_url = fields.Char(
        string="Webhook URL",
        groups="base.group_system",
        help="Optional. Every new version of this price list is sent here (POST, JSON), e.g. to "
        "publish it on your own website.",
    )
    webhook_secret = fields.Char(
        string="Webhook Secret",
        groups="base.group_system",
        help="Optional. Each request is signed with it: header X-Price-List-Signature: sha256=<HMAC of the body>.",
    )
    version_ids = fields.One2many("l10n_hr.price.list.version", "location_id", string="Versions")
    version_count = fields.Integer(compute="_compute_version_count")
    url = fields.Char(string="Public Link", compute="_compute_url")

    _company_code_uniq = models.Constraint(
        "UNIQUE(company_id, object_code)",
        "Each premises needs its own label.",
    )

    @api.depends("all_premises", "object_type", "address", "object_code", "company_id.street", "company_id.city")
    def _compute_name(self):
        for location in self:
            location.name = location._premises_name()

    @api.depends("version_ids")
    def _compute_version_count(self):
        for location in self:
            location.version_count = len(location.version_ids)

    @api.depends("object_code")
    def _compute_url(self):
        for location in self:
            code = file_name_part(location.object_code)
            location.url = f"{location.get_base_url()}/cjenik/{quote(code)}" if code else False

    def _address(self):
        self.ensure_one()
        company = self.company_id
        return self.address or " ".join(part for part in (company.street, company.city) if part)

    def _premises_name(self):
        """The premises in the file name: type_address_label, or ZA_SVA_PRODAJNA_MJESTA (Pravilnik o načinu
        objave cjenika proizvoda, NN 132/26, article 6(3) and (4))."""
        self.ensure_one()
        if self.all_premises:
            return ALL_PREMISES
        return "_".join(file_name_part(part) for part in (self.object_type, self._address(), self.object_code))

    def _trader_id(self):
        """OIB of a company, or the registration number of a natural person (craft), as in the file name."""
        self.ensure_one()
        company = self.company_id
        if company.price_list_natural_person:
            return file_name_part(company.company_registry)
        return re.sub(r"\D", "", company.vat or "")

    def _file_name(self, kind, number):
        """OIB_premises_ROBA|USLUGE_storage number_GGGGMMDD_SSMM.csv (article 6(3) and (4))."""
        self.ensure_one()
        return f"{self._trader_id()}_{self._premises_name()}_{KIND_FILE_NAME[kind]}_{number:03d}_{local_now():%Y%m%d_%H%M}.csv"

    def _problem(self):
        """What is missing for a price list, or False."""
        self.ensure_one()
        if self.company_id.price_list_natural_person:
            trader = (_("Company Registry of the company"), self._trader_id())
        else:
            trader = (_("Tax ID (OIB) of the company"), self._trader_id())
        parts = [trader, (_("Premises Label"), file_name_part(self.object_code))]
        if not self.all_premises:
            parts += [
                (_("Type of Premises"), file_name_part(self.object_type)),
                (_("Address of Premises"), file_name_part(self._address())),
            ]
        missing = [label for label, value in parts if not value]
        if missing:
            return _("The public price list %(premises)s needs: %(fields)s.", premises=self.name, fields=", ".join(missing))
        return False

    @api.model_create_multi
    def create(self, vals_list):
        locations = super().create(vals_list)
        self.env["l10n_hr.price.list.version"]._trigger_publish()
        return locations

    def write(self, vals):
        result = super().write(vals)
        if vals.get("webhook_url"):
            # The website gets the current version when the webhook is set.
            for location in self.sudo():
                location._current_versions().filtered(lambda v: v.webhook_state == "none").webhook_state = "pending"
        self.env["l10n_hr.price.list.version"]._trigger_publish()
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_published(self):
        if self.sudo().version_ids:
            raise UserError(_("A published price list must stay public. Archive the premises instead."))

    def _lang(self):
        """Croatian when installed (the price list is for Croatian consumers), otherwise the
        language of the company."""
        self.ensure_one()
        if self.env["res.lang"].sudo().search_count([("code", "=", "hr_HR")], limit=1):
            return "hr_HR"
        return self.company_id.partner_id.lang or self.env.lang

    def _current_version(self, kind):
        """The current file of the goods or of the services price list."""
        self.ensure_one()
        return self.env["l10n_hr.price.list.version"].sudo().search(
            [("location_id", "=", self.id), ("kind", "=", kind)], limit=1,
        )

    def _current_versions(self):
        """The current files: of goods and of services; before they were published separately, the last
        file with both."""
        self.ensure_one()
        current = self.env["l10n_hr.price.list.version"].sudo()
        for kind in KINDS:
            current |= self._current_version(kind)
        return current or self._current_version(False)

    def _current_url(self, kind):
        """The stable link of the current file (article 6(2): a changed price list on the same address)."""
        self.ensure_one()
        return f"{self.get_base_url()}/cjenik/{quote(file_name_part(self.object_code))}/{KIND_URL[kind]}"

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def _products(self):
        """Active sellable products of the categories (and their subcategories); without
        categories all active sellable products."""
        self.ensure_one()
        domain = [("categ_id", "child_of", self.category_ids.ids)] if self.category_ids else []
        return self.env["product.product"].with_company(self.company_id).search(domain + [
            ("sale_ok", "=", True),
            ("type", "!=", "combo"),
            ("company_id", "in", [False, self.company_id.id]),
        ], order="default_code, name, id")

    def _default_pricelist(self):
        """The pricelist Odoo gives a customer from the country of the company without a pricelist of
        their own (as on a quotation); none when Pricelists are turned off."""
        self.ensure_one()
        Pricelist = self.env["product.pricelist"].sudo().with_company(self.company_id)
        if not self.env["res.groups"]._is_feature_enabled("product.group_product_pricelist"):
            return Pricelist
        country = self.company_id.country_id
        if country:
            return Pricelist._get_country_pricelist_multi([country.id])[country.id]
        return Pricelist.search(Pricelist._get_partner_pricelist_multi_search_domain_hook(self.company_id.id), limit=1)

    @api.model
    def _pricelist_prices(self, pricelist, products, currency):
        """{product id: (price without the taxes, rule id or False)}: the price of the rule of the
        pricelist for the product, or its sales price (no rule or no pricelist)."""
        rules = pricelist._compute_price_rule(products, 1.0, currency=currency) if pricelist and products else {}
        result = {}
        for product in products:
            price, rule = rules.get(product.id, (0.0, False))
            result[product.id] = (price, rule) if rule else (product.lst_price, False)
        return result

    def _prices(self, products):
        """{product id: Price}.

        The price for a consumer is the price of the default pricelist (its rule for the product, e.g. a
        discount for a period) or the sales price, with the taxes of the product, as on an invoice without
        a fiscal position. A rule with the name of a special sale makes it a special sale price. The regular
        price is the price of the same pricelist without the rules of special sales (rules without a name
        are regular prices). The regular price without taxes is sent on the webhook (e.g. for showing
        prices to companies on the website)."""
        self.ensure_one()
        company = self.company_id
        currency = company.currency_id
        pricelist = self._default_pricelist()
        prices = self._pricelist_prices(pricelist, products, currency)
        names = {rule.id: (rule.price_list_special_sale or "").strip()
                 for rule in self.env["product.pricelist.item"].sudo().browse({rule for __, rule in prices.values() if rule})}
        on_sale = products.filtered(lambda product: names.get(prices[product.id][1]))
        regular_prices = self._pricelist_prices(
            pricelist.with_context(l10n_hr_price_list_regular_price=True), on_sale, currency,
        )
        result = {}
        for product in products:
            taxes = product.taxes_id._filter_taxes_by_company(company)
            price, rule = prices[product.id]
            consumer = taxes.compute_all(price, currency=currency, quantity=1.0, product=product)
            regular = consumer
            if product.id in regular_prices:
                regular = taxes.compute_all(regular_prices[product.id][0], currency=currency, quantity=1.0, product=product)
            result[product.id] = Price(
                consumer=currency.round(consumer["total_included"]),
                regular=currency.round(regular["total_included"]),
                net=currency.round(regular["total_excluded"]),
                special_sale=names.get(rule, ""),
            )
        return result

    @api.model
    def _kind(self, product):
        return SERVICES if product.type == "service" else GOODS

    @api.model
    def _base_unit(self, product):
        """(net quantity, its unit) when the product has a price per unit of measure (eCommerce), else
        (0, None)."""
        if "base_unit_id" in product._fields and product.base_unit_id and product.base_unit_count:
            return product.base_unit_count, product.base_unit_id
        return 0.0, None

    def _row(self, product, price, anchor, special_sale=""):
        """One line of the price list: the prescribed columns of its kind (article 3(2) and (3)), the
        code also of a service, the name of the special sale and the date of the base price (sent on the
        webhook)."""
        row = {
            "naziv": product.with_context(display_default_code=False).display_name,
            CODE_COLUMN: product.default_code or "",
            "maloprodajna_cijena_eur": format_amount(price),
            "posebni_oblik_prodaje": "da" if special_sale else "ne",
            "bazna_cijena_eur": format_amount(anchor.price),
            SPECIAL_SALE_NAME_COLUMN: special_sale,
            BASE_PRICE_DATE_COLUMN: format_date(anchor.date),
        }
        if self._kind(product) == GOODS:
            quantity, unit = self._base_unit(product)
            barcode = product.barcode or ""
            ean = bool(barcode) and any(check_barcode_encoding(barcode, encoding) for encoding in ("ean13", "ean8"))
            row.update({
                "marka": product.price_list_brand or "",
                "neto_kolicina": format_quantity(quantity) if unit else "",
                "jedinica_mjere": unit.name if unit else product.uom_id.name or "",
                "cijena_za_jedinicu_mjere_eur": format_amount(price / quantity) if unit else "",
                "barkod": barcode,
                "ean_barkod": barcode if ean else "",
            })
        return row

    def _rows(self):
        """{kind: lines of its price list}. A product published here for the first time gets its base
        price: its current price, dated today (during a special sale the regular price). Products without
        a price are left out (their base price would be 0)."""
        self.ensure_one()
        currency = self.company_id.currency_id
        products = self._products().with_context(lang=self._lang())
        prices = self._prices(products)
        products = products.filtered(lambda product: not currency.is_zero(prices[product.id].consumer))
        # Saving the base prices must not schedule another check of this price list.
        Anchor = self.env["l10n_hr.price.list.anchor"].sudo().with_context(l10n_hr_price_list_publishing=True)
        anchors = {anchor.product_id.id: anchor for anchor in Anchor.search([("location_id", "=", self.id)])}
        today = local_now().date()
        new = Anchor.create([
            {"location_id": self.id, "product_id": product.id, "date": today, "price": prices[product.id].regular}
            for product in products if product.id not in anchors
        ])
        anchors.update({anchor.product_id.id: anchor for anchor in new})
        rows = {}
        for kind in KINDS:
            kind_products = products.filtered(lambda product: self._kind(product) == kind)
            on_sale = [product.id for product in kind_products if prices[product.id].special_sale]
            sale_prices = self._special_sale_prices(kind, kind_products, on_sale) if on_sale else {}
            rows[kind] = []
            for product in kind_products:
                price = prices[product.id]
                row = self._row(product, price.consumer, anchors[product.id], price.special_sale)
                row[NET_COLUMN] = format_amount(price.net)
                if product.id in sale_prices:
                    price_before, lowest_price = sale_prices[product.id]
                    row[PRICE_BEFORE_SALE_COLUMN] = format_amount(price_before)
                    row[LOWEST_PRICE_COLUMN] = format_amount(lowest_price)
                row[PRODUCT_KEY] = product.id
                rows[kind].append(row)
        return rows

    def _special_sale_prices(self, kind, products, product_ids):
        """{product id: (price before its special sale, lowest price in the LOWEST_PRICE_DAYS days before
        it)} from the price lists of this kind published for this premises (and the earlier ones with goods
        and services in one file). The sale began with the oldest of the latest versions in a row that show
        it on special sale (now, when none does yet)."""
        self.ensure_one()
        by_code = {product.default_code: product.id for product in products if product.default_code}
        start = dict.fromkeys(product_ids, fields.Datetime.now())
        price_before, prices = {}, defaultdict(list)
        looking, done = set(product_ids), set()
        versions = self.env["l10n_hr.price.list.version"].sudo().search(
            [("location_id", "=", self.id), ("kind", "in", [kind, False])], order="published_at desc, id desc",
        )
        for version in versions:
            rows = {}
            for row in json.loads(version.rows_json or "[]"):
                product_id = row.get(PRODUCT_KEY) or by_code.get(row.get(CODE_COLUMN))  # older versions: by code
                if product_id:
                    rows[product_id] = row
            for product_id in product_ids:
                if product_id in done:
                    continue
                row = rows.get(product_id)
                if product_id in looking:
                    if row and row.get("posebni_oblik_prodaje") == "da":
                        start[product_id] = version.published_at
                        continue
                    looking.discard(product_id)
                    price_before[product_id] = parse_amount(row["maloprodajna_cijena_eur"]) if row else 0.0
                # Published before the sale: valid in the days before it, back to the version that was
                # current when they began.
                if row:
                    prices[product_id].append(parse_amount(row["maloprodajna_cijena_eur"]))
                if version.published_at <= start[product_id] - timedelta(days=LOWEST_PRICE_DAYS):
                    done.add(product_id)
            if len(done) == len(product_ids):
                break
        return {
            product_id: (price_before.get(product_id, 0.0), min(prices[product_id], default=0.0))
            for product_id in product_ids
        }

    @api.model
    def _csv(self, kind, rows):
        """UTF-8 with BOM (opens correctly in Excel), semicolons, decimal comma (article 6(6) and (7))."""
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer, fieldnames=COLUMNS[kind], delimiter=";", lineterminator="\r\n", extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8-sig")

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------

    def _publish(self):
        """Publish a new version of the goods and of the services price list when its rows (also the
        values sent on the webhook) or the trader and premises in its file name changed. A price list is
        published once it has lines; after that also when none are left.

        :returns: the new versions (none when nothing changed)
        """
        self.ensure_one()
        problem = self._problem()
        if problem:
            raise UserError(problem)
        location = self.sudo()
        Version = self.env["l10n_hr.price.list.version"].sudo()
        new = Version
        premises = f"{location._trader_id()}_{location._premises_name()}"
        for kind, rows in location._rows().items():
            current = location._current_version(kind)
            if not rows and not current:
                continue
            published = json.dumps(public_rows(rows), ensure_ascii=False, sort_keys=True)
            checksum = hashlib.sha256(premises.encode() + b"\0" + published.encode()).hexdigest()
            if current.checksum == checksum:
                continue
            last = Version.search([("location_id", "=", location.id)], order="number desc", limit=1)
            name = location._file_name(kind, last.number + 1)
            new |= Version.create({
                "location_id": location.id,
                "kind": kind,
                "number": last.number + 1,
                "name": name,
                "published_at": fields.Datetime.now(),
                "file": base64.b64encode(location._csv(kind, rows)),
                "checksum": checksum,
                "rows_json": json.dumps(rows, ensure_ascii=False, sort_keys=True),
                "line_count": len(rows),
                "webhook_state": "pending" if location.webhook_url else "none",
            })
            _logger.info("Price list %s published for %s", name, location.company_id.name)
        return new


    def _send_webhooks(self):
        """Send unsent versions oldest first; stop at the first error (tried again later),
        so the website gets them in order."""
        for location in self.sudo():
            if not location.webhook_url:
                continue
            versions = location.version_ids.filtered(lambda v: v.webhook_state in ("pending", "error"))
            for version in versions.sorted("number"):
                if not version._webhook_send():
                    break

    def action_publish(self):
        """Publish now (administrators): a new version if anything changed, then the webhook."""
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only administrators can publish the price list."))
        new = self._publish()
        self._send_webhooks()
        current = self._current_versions()
        if new:
            message = _("New price list published: %(names)s", names=", ".join(new.mapped("name")))
        elif current:
            message = _("No changes: the current price list is %(names)s", names=", ".join(current.mapped("name")))
        else:
            message = _("Nothing to publish: the premises has no sellable products with a price.")
        notification_type = "success" if current else "warning"
        failed = (new | current).filtered(lambda version: version.webhook_state == "error")
        if failed:
            message += "\n" + _(
                "Not sent to the webhook: %(error)s. Odoo tries again in an hour.", error=failed[0].webhook_error,
            )
            notification_type = "warning"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "message": message,
                "type": notification_type,
                "sticky": notification_type == "warning",
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_versions(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("l10n_hr_price_list.action_price_list_version")
        action["domain"] = [("location_id", "in", self.ids)]
        return action
