"""Behavior checks against a fake Frappe boundary, not live integration tests."""
import contextlib
import datetime
import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

class Invalid(Exception): pass
class Denied(Exception): pass
def throw(message, exc=Invalid): raise exc(message)

fake = types.ModuleType('frappe')
fake._ = lambda v: v
fake.throw = throw
fake.ValidationError = Invalid
fake.PermissionError = Denied
fake.AuthenticationError = Denied
fake.whitelist = lambda **kw: lambda fn: fn
fake.session = Row(user='agent', sid='s1')
fake.get_roles = lambda: []
utils = types.ModuleType('frappe.utils')
utils.cint = lambda v: int(v or 0)
utils.flt = lambda v: float(v or 0)
utils.nowdate = lambda: '2026-10-18'
utils.getdate = datetime.date.fromisoformat
sessions = types.ModuleType('frappe.sessions')
sessions.get_csrf_token = lambda: 'csrf'
# Keep one fake runtime for the complete test process, including lazily imported modules.
sys.modules.update({'frappe': fake, 'frappe.utils': utils, 'frappe.sessions': sessions})
settings = importlib.import_module('van_sales_api.settings')
api = importlib.import_module('van_sales_api.api')

class Cache:
    def __init__(self): self.data = {}
    def lock(self, *a, **kw): return contextlib.nullcontext()
    def get_value(self, key): return self.data.get(key)
    def set_value(self, key, value, **kw): self.data[key] = value
    def delete_value(self, key): self.data.pop(key, None)

class SettingsTests(unittest.TestCase):
    def setUp(self):
        fake.cache = Cache()
        fake.session = Row(user='agent', sid='s1')
        self.doc = Row(company='Co', warehouse='Van', price_list='Retail', tax_template='VAT', update_stock=1)
        self.doc.get_password = lambda *a, **kw: '123456'
        self.doc.save = Mock()
        p = patch.object(settings, 'get_settings', return_value=self.doc)
        p.start(); self.addCleanup(p.stop)
    def test_lock_after_five_invalid_attempts(self):
        for _ in range(5):
            with self.assertRaises(Invalid): settings.unlock('000000')
        with self.assertRaisesRegex(Invalid, '15'): settings.unlock('123456')
    def test_token_bound_to_session_and_user(self):
        token = settings.unlock('١٢٣٤٥٦')
        fake.session.sid = 's2'
        with self.assertRaises(Denied): settings.save({}, token)
        fake.session.sid = 's1'; fake.session.user = 'other'
        with self.assertRaises(Denied): settings.save({}, token)
        self.doc.save.assert_not_called()
    def test_authorized_save_filters_fields(self):
        token = settings.unlock('123456')
        settings.save({'company':'Co','warehouse':'New','user':'attacker','settings_pin':'000000'}, token)
        self.assertEqual(self.doc.warehouse, 'New')
        self.assertNotIn('user', self.doc)
        self.assertNotIn('settings_pin', settings.public_settings(self.doc))
        self.doc.save.assert_called_once_with(ignore_permissions=True)
    def test_invoice_defaults_override_client(self):
        out = settings.transaction_defaults({'kind':'invoice','company':'Other','warehouse':'Other','price_list':'Cheap','update_stock':False})
        self.assertEqual((out['company'],out['warehouse'],out['price_list'],out['tax_template'],out['update_stock']), ('Co','Van','Retail','VAT',True))
    def test_first_setup_requires_manager(self):
        with patch.object(settings,'get_settings',return_value=None), patch.object(fake,'get_roles',return_value=[],create=True):
            with self.assertRaises(Denied): settings.save({},pin='123456')

class AccountingTests(unittest.TestCase):
    def setUp(self): fake.session = Row(user='agent',sid='s1')
    def test_statement_dict_aggregation_and_balances(self):
        queries=[]
        def query(dt, **kw):
            queries.append(kw)
            return [Row(debit=100,credit=40)] if len(queries)==1 else [Row(debit=90,credit=20)]
        with patch.object(api,'company_doc',return_value=Row(default_currency='SAR')), patch.object(api,'read_doc'), patch.object(fake,'get_list',side_effect=query,create=True):
            out=api.statement('Co','C','2026-01-01','2026-12-31')
        self.assertEqual((out['opening'],out['closing']), (60,130))
        self.assertEqual(queries[0]['fields'][1], {'SUM':'debit','as':'debit'})
        self.assertEqual(queries[0]['filters']['party'],'C')
        self.assertEqual(queries[0]['group_by'],'party')
    def receipt(self, amount, allocation):
        objects={
            ('Customer','C'):Row(name='C'),
            ('Mode of Payment','Cash'):Row(name='Cash',type='Cash',accounts=[Row(company='Co',default_account='CashAcct')]),
            ('Account','CashAcct'):Row(name='CashAcct',company='Co',is_group=0,disabled=0,account_type='Cash',account_currency='SAR'),
            ('Account','Receivable'):Row(name='Receivable',company='Co',account_currency='SAR'),
            ('Sales Invoice','INV1'):Row(name='INV1',docstatus=1,is_return=0,customer='C',company='Co',currency='SAR',outstanding_amount=80,grand_total=100,due_date='2026-10-18',debit_to='Receivable')}
        doc=Mock(); calls=[]
        for method in ['setup_party_account_field','set_missing_values','set_missing_ref_details','set_exchange_rate','set_amounts']:
            getattr(doc,method).side_effect=lambda m=method:calls.append(m)
        party=types.ModuleType('erpnext.accounts.party')
        party.get_party_account=lambda *a:'Receivable'
        with patch.dict(sys.modules,{'erpnext.accounts.party':party}), patch.object(api,'transaction_defaults',side_effect=lambda p:p), patch.object(api,'validate_settings',return_value=Row(name='Co',default_currency='SAR')), patch.object(api,'read_doc',side_effect=lambda dt,n:objects[(dt,n)]), patch.object(fake,'new_doc',return_value=doc,create=True):
            api.receipt({'company':'Co','customer':'C','mode_of_payment':'Cash','amount':amount,'references':[{'reference_name':'INV1','allocated_amount':allocation}]})
        return doc,calls
    def test_receipt_setup_and_allocation(self):
        doc,calls=self.receipt(50,40)
        self.assertLess(calls.index('setup_party_account_field'),calls.index('set_missing_values'))
        self.assertEqual(doc.append.call_args.args[1]['allocated_amount'],40)
    def test_reject_invoice_overpayment(self):
        with self.assertRaises(Invalid): self.receipt(100,81)
    def test_reject_total_allocation_above_amount(self):
        with self.assertRaises(Invalid): self.receipt(30,40)

if __name__ == '__main__': unittest.main()
