from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    price_list_natural_person = fields.Boolean(
        string="Natural Person (Craft)",
        help="The file name of the public price list starts with the registration number (Company Registry) of "
        "a trader who is a natural person, and with the OIB (Tax ID) of a legal person.",
    )

    def write(self, vals):
        result = super().write(vals)
        if {"vat", "company_registry", "price_list_natural_person", "street", "city"} & vals.keys():
            self.env["l10n_hr.price.list.version"]._trigger_publish()  # part of the file name
        return result


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    price_list_natural_person = fields.Boolean(related="company_id.price_list_natural_person", readonly=False)
