import unittest
from unittest.mock import patch,Mock
from test_update1 import fake,api,Row,Denied,Invalid
from van_sales_api import mobile_reports as reports,customer_scope
from van_sales_api.validation import return_quantity

class ReturnConversionTests(unittest.TestCase):
 def test_selected_carton_converts_to_original_pieces(self):
  self.assertEqual(return_quantity(2,12,1,24),24)
 def test_selected_pieces_convert_to_original_cartons(self):
  self.assertEqual(return_quantity(6,1,12,2),.5)
 def test_over_return_rejected(self):
  with self.assertRaises(ValueError):return_quantity(3,12,1,24)
 def test_invalid_factor_or_quantity_rejected(self):
  for q,f in [(1,0),(0,1),(float('nan'),1),(1,float('inf'))]:
   with self.subTest(q=q,f=f),self.assertRaises(ValueError):return_quantity(q,f,1,24)

class ReturnBuilderTests(unittest.TestCase):
 def build(self, chosen, factor=1, original_uom='UN'):
  import types,sys
  row=Row(sales_invoice_item='R',item_code='A',qty=-24,uom=original_uom,conversion_factor=factor,rate=10)
  doc=types.SimpleNamespace(items=[row],check_permission=Mock(),calculate_taxes_and_totals=Mock())
  doc.set=lambda key,value:setattr(doc,key,value)
  original=Row(docstatus=1,is_return=0,name='INV',company='Co',customer='C')
  item=Row(stock_uom='UN',uoms=[Row(uom='UN',conversion_factor=1),Row(uom='CT',conversion_factor=24 if original_uom=='CT' else 12)])
  module=types.ModuleType('erpnext.accounts.doctype.sales_invoice.sales_invoice');module.make_sales_return=lambda name:doc
  with patch.dict(sys.modules,{'erpnext.accounts.doctype.sales_invoice.sales_invoice':module}),patch.object(api,'read_doc',side_effect=lambda dt,n:original if dt=='Sales Invoice' else item):
   result=api.sales_return({'company':'Co','customer':'C','invoice':'INV','return_items':[dict(row_name='R',**chosen)]})
  return result
 def test_selected_uom_normalized_without_changing_historical_rate(self):
  doc=self.build({'qty':2,'uom':'CT'});self.assertEqual(doc.items[0].qty,-24);self.assertEqual(doc.items[0].rate,10);self.assertEqual(doc.items[0].uom,'UN')
 def test_historical_factor_preserved_for_same_uom_after_master_changes(self):
  doc=self.build({'qty':1,'uom':'CT'},factor=12,original_uom='CT');self.assertEqual(doc.items[0].qty,-1)

class HistoryTests(unittest.TestCase):
 def test_invoice_history_retains_group_scope_and_latest_order(self):
  with patch.object(api,'company_doc'),patch.object(customer_scope,'customer_names',return_value=['C1']),patch.object(fake,'get_list',return_value=[],create=True) as listing:
   result=reports.document_history('Co','invoice',query='INV',start=50)
   kw=listing.call_args.kwargs
   self.assertEqual(kw['filters']['customer'],['in',['C1']]);self.assertEqual(kw['filters']['docstatus'],1)
   self.assertEqual(kw['limit_start'],50);self.assertIn('posting_date desc',kw['order_by']);self.assertIsNone(result['next_start'])
 def test_receipt_history_only_customer_collections(self):
  with patch.object(api,'company_doc'),patch.object(customer_scope,'customer_names',return_value=[]),patch.object(fake,'get_list',return_value=[],create=True) as listing:
   reports.document_history('Co','receipt')
   f=listing.call_args.kwargs['filters'];self.assertEqual(f['payment_type'],'Receive');self.assertEqual(f['party_type'],'Customer');self.assertEqual(f['party'],['in',['__NO_CUSTOMERS__']])
 def test_explicit_customer_checks_document_permission(self):
  with patch.object(api,'company_doc'),patch.object(api,'read_doc',side_effect=Denied('outside')):
   with self.assertRaises(Denied):reports.document_history('Co','invoice','Outside')
 def test_unknown_kind_rejected(self):
  with patch.object(api,'company_doc'):
   with self.assertRaises(Invalid):reports.document_history('Co','Journal Entry')

class StockReportTests(unittest.TestCase):
 def test_barcode_and_zero_filters_match_printed_report(self):
  rows=[Row(item_code='A',item_name='Alpha',actual_qty=12,barcodes=[{'barcode':'4823'}]),Row(item_code='B',item_name='Beta',actual_qty=0,barcodes=[{'barcode':'4823'}])]
  with patch.object(api,'company_doc',return_value=Row(name='Co')),patch.object(fake,'has_permission',return_value=True,create=True),patch.object(api,'stock',return_value={'rows':rows,'next_start':None}):
   self.assertEqual([r['item_code'] for r in reports.stock_print_data('Co','WH','4823',1)['items']],['A'])
 def test_report_permission_required_before_stock_read(self):
  with patch.object(api,'company_doc'),patch.object(fake,'has_permission',return_value=False,create=True),patch.object(api,'stock') as stock:
   with self.assertRaises(Denied):reports.stock_print_data('Co','WH')
   stock.assert_not_called()
 def test_all_registered_units_quoted_individually(self):
  item=Row(stock_uom='UN',uoms=[Row(uom='UN',conversion_factor=1),Row(uom='CT',conversion_factor=12)])
  with patch.object(api,'read_doc',return_value=item),patch.object(api,'invoice',side_effect=lambda p:Row(net_total=10 if p['items'][0]['uom']=='UN' else 120,grand_total=11.5 if p['items'][0]['uom']=='UN' else 138,total_taxes_and_charges=1.5,currency='SAR')) as quote:
   result=api.item_prices('C',['A'])
   self.assertEqual(quote.call_count,2);self.assertEqual(result[0]['units'][1]['after_tax'],138)
if __name__=='__main__':unittest.main()
