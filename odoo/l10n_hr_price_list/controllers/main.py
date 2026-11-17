import base64
from urllib.parse import quote

from markupsafe import Markup, escape

from odoo import http
from odoo.http import content_disposition, request

from ..models.price_list_location import file_name_part
from ..models.price_list_version import KIND_URL, local_time

PAGE = Markup("""<!DOCTYPE html>
<html lang="%(lang)s"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>%(title)s</title>
<style>body{font-family:sans-serif;margin:2em auto;max-width:60em;padding:0 1em}
td,th{padding:.3em .8em;text-align:left;border-bottom:1px solid #ddd}</style>
</head><body><h1>%(title)s</h1>%(body)s</body></html>""")


class PriceListController(http.Controller):
    """Public price lists, without login (machine-readable, Pravilnik o načinu objave cjenika proizvoda,
    NN 132/26). The current file of each premises is always on the same link, /cjenik/<label>/roba or
    /cjenik/<label>/usluge; every file (also replaced ones) on /cjenik/<file name>."""

    def _locations(self):
        return request.env["l10n_hr.price.list.location"].sudo().search([])

    def _page(self, versions, current_only):
        lang = versions[:1].location_id._lang()
        env = request.env(context=dict(request.env.context, lang=lang))
        title = env._("Price list") if current_only else env._("Price list archive")

        def link(version):
            if current_only and version.kind:
                label = file_name_part(version.location_id.object_code)
                return f"/cjenik/{quote(label)}/{KIND_URL[version.kind]}"
            return f"/cjenik/{quote(version.name)}"

        rows = Markup("").join(
            Markup('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td></tr>') % (
                link(version),
                version.name,
                local_time(version.published_at).strftime("%d.%m.%Y %H:%M"),
                version.location_id.name,
            )
            for version in versions
        )
        archive = Markup("") if not current_only else Markup('<p><a href="/cjenik/arhiva">%s</a></p>') % env._(
            "Previous price lists"
        )
        body = Markup("<table><tr><th>%s</th><th>%s</th><th>%s</th></tr>%s</table>%s") % (
            env._("File"), env._("Published"), env._("Premises"), rows, archive,
        )
        html = PAGE % {"lang": (lang or "hr").split("_")[0], "title": escape(title), "body": body}
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    def _current_page(self, locations):
        current = request.env["l10n_hr.price.list.version"].sudo()
        for location in locations:
            current |= location._current_versions()
        if not current:
            raise request.not_found()
        return self._page(current, current_only=True)

    def _file(self, version):
        return request.make_response(base64.b64decode(version.file), headers=[
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Disposition", content_disposition(version.name, "inline")),
            ("Cache-Control", "no-cache"),
        ])

    @http.route("/cjenik", type="http", auth="public", methods=["GET"], readonly=True)
    def price_list(self, **kwargs):
        return self._current_page(self._locations())

    @http.route("/cjenik/arhiva", type="http", auth="public", methods=["GET"], readonly=True)
    def price_list_archive(self, **kwargs):
        versions = request.env["l10n_hr.price.list.version"].sudo().search([], order="published_at desc, id desc")
        if not versions:
            raise request.not_found()
        return self._page(versions, current_only=False)

    @http.route("/cjenik/<path:name>", type="http", auth="public", methods=["GET"], readonly=True)
    def price_list_file(self, name, **kwargs):
        """A file by its name (any version, also of archived premises), the current files of a premises by
        its label (/cjenik/01) or its current goods or services file (/cjenik/01/roba)."""
        version = request.env["l10n_hr.price.list.version"].sudo().search([("name", "=", name)], limit=1)
        if version:
            return self._file(version)
        label, __, kind_url = name.partition("/")
        locations = self._locations().filtered(lambda location: file_name_part(location.object_code) == label)
        if not kind_url:
            return self._current_page(locations)
        kind = next((kind for kind, url in KIND_URL.items() if url == kind_url), None)
        current = locations[:1]._current_version(kind) if kind and locations else None
        if not current:
            raise request.not_found()
        return self._file(current)
