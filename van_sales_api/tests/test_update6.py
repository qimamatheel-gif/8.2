import sys
import types
import unittest
from unittest.mock import Mock,patch
from test_update1 import fake, Row, Cache, api, Denied, Invalid
from van_sales_api import sales_features as features
from van_sales_api.validation import clean_lines, discount_percentage
from van_sales_api.mobile_documents import editable_payload

ORIGINAL_READ_DOC=api.read_doc

class DiscountTests(unittest.TestCase):
    def setUp(self):
        p=patch('van_sales_api.customer_pricing.get_settings',return_value=Row(allow_manual_discount=1));p.start();self.addCleanup(p.stop)

    def test_percent_bounds_and_no_client_prices(self):
        for n in [-1,101,float('nan'),float('inf'),True,'bad']:
            with self.subTest(n=n),self.assertRaises((ValueError,TypeError)):discount_percentage(n)
        self.assertEqual(discount_percentage(0),0);self.assertEqual(discount_percentage('12.5'),12.5)
        self.assertEqual(clean_lines([{'item_code':'I','uom':'CT','qty':2,'discount_percentage':10,'rate':.01}]),[{'item_code':'I','uom':'CT','qty':2.0,'discount_percentage':10}])
    def doc(self,allowed=True):
        item=Row(item_code='I',uom='CT',price_list_rate=100,rate=100,discount_percentage=0,
            meta=Row(get_permitted_fieldnames=lambda **kw:['discount_percentage'] if allowed else []))
        return types.SimpleNamespace(doctype='Sales Invoice',items=[item],flags=Row())
    def test_manual_discount_uses_erp_reference_not_client_rate(self):
        d=self.doc();features.apply_discounts(d,[{'item_code':'I','uom':'CT','qty':2,'discount_percentage':10,'rate':.01}])
        self.assertEqual((d.items[0].discount_percentage,d.items[0].rate,d.items[0].discount_amount),(10,0,0))
        features.verify_discounts(d)
    def test_omitted_discount_preserves_automatic_pricing(self):
        d=self.doc();d.items[0].discount_percentage=15;d.items[0].rate=85
        self.assertFalse(features.apply_discounts(d,[{'item_code':'I','uom':'CT','qty':1}]))
        self.assertEqual(d.items[0].rate,85)
    def test_field_permission_and_missing_price_fail(self):
        with self.assertRaises(Denied):features.apply_discounts(self.doc(False),[{'item_code':'I','uom':'CT','qty':1,'discount_percentage':10}])
        d=self.doc();d.items[0].price_list_rate=0
        with self.assertRaises(Invalid):features.apply_discounts(d,[{'item_code':'I','uom':'CT','qty':1,'discount_percentage':10}])
    def test_repricing_cannot_silently_change_requested_discount(self):
        d=self.doc();features.apply_discounts(d,[{'item_code':'I','uom':'CT','qty':1,'discount_percentage':10}]);d.items[0].discount_percentage=20
        with self.assertRaises(Invalid):features.verify_discounts(d)
    def test_quote_edit_payload_preserves_percent_and_expiry(self):
        item=Row(item_code='I',item_name='Item',qty=2,uom='CT',price_list_rate=100,discount_percentage=10)
        # Document child tables are attributes, unlike dict.items.
        d=types.SimpleNamespace(doctype='Quotation',company='Co',party_name='C',selling_price_list='Retail',valid_till='2026-12-01',items=[item],get=lambda key:1 if key=='custom_mobile_manual_discount' else None)
        p=editable_payload(d);self.assertEqual(p['kind'],'quotation');self.assertEqual(p['items'][0]['discount_percentage'],10);self.assertEqual(p['valid_till'],'2026-12-01')

class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.source=Row(name='QTN',doctype='Quotation',company='Co',party_name='C',quotation_to='Customer',docstatus=1,valid_till='2099-01-01')
        self.invoice=Mock();self.invoice.name='INV';self.invoice.doctype='Sales Invoice';self.invoice.customer='C';self.invoice.company='Co';self.invoice.items=[Row(item_code='I')]
        self.ledger=Mock();self.existing=None;self.insert_count=0
        self.invoice.insert.side_effect=self.insert
        self.mapper=Mock(return_value=self.invoice)
        self.db=types.SimpleNamespace(get_value=lambda *a,**kw:self.existing,commit=Mock())
        self.patches=[patch.object(api,'read_doc',side_effect=self.read),patch.object(api,'transaction_defaults',return_value={'company':'Co','warehouse':'WH','update_stock':True}),patch.object(api,'validate_settings'),patch.object(api,'summary',side_effect=lambda d:{'doctype':'Sales Invoice','name':d.name,'docstatus':0,'source_quotation':'QTN'}),patch.object(fake,'get_meta',return_value=Row(has_field=lambda f:True),create=True),patch.object(fake,'db',self.db,create=True),patch.object(fake,'cache',Cache(),create=True),patch.object(fake,'get_doc',return_value=self.ledger,create=True),patch.dict(sys.modules,{'erpnext.selling.doctype.quotation.quotation':types.SimpleNamespace(make_sales_invoice=self.mapper)})]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def read(self,dt,name):
        return self.source if dt=='Quotation' else self.invoice if dt=='Sales Invoice' else Row(name=name)
    def insert(self):self.insert_count+=1;self.existing='INV'
    def test_conversion_is_draft_linked_and_repeated_uuid_uses_existing(self):
        first=features.convert_quotation({'quotation':'QTN'},'key1','hash')
        second=features.convert_quotation({'quotation':'QTN'},'key2','hash')
        self.assertEqual(first,second);self.assertEqual(self.insert_count,1);self.mapper.assert_called_once_with('QTN')
        self.invoice.set.assert_called_with('custom_mobile_quotation','QTN');self.invoice.check_permission.assert_called_with('create');self.invoice.submit.assert_not_called()
    def test_database_snapshot_refresh_precedes_duplicate_lookup(self):
        events=[]
        self.db.commit.side_effect=lambda:events.append('commit')
        self.db.get_value=lambda *a,**kw:events.append('lookup') or self.existing
        features.convert_quotation({'quotation':'QTN'},'key','hash')
        self.assertEqual(events[:2],['commit','lookup'])
    def test_draft_or_cancelled_quote_rejected(self):
        for state in [0,2]:
            self.source.docstatus=state
            with self.assertRaises(Invalid):features.convert_quotation({'quotation':'QTN'},'key','hash')
        self.mapper.assert_not_called()
    def test_expired_quote_and_cross_company_rejected(self):
        self.source.valid_till='2020-01-01'
        with self.assertRaises(Invalid):features.convert_quotation({'quotation':'QTN'},'key','hash')
        self.source.valid_till='2099-01-01';self.source.company='Other'
        with self.assertRaises(Invalid):features.convert_quotation({'quotation':'QTN'},'key','hash')
    def test_existing_invoice_still_requires_normal_read_permission(self):
        self.existing='INV'
        with patch.object(api,'read_doc',side_effect=lambda dt,name:self.source if dt=='Quotation' else (_ for _ in ()).throw(Denied())):
            with self.assertRaises(Denied):features.convert_quotation({'quotation':'QTN'},'key','hash')
        self.invoice.insert.assert_not_called()
    def test_quotation_read_enforces_customer_group(self):
        self.source.check_permission=lambda permission:None
        with patch.object(fake,'get_doc',return_value=self.source,create=True),patch.object(api,'read_doc',side_effect=Denied()) as read:
            with self.assertRaises(Denied):ORIGINAL_READ_DOC('Quotation','QTN')
            read.assert_called_once_with('Customer','C')
    def test_history_uses_company_customer_scope_and_only_approved_customer_quotes(self):
        from van_sales_api import customer_scope
        with patch.object(customer_scope,'customer_names',return_value=['C']),patch.object(fake,'get_list',return_value=[],create=True) as query,patch.object(api,'company_doc'):
            features.quotation_history('Co')
        filters=query.call_args.kwargs['filters'];self.assertEqual(filters['party_name'],['in',['C']]);self.assertEqual(filters['quotation_to'],'Customer');self.assertEqual(filters['docstatus'],1);self.assertEqual(filters['company'],'Co')

class SalesBuilderTests(unittest.TestCase):
    def setUp(self):
        p=patch('van_sales_api.customer_pricing.get_settings',return_value=Row(allow_manual_discount=1));p.start();self.addCleanup(p.stop)

    def build(self, quotation=False, percentage=10, maximum=100, customer_list="Retail", client_list="Retail"):
        class Doc:
            def __init__(self):
                self.flags=Row();self.docstatus=0;self.name='';self.check_permission=Mock();self.insert=Mock()
            def get(self,key):return getattr(self,key,None)
            def update(self,values):
                for k,v in values.items():setattr(self,k,v)
                self.items=[Row(**row,meta=Row(get_permitted_fieldnames=lambda **kw:['discount_percentage'])) for row in self.items]
            def set_missing_values(self):
                self.customer_name='Customer'
                for row in self.items:row.price_list_rate=100;row.rate=100;row.discount_percentage=0;row.discount_amount=0
            def calculate_taxes_and_totals(self):
                for row in self.items:
                    row.rate_with_margin=100;row.rate=100*(1-float(row.discount_percentage)/100);row.amount=row.rate*row.qty
                self.net_total=sum(row.amount for row in self.items);self.total_taxes_and_charges=self.net_total*.15;self.grand_total=self.net_total*1.15
            def validate_max_discount(self):
                if any(row.discount_percentage>maximum for row in self.items):fake.throw('max discount')
        doc=Doc();doc.doctype='Quotation' if quotation else 'Sales Invoice'
        item=Row(name='I',disabled=0,stock_uom='UN',uoms=[Row(uom='CT',conversion_factor=22)])
        lookup={('Item','I'):item,('Customer','C'):Row(name='C',disabled=0,default_price_list=customer_list),('Price List',customer_list):Row(name=customer_list,enabled=1,selling=1,currency='SAR')}
        payload={'company':'Co','customer':'C','price_list':client_list,'items':[{'item_code':'I','uom':'CT','qty':2,'discount_percentage':percentage}],'valid_till':'2099-01-01'}
        with patch.object(fake,'get_doc',return_value=Row(name='Retail',enabled=1,selling=1,check_permission=lambda p:None),create=True),patch.object(api,'transaction_defaults',side_effect=lambda p:p),patch.object(api,'validate_settings',return_value=Row(name='Co',default_currency='SAR')),patch.object(api,'read_doc',side_effect=lambda dt,name:lookup[(dt,name)]),patch.object(fake,'new_doc',return_value=doc,create=True):
            result=api.invoice(payload,as_quotation=quotation)
        return result
    def test_invoice_preview_recalculates_discounted_tax_and_total_without_insert(self):
        doc=self.build();self.assertAlmostEqual(doc.items[0].rate,90);self.assertAlmostEqual(doc.net_total,180);self.assertAlmostEqual(doc.total_taxes_and_charges,27);self.assertAlmostEqual(doc.grand_total,207);doc.insert.assert_not_called()
    def test_customer_quotation_uses_same_pricing_and_does_not_update_stock(self):
        doc=self.build(quotation=True);self.assertEqual(doc.quotation_to,'Customer');self.assertEqual(doc.party_name,'C');self.assertEqual(doc.valid_till,'2099-01-01');self.assertIsNone(doc.get('update_stock'));self.assertAlmostEqual(doc.grand_total,207)
    def test_item_maximum_discount_is_enforced_in_preview(self):
        with self.assertRaises(Invalid):self.build(percentage=10,maximum=5)

class QuotationLinkTests(unittest.TestCase):
    def test_linked_invoice_cannot_switch_customer_or_use_cancelled_quote(self):
        source=Row(docstatus=1,party_name='C',company='Co')
        doc=types.SimpleNamespace(doctype='Sales Invoice',customer='Other',company='Co',get=lambda f:'QTN' if f=='custom_mobile_quotation' else None)
        with patch.object(api,'read_doc',return_value=source):
            with self.assertRaises(Invalid):features.validate_quotation_link(doc)
            doc.customer='C';source.docstatus=2
            with self.assertRaises(Invalid):features.validate_quotation_link(doc)
            source.docstatus=1;features.validate_quotation_link(doc)
    def test_migration_refuses_incompatible_existing_field(self):
        from van_sales_api.install import ensure_quotation_link
        with patch.object(fake,'get_meta',return_value=Row(get_field=lambda f:Row(fieldtype='Data',options='')),create=True):
            with self.assertRaises(Invalid):ensure_quotation_link()
    def test_migration_creates_read_only_no_copy_link_once(self):
        from van_sales_api.install import ensure_quotation_link
        create=Mock()
        with patch.object(fake,'get_meta',return_value=Row(get_field=lambda f:None),create=True),patch.dict(sys.modules,{'frappe.custom.doctype.custom_field.custom_field':types.SimpleNamespace(create_custom_fields=create)}):
            ensure_quotation_link()
        field=create.call_args.args[0]['Sales Invoice'][0]
        self.assertEqual(field['fieldtype'],'Link');self.assertEqual(field['options'],'Quotation');self.assertEqual((field['read_only'],field['no_copy']),(1,1))
