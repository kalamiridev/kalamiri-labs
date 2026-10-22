# Kalamiri Labs

Open-source integrations, tools, experiments and technical projects by Kalamiri.

## Projects

### Integrations

#### FusionSolar MQTT

Docker service that reads Huawei FusionSolar plant data and publishes it to MQTT, with optional Home Assistant MQTT Discovery support.

[`integrations/fusionsolar-mqtt`](./integrations/fusionsolar-mqtt/)

### Odoo modules

Modules for Odoo 19 (Community and Enterprise), mostly for Croatian companies. Each module has a README
in Croatian with setup and usage. License: AGPL-3.

**To install the modules**, use the released versions in
**[odoo-croatia](https://github.com/kalamiridev/odoo-croatia)** (branch `19.0`) or the
[Odoo Apps Store](https://apps.odoo.com/apps/modules/19.0/l10n_hr_price_list). This folder is
where they are developed; release tools are in [`odoo/tools`](./odoo/tools/).

| Module | Description |
|---|---|
| [`l10n_hr_price_list`](./odoo/l10n_hr_price_list/) | Public price lists for consumers (CSV, per premises, with the additional price, NN 101/26), with an optional webhook |
| [`l10n_hr_price_list_stock`](./odoo/l10n_hr_price_list_stock/) | Availability in the public price list from the warehouse of each premises (installed automatically with Inventory) |

## Licensing

Projects in this repository may use different open-source licenses.  
See the `LICENSE` file inside each project directory for the license that applies to that project.

## About Kalamiri

Kalamiri develops software, infrastructure, automation and systems integrations.

https://kalamiri.hr
