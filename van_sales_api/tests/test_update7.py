"""Policy tests use fake Frappe boundaries; production-site validation is separate."""
import types
import unittest
from unittest.mock import patch, Mock
from test_update1 import fake, Row, Denied, Invalid, api, settings
import test_update6
from van_sales_api import customer_pricing as policy, sales_features, customer_scope
from van_sales_api.mobile_documents import editable_payload

class PolicyTests(unittest.TestCase):
    def test_permission_fails_closed_and_rechecks_revocation(self):
        for config in [None, Row(), Row(allow_manual_discount=0)]:
            with patch.object(policy,'get_settings',return_value=config):
                with self.assertRaises(Denied):policy.require_discount()
        with patch.object(policy,'get_settings',return_value=Row(allow_manual_discount=1)):
            policy.require_discount()

    def test_direct_discount_payload_cannot_bypass_disabled_policy_even_with_zero(self):
        for pct in [0,10,100]:
            doc=test_update6.DiscountTests().doc()
            with patch.object(policy,'get_settings',return_value=Row(allow_manual_discount=0)):
                with self.assertRaises(Denied):sales_features.apply_discounts(doc,[dict(item_code='I',uom='CT',qty=1,discount_percentage=pct)])
            self.assertEqual(doc.items[0].rate,100)

    def test_automatic_pricing_survives_when_manual_is_disabled(self):
        doc=test_update6.DiscountTests().doc();doc.items[0].rate=85
        with patch.object(policy,'get_settings',return_value=None):
            sales_features.apply_discounts(doc,[dict(item_code='I',uom='CT',qty=1)])
        self.assertEqual(doc.items[0].rate,85)
        self.assertEqual(doc.custom_mobile_manual_discount,0)

    def test_customer_list_ignores_rep_fallback_and_requires_read_permission(self):
        customer=Row(name='C',default_price_list='Wholesale')
        price=Row(enabled=1,selling=1,check_permission=Mock())
        with patch.object(fake,'get_doc',return_value=price,create=True) as read:
            self.assertEqual(policy.customer_price_list(customer),'Wholesale')
            read.assert_called_once_with('Price List','Wholesale');price.check_permission.assert_called_once_with('read')
            price.check_permission.side_effect=Denied()
            with self.assertRaises(Denied):policy.customer_price_list(customer)
        with self.assertRaises(Invalid):policy.customer_price_list(Row(name='NoList'))

    def test_disabled_or_buying_list_rejected(self):
        for enabled,selling in [(0,1),(1,0)]:
            with patch.object(fake,'get_doc',return_value=Row(enabled=enabled,selling=selling,check_permission=lambda p:None),create=True):
                with self.assertRaises(Invalid):policy.customer_price_list(Row(name='C',default_price_list='L'))

    def test_scoped_lists_come_from_visible_assigned_customers(self):
        with patch.object(customer_scope,'customer_filters',return_value={'customer_group':['in',['G']]}),patch.object(fake,'get_list',return_value=[Row(default_price_list='A'),Row(default_price_list='A'),Row(default_price_list=None)],create=True) as query:
            self.assertEqual(policy.permitted_price_lists(),['A'])
            self.assertEqual(query.call_args.kwargs['filters'],{'disabled':0,'customer_group':['in',['G']]})

    def test_submit_rechecks_discount_and_changed_customer_price_list(self):
        data=dict(custom_mobile_manual_discount=1,customer='C',is_return=0)
        doc=types.SimpleNamespace(doctype='Sales Invoice',selling_price_list='A',get=data.get)
        with patch.object(policy,'get_settings',return_value=Row(allow_manual_discount=0)):
            with self.assertRaises(Denied):policy.validate_sale_policy(doc)
        data['custom_mobile_manual_discount']=0
        with patch.object(api,'read_doc',return_value=Row(name='C',default_price_list='B')),patch.object(policy,'customer_price_list',return_value='B'):
            with self.assertRaises(Invalid):policy.validate_sale_policy(doc)
            doc.selling_price_list='B';policy.validate_sale_policy(doc)

    def test_sales_return_keeps_original_pricing(self):
        doc=types.SimpleNamespace(doctype='Sales Invoice',get=lambda k:1 if k=='is_return' else None)
        with patch.object(policy,'require_discount') as gate:policy.validate_sale_policy(doc);gate.assert_not_called()

    def test_pin_holder_cannot_enable_discount(self):
        doc=Row(allow_manual_discount=0,customer_group='G')
        doc.save=Mock();doc.update=Mock()
        token='t';cache=Row(get_value=lambda key:{'user':fake.session.user,'sid':fake.session.sid})
        with patch.object(settings,'get_settings',return_value=doc),patch.object(fake,'cache',cache,create=True),patch.object(fake,'get_roles',return_value=['Sales User'],create=True):
            with self.assertRaises(Denied):settings.save({'allow_manual_discount':1},token=token)
        doc.save.assert_not_called()

    def test_automatic_discounts_are_not_recovered_as_manual_input(self):
        item=Row(item_code='I',item_name='Item',qty=1,uom='CT',price_list_rate=100,discount_percentage=15)
        doc=types.SimpleNamespace(doctype='Quotation',company='Co',party_name='C',selling_price_list='A',valid_till='',items=[item],get=lambda key:None)
        self.assertNotIn('discount_percentage',editable_payload(doc)['items'][0])

    def test_price_catalog_rejects_forged_list(self):
        with patch.object(api,'company_doc'),patch.object(policy,'permitted_price_lists',return_value=['A']):
            with self.assertRaises(Denied):api.catalog('prices',company='Co',price_list='B')

    def test_price_catalog_all_lists_keep_customer_scope_and_list_identity(self):
        with patch.object(api,'company_doc'),patch.object(api,'read_doc'),patch.object(policy,'permitted_price_lists',return_value=['A','B']),patch.object(customer_scope,'customer_names',return_value=['C']),patch.object(api,'visible',return_value=[Row(customer='C'),Row(customer='Other'),Row(customer=None)]) as query:
            result=api.catalog('prices',company='Co')
        self.assertEqual(len(result['rows']),2)
        self.assertIn('price_list',query.call_args.args[1]);self.assertEqual(query.call_args.args[2]['price_list'],['in',['A','B']])

    def test_invoice_builder_uses_customer_list_even_if_client_sends_rep_list(self):
        with patch.object(policy,'get_settings',return_value=Row(allow_manual_discount=1)):
            doc=test_update6.SalesBuilderTests().build(customer_list='Wholesale',client_list='ForgedList')
        self.assertEqual(doc.selling_price_list,'Wholesale')
