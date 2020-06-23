# Copyright 2019 Brainbean Apps (https://brainbeanapps.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from collections import defaultdict
from datetime import timedelta
import json
import urllib.parse
import urllib.request
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCurrencyRateProviderOXR(models.Model):
    _inherit = 'res.currency.rate.provider'

    service = fields.Selection(
        selection_add=[('OXR', 'OpenExchangeRates.org')],
    )

    def _get_supported_currencies(self):
        self.ensure_one()
        if self.service != 'OXR':
            return super()._get_supported_currencies()  # pragma: no cover

        for provider in self:
            base_currency = provider.company_id.currency_id.name
            if base_currency != 'USD':
                data = self._oxr_provider_usage_plan()
                if 'error' in data and data['error']:
                    raise UserError(
                        data['description']
                        if 'description' in data
                        else 'Unknown error'
                    )
                if 'name' in data and data['name'] == 'Free':
                    return ['USD']
        url = 'https://openexchangerates.org/api/currencies.json'
        data = json.loads(self._oxr_provider_retrieve(url))
        if 'error' in data and data['error']:
            raise UserError(
                data['description']
                if 'description' in data
                else 'Unknown error'
            )

        return list(data.keys())

    def _obtain_rates(self, base_currency, currencies, date_from, date_to):
        self.ensure_one()
        if self.service != 'OXR':
            return super()._obtain_rates(base_currency, currencies, date_from,
                                         date_to)  # pragma: no cover

        content = defaultdict(dict)
        invert_calculation = False

        if base_currency != 'USD':
            data = self._oxr_provider_usage_plan()
            if 'error' in data and data['error']:
                raise UserError(
                    data['description']
                    if 'description' in data
                    else 'Unknown error'
                )
            if 'name' in data and data['name'] == 'Free':
                invert_calculation = True
                currencies.append(base_currency)
                base_currency = currencies.pop(0)

        date = date_from
        while date <= date_to:
            url = (
                'https://openexchangerates.org/api/historical' +
                '/%(date)s.json'
                '?base=%(from)s' +
                '&symbols=%(to)s'
            ) % {
                'from': base_currency,
                'to': ','.join(currencies),
                'date': str(date),
            }
            logging.info(url)
            data = json.loads(self._oxr_provider_retrieve(url))
            if 'error' in data and data['error']:
                raise UserError(
                    data['description']
                    if 'description' in data
                    else 'Unknown error'
                )
            date_content = content[date.isoformat()]
            base = data['base']
            if 'rates' in data:
                for currency, rate in data['rates'].items():
                    if invert_calculation:
                        date_content[base] = 1.0 / rate
                    else:
                        date_content[currency] = rate

            date += timedelta(days=1)

        return content

    def _oxr_provider_usage_plan(self):
        url = 'https://openexchangerates.org/api/usage.json'
        res = json.loads(self._oxr_provider_retrieve(url))
        if 'data' in res and 'plan' in res['data']:
            return res['data']['plan']
        return res

    def _oxr_provider_retrieve(self, url):
        self.ensure_one()
        with self._oxr_provider_urlopen(url) as response:
            content = response.read().decode(
                response.headers.get_content_charset()
            )
        return content

    def _oxr_provider_urlopen(self, url):
        self.ensure_one()

        if not self.company_id.openexchangerates_app_id:
            raise UserError(_(
                'No OpenExchangeRates.org credentials specified!'
            ))

        parsed_url = urllib.parse.urlparse(url)
        parsed_query = urllib.parse.parse_qs(parsed_url.query)
        parsed_query['app_id'] = self.company_id.openexchangerates_app_id
        parsed_url = parsed_url._replace(query=urllib.parse.urlencode(
            parsed_query,
            doseq=True,
            quote_via=urllib.parse.quote,
        ))
        url = urllib.parse.urlunparse(parsed_url)

        request = urllib.request.Request(url)
        request.add_header(
            'Authorization',
            'Token %s' % self.company_id.openexchangerates_app_id
        )
        return urllib.request.urlopen(request)
