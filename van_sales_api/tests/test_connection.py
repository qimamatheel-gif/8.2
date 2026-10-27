import unittest
from unittest.mock import Mock, patch
from test_update1 import fake, Row, api, Invalid, Denied
from van_sales_api import connection

class ConnectionTests(unittest.TestCase):
    def db(self, missing=(), absent=()):
        return Row(exists=lambda dt,name:name not in absent,
                   has_column=lambda dt,field:(dt,field) not in missing)
    def test_ready_schema(self):
        with patch.object(fake,'db',self.db(),create=True):
            self.assertEqual(connection.schema_readiness(),{'ready':True,'missing_schema':[],'missing_files':[],'unavailable_schema':[]})
    def test_missing_table_does_not_query_its_columns(self):
        db=self.db(absent=['Mobile Sales Settings']);db.has_column=Mock(return_value=True)
        with patch.object(fake,'db',db,create=True):r=connection.schema_readiness()
        self.assertFalse(r['ready']);self.assertIn('Mobile Sales Settings',r['missing_schema'])
        self.assertTrue(all(c.args[0]!='Mobile Sales Settings' for c in db.has_column.call_args_list))
    def test_missing_custom_column_is_named(self):
        with patch.object(fake,'db',self.db(missing=[('Sales Invoice','custom_mobile_manual_discount')]),create=True):
            r=connection.schema_readiness()
        self.assertFalse(r['ready']);self.assertIn('Sales Invoice.custom_mobile_manual_discount',r['missing_schema'])
    def test_missing_package_file_is_named(self):
        original=connection.Path.is_file
        def exists(p):return False if p.name=='customer_pricing.py' else original(p)
        with patch.object(fake,'db',self.db(),create=True),patch.object(connection.Path,'is_file',exists):
            r=connection.schema_readiness()
        self.assertEqual(r['missing_files'],['customer_pricing.py']);self.assertFalse(r['ready'])
    def test_bootstrap_incomplete_schema_still_identifies_user_without_reading_business_data(self):
        with patch.object(connection,'schema_readiness',return_value={'ready':False,'missing_schema':['Mobile Sales Settings'],'missing_files':[]}),patch.object(api,'get_csrf_token',return_value='csrf'),patch.object(api,'visible') as business:
            r=api.bootstrap()
        self.assertEqual(r['user'],fake.session.user);self.assertEqual(r['api_version'],8)
        self.assertFalse(r['configured']);self.assertFalse(r['can_initialize']);self.assertEqual(r['settings'],{})
        business.assert_not_called()
    def test_incomplete_schema_stops_financial_write_before_ledger_or_builder(self):
        with patch.object(connection,'schema_readiness',return_value={'ready':False}),patch.object(api,'invoice') as builder:
            with self.assertRaises(Invalid):api.save_document('request',{'kind':'invoice'})
            with self.assertRaises(Invalid):api.submit_document('Sales Invoice','INV')
        builder.assert_not_called()
    def test_diagnostic_rejects_guest_and_contains_no_secrets(self):
        with patch.object(fake,'session',Row(user='Guest')):
            with self.assertRaises(Denied):connection.status()
        with patch.object(fake,'db',self.db(),create=True):r=connection.status()
        self.assertEqual(r['app_version'],'0.8.2');self.assertEqual(r['api_version'],8)
        for name in ('sid','csrf_token','password','settings'):self.assertNotIn(name,r)

    def test_failed_database_inspection_never_appears_ready_or_leaks_sql(self):
        db=Row(exists=Mock(side_effect=RuntimeError("password=secret SQL table unavailable")))
        with patch.object(fake,'db',db,create=True):r=connection.schema_readiness()
        self.assertFalse(r['ready']);self.assertEqual(len(r['unavailable_schema']),4)
        self.assertNotIn('secret',str(r));self.assertNotIn('password',str(r))
