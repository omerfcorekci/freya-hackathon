"""Offline tests for builder/datefacts.py.

Run with: python3 -m unittest builder.tests.test_datefacts
"""

import datetime
import json
import unittest

from builder import datefacts

CFG = {
    'business_weekdays': [0, 1, 2, 3, 4],
    'holidays': ['2026-10-26', '2026-11-11', '2026-11-26', '2026-12-25', '2027-01-01'],
    'next_weekday_means': 'following_calendar_week',
    'currency_word': 'dollars',
    'band_fallback': 'last',
}
NOW = datetime.datetime(2026, 10, 14, 11, 0)  # a Wednesday
TODAY = NOW.date()

BANDS = [
    {'name': 'early', 'days_late_min': 1, 'days_late_max': 7,
     'deadline_kind': 'business_days_after_today', 'deadline_n': 12,
     'deadline_text': 'the 12th business day after today', 'persuasion_attempts': 1},
    {'name': 'late', 'days_late_min': 8, 'days_late_max': 45,
     'deadline_kind': 'business_days_after_today', 'deadline_n': 7,
     'deadline_text': 'the 7th business day after today', 'persuasion_attempts': 2},
]

FLOOR_CFG = {
    'floor_kind': 'by_product_type',
    'floor_by_type': {'credit_card': 'minimum_payment',
                      'personal_loan': 'instalment_amount',
                      'car_loan': 'instalment_amount'},
    'floor_fraction': 0,
    'floor_fixed': 0,
}

L = datefacts.lib_namespace(CFG)


def iso(d):
    return d.isoformat() if d else None


class BusinessDays(unittest.TestCase):

    def test_add_business_days(self):
        self.assertEqual(iso(L['_add_business_days'](TODAY, 12, CFG)), '2026-11-02')
        self.assertEqual(iso(L['_add_business_days'](TODAY, 7, CFG)), '2026-10-23')
        self.assertEqual(iso(L['_add_business_days'](TODAY, 0, CFG)), '2026-10-14')

    def test_last_business_day_of_week(self):
        self.assertEqual(iso(L['_last_business_day_of_week'](TODAY, CFG)), '2026-10-16')
        self.assertEqual(iso(L['_last_business_day_of_week'](TODAY, CFG, 1)), '2026-10-23')
        holiday_friday = dict(CFG, holidays=['2026-10-16'])
        self.assertEqual(iso(L['_last_business_day_of_week'](TODAY, holiday_friday)), '2026-10-15')

    def test_next_business_day(self):
        self.assertEqual(iso(L['_next_business_day']('2026-10-26', CFG)), '2026-10-27')
        self.assertEqual(iso(L['_next_business_day']('2026-10-23', CFG)), '2026-10-27')
        self.assertEqual(iso(L['_next_business_day']('2026-10-26', CFG, True)), '2026-10-27')
        self.assertEqual(iso(L['_next_business_day']('2026-10-14', CFG, True)), '2026-10-14')
        self.assertFalse(L['_is_business_day']('2026-10-26', CFG))
        self.assertTrue(L['_is_business_day']('2026-10-27', CFG))

    def test_offer_dates(self):
        f = L['_resolve_offer_date']
        self.assertEqual(f('last_business_day_this_week_or_next', '2026-10-16', None, CFG), '2026-10-23')
        self.assertEqual(f('last_business_day_this_week_or_next', TODAY, None, CFG), '2026-10-16')
        self.assertEqual(f('next_business_day', '2026-10-23', None, CFG), '2026-10-27')
        self.assertEqual(f('deadline', TODAY, '2026-11-02', CFG), '2026-11-02')
        self.assertEqual(f('today', TODAY, None, CFG), '2026-10-14')
        self.assertIsNone(f('unknown', TODAY, None, CFG))

    def test_parse_now(self):
        p = L['_parse_now']
        self.assertEqual(p('2026-10-14T11:00'), NOW)
        self.assertEqual(p('2026-10-14 11:00:30'), datetime.datetime(2026, 10, 14, 11, 0, 30))
        self.assertEqual(p('2026-10-14T11:00:00Z'), NOW)
        self.assertEqual(p('2026-10-14T11:00+02:00'), NOW)
        self.assertEqual(p('2026-10-14'), datetime.datetime(2026, 10, 14))
        self.assertIsNone(p('yesterday'))
        self.assertIsNone(p(None))


class BandsAndDeadlines(unittest.TestCase):

    def test_bands(self):
        early = L['_band_for'](6, BANDS)
        self.assertEqual(early['name'], 'early')
        self.assertEqual(L['_deadline_for'](TODAY, early, CFG), '2026-11-02')
        late = L['_band_for']('14', BANDS, CFG)
        self.assertEqual(late['name'], 'late')
        self.assertEqual(L['_deadline_for'](TODAY, late, CFG), '2026-10-23')
        self.assertEqual(L['_band_for'](90, BANDS, CFG)['name'], 'late')
        self.assertIsNone(L['_band_for'](90, BANDS, dict(CFG, band_fallback='none')))
        self.assertEqual(L['_band_for'](3, json.dumps(BANDS), CFG)['name'], 'early')

    def test_other_deadline_kinds(self):
        f = L['_deadline_for']
        # 2026-10-14 + 10 days is Saturday 24 Oct; Monday 26 is a holiday.
        self.assertEqual(f(TODAY, {'deadline_kind': 'calendar_days_after_today', 'deadline_n': 10}, CFG),
                         '2026-10-27')
        self.assertEqual(f(TODAY, {'deadline_kind': 'end_of_month'}, CFG), '2026-10-30')
        self.assertEqual(f(TODAY, {'deadline_kind': 'fixed_date', 'deadline_text': '2026-10-30'}, CFG),
                         '2026-10-30')
        self.assertIsNone(f(TODAY, {'deadline_kind': 'whatever'}, CFG))


class DateExpressions(unittest.TestCase):

    def check(self, text, expected, now=NOW):
        self.assertEqual(L['_resolve_date_expr'](text, now, CFG), ('date', expected), text)

    def test_explicit_dates(self):
        self.check('Monday the 26th', '2026-10-26')
        self.check('6 November', '2026-11-06')
        self.check('the thirtieth of October', '2026-10-30')
        self.check('the twenty-sixth of October', '2026-10-26')
        self.check('the 6th of November', '2026-11-06')
        self.check('October 26th', '2026-10-26')
        self.check('Oct 26', '2026-10-26')
        self.check('26 October 2026', '2026-10-26')
        self.check('2026-10-20', '2026-10-20')
        self.check('I can pay on the 23rd', '2026-10-23')
        self.check('the 2nd', '2026-11-02')
        self.check('Friday the sixteenth', '2026-10-16')
        self.check('Friday 16 October', '2026-10-16')
        self.check('let\'s say the twenty second', '2026-10-22')
        self.check('maybe the first of November', '2026-11-01')
        self.check('10 October', '2027-10-10')

    def test_weekdays(self):
        self.check('this Friday', '2026-10-16')
        self.check('next Friday', '2026-10-23')
        self.check('Friday', '2026-10-16')
        self.check('next Friday', '2026-10-23', now=datetime.datetime(2026, 10, 16, 10, 0))
        self.check('Friday next week', '2026-10-23')
        self.assertEqual(L['_resolve_date_expr']('this Monday', NOW, CFG), ('none', ''))
        nxt = dict(CFG, next_weekday_means='next_occurrence')
        self.assertEqual(L['_resolve_date_expr']('next Friday', NOW, nxt), ('date', '2026-10-16'))

    def test_relative(self):
        self.check('tomorrow', '2026-10-15')
        self.check('the day after tomorrow', '2026-10-16')
        self.check('today', '2026-10-14')
        self.check('in two weeks', '2026-10-28')
        self.check('in a week', '2026-10-21')
        self.check('in 3 days', '2026-10-17')

    def test_vague_and_none(self):
        f = L['_resolve_date_expr']
        for text in ('the week after next', 'when my salary comes', 'end of the month',
                     'next week', 'when I get paid', 'later', 'soon', 'in a few days',
                     'next month', 'beginning of next month', 'mid-November'):
            self.assertEqual(f(text, NOW, CFG)[0], 'vague', text)
        self.assertEqual(f('no', NOW, CFG), ('none', ''))
        self.assertEqual(f('just a second', NOW, CFG), ('none', ''))
        self.assertEqual(f(None, NOW, CFG), ('none', ''))
        self.assertEqual(f('end of the month, say the 30th', NOW, CFG), ('date', '2026-10-30'))


class Amounts(unittest.TestCase):

    def test_parse_amount(self):
        p = L['_parse_amount']
        self.assertEqual(p('420'), 420.0)
        self.assertEqual(p('637.50'), 637.5)
        self.assertEqual(p('$420'), 420.0)
        self.assertEqual(p('four hundred and twenty'), 420.0)
        self.assertEqual(p('six hundred thirty-seven fifty'), 637.5)
        self.assertEqual(p('six hundred thirty seven point five'), 637.5)
        self.assertEqual(p('one thousand two hundred and fifty'), 1250.0)
        self.assertEqual(p('1,250 dollars'), 1250.0)
        self.assertEqual(p('1250.00'), 1250.0)
        self.assertEqual(p('twelve hundred'), 1200.0)
        self.assertEqual(p('I can do 300, not 400'), 300.0)
        self.assertEqual(p('on the 23rd I pay 200'), 200.0)
        self.assertEqual(p('four hundred dollars and fifty cents'), 400.5)
        self.assertIsNone(p('four twenty'))
        self.assertIsNone(p('half'))
        self.assertIsNone(p(''))
        self.assertIsNone(p(None))

    def test_speak_money(self):
        self.assertEqual(L['_speak_money'](637.5, CFG), '637.50 dollars')
        self.assertEqual(L['_speak_money'](420, CFG), '420 dollars')
        self.assertEqual(L['_speak_money']('420.0', dict(CFG, currency_word='')), '420')


class Times(unittest.TestCase):

    def test_parse_time(self):
        p = L['_parse_time']
        self.assertEqual(p('around eleven in the morning'), '11:00')
        self.assertEqual(p('6 pm'), '18:00')
        self.assertEqual(p('half past ten'), '10:30')
        self.assertEqual(p('quarter to ten'), '09:45')
        self.assertEqual(p('quarter past six in the evening'), '18:15')
        self.assertEqual(p('18:30'), '18:30')
        self.assertEqual(p('noon'), '12:00')
        self.assertEqual(p('midnight'), '00:00')
        self.assertEqual(p('11am'), '11:00')
        self.assertEqual(p('11 a.m.'), '11:00')
        self.assertEqual(p('11'), '11:00')
        self.assertEqual(p('seven in the evening'), '19:00')
        self.assertIsNone(p('at 6'))
        self.assertIsNone(p('I am not sure'))


class Speaking(unittest.TestCase):

    def test_speak_date(self):
        self.assertEqual(L['_speak_date']('2026-10-16'), 'Friday 16 October')
        self.assertEqual(L['_speak_date']('2026-11-02'), 'Monday 2 November')
        self.assertIsNone(L['_speak_date']('bad'))

    def test_calendar_table(self):
        lines = L['_calendar_table'](TODAY, CFG, 14).splitlines()
        self.assertEqual(len(lines), 14)
        self.assertEqual(lines[0], 'Wed 14 Oct 2026: today')
        self.assertEqual(lines[1], 'Thu 15 Oct 2026: business day')
        self.assertEqual(lines[3], 'Sat 17 Oct 2026: weekend')
        self.assertEqual(lines[12], 'Mon 26 Oct 2026: bank holiday')


class Products(unittest.TestCase):

    CARD = {'product_id': 'P1', 'type': 'credit_card', 'card_last4': '4821',
            'past_due': 420, 'minimum_payment': 126}
    LOAN = {'product_id': 'P2', 'type': 'personal_loan', 'past_due': '310.50',
            'instalment_amount': '103.5'}

    def test_floor(self):
        self.assertEqual(L['_product_floor'](self.CARD, FLOOR_CFG), 126.0)
        self.assertEqual(L['_product_floor'](self.LOAN, FLOOR_CFG), 103.5)
        self.assertEqual(L['_product_floor'](self.CARD, {'floor_kind': 'fraction_of_full',
                                                         'floor_fraction': 0.5}), 210.0)
        self.assertIsNone(L['_product_floor'](self.CARD, {'floor_kind': 'none'}))

    def test_name(self):
        wording = {'credit_card': 'credit card ending {card_last4}', 'personal_loan': 'personal loan'}
        self.assertEqual(L['_product_name'](self.CARD, wording), 'credit card ending 4821')
        self.assertEqual(L['_product_name'](self.LOAN, wording), 'personal loan')
        self.assertEqual(L['_product_name']({'type': 'car_loan'}, wording), 'car loan')
        self.assertEqual(L['_product_name']({'type': 'credit_card'}, wording), 'credit card ending')

    def test_products_from_vars(self):
        f = L['_products_from_vars']
        self.assertEqual(f({'products': [self.CARD, self.LOAN]}), [self.CARD, self.LOAN])
        self.assertEqual(f({'products': json.dumps([self.CARD])}), [self.CARD])
        flat = {'get_account_response.data.products.0.product_id': 'P1',
                'get_account_response.data.products.0.type': 'credit_card',
                'get_account_response.data.products.1.product_id': 'P2'}
        self.assertEqual(f(flat), [{'product_id': 'P1', 'type': 'credit_card'}, {'product_id': 'P2'}])
        self.assertEqual(L['_num_products'](flat), 2)
        self.assertEqual(f({}), [])
        self.assertEqual(f(None), [])


class SandboxSafety(unittest.TestCase):

    def test_lib_is_safe(self):
        datefacts.assert_sandbox_safe(datefacts.LIB_SOURCE)

    def test_rejects_braces_and_imports(self):
        with self.assertRaises(ValueError):
            datefacts.assert_sandbox_safe("x = {'a': {'b': 1}}\n")
        with self.assertRaises(ValueError):
            datefacts.assert_sandbox_safe('import os\n')
        with self.assertRaises(ValueError):
            datefacts.assert_sandbox_safe('from collections import defaultdict\n')
        datefacts.assert_sandbox_safe('import json, re\nfrom datetime import date\n')

    def test_render_cfg(self):
        text = datefacts.render_cfg({'a': {'b': {'c': 1}}, 'd': [{'e': {}}]})
        self.assertNotIn('}}', text)
        self.assertNotIn('{{', text)
        self.assertEqual(json.loads(text), {'a': {'b': {'c': 1}}, 'd': [{'e': {}}]})
        self.assertNotIn('}}', datefacts.render_cfg({'a': {'b': 1}}))

    def test_sandbox_round_trip(self):
        out = datefacts.sandbox_exec(datefacts.LIB_SOURCE + "\nvars['x'] = _speak_date('2026-10-16')\n", {})
        self.assertEqual(out['x'], 'Friday 16 October')

    def test_sandbox_blocks_other_imports(self):
        with self.assertRaises(ImportError):
            datefacts.sandbox_exec('import os\n', {})

    def test_never_raises_on_garbage(self):
        garbage = [None, '', 'xyz', 42, [], {}, object()]
        for g in garbage:
            for name in ('_parse_now', '_to_date', '_parse_amount', '_parse_time', '_speak_date',
                         '_products_from_vars', '_num_products'):
                L[name](g)
            L['_resolve_date_expr'](g, NOW, CFG)
            L['_resolve_date_expr']('Friday', g, CFG)
            L['_band_for'](g, BANDS, CFG)
            L['_deadline_for'](g, BANDS[0], CFG)
            L['_product_floor'](g, FLOOR_CFG)
            L['_product_name'](g, {})
            L['_calendar_table'](g, CFG)
            L['_speak_money'](g, CFG)
            L['_add_business_days'](TODAY, g, CFG)
            L['_is_business_day'](TODAY, g)


if __name__ == '__main__':
    unittest.main()
