import unittest
from unittest.mock import Mock,patch
from test_update1 import fake,Row,Cache,settings,Denied,Invalid,api
from van_sales_api import item_batch

class SettingsScopeTests(unittest.TestCase):
 def setUp(self):
  fake.cache=Cache();fake.session=Row(user='agent',sid='sid')
  self.doc=Row(customer_group='Assigned',company='Co');self.doc.get_password=lambda *a,**k:'123456';self.doc.save=Mock()
  p=patch.object(settings,'get_settings',return_value=self.doc);p.start();self.addCleanup(p.stop)
 def test_rep_with_valid_pin_cannot_change_or_clear_group(self):
  with patch.object(fake,'get_roles',return_value=['Sales User']):
   token=settings.unlock('123456')
   for value in ('Other',None,''):
    with self.subTest(value=value),self.assertRaises(Denied):settings.save({'customer_group':value},token)
   self.assertEqual(self.doc.customer_group,'Assigned');self.doc.save.assert_not_called()
 def test_rep_can_keep_or_omit_assigned_group(self):
  with patch.object(fake,'get_roles',return_value=['Sales User']):
   token=settings.unlock('123456')
   settings.save({'warehouse':'W'},token);self.assertEqual(self.doc.customer_group,'Assigned')
   settings.save({'customer_group':'Assigned','warehouse':'W2'},token);self.assertEqual(self.doc.customer_group,'Assigned')
 def test_manager_can_change_group_with_valid_pin(self):
  with patch.object(fake,'get_roles',return_value=['System Manager']):
   settings.save({'customer_group':'Other'},settings.unlock('123456'));self.assertEqual(self.doc.customer_group,'Other')
 def test_unicode_pin_counts_attempts_and_locks(self):
  for value in ['中文','abcعربي','１２３４５６','🙂','x\ud800']:
   with self.subTest(value=repr(value)),self.assertRaisesRegex(Invalid,'غير صحيح'):settings.unlock(value)
  with self.assertRaisesRegex(Invalid,'15'):settings.unlock('123456')
 def test_group_catalog_hidden_from_non_manager(self):
  with patch.object(fake,'get_roles',return_value=['Sales User']),patch.object(api,'visible') as query:
   self.assertEqual(api.catalog('customer_groups'),{'rows':[],'next_start':None});query.assert_not_called()

class BatchTests(unittest.TestCase):
 def prepare(self,n=3,deny=None):
  codes=[f'I{i}' for i in range(n)]
  tables=[Row(options='Item Barcode',fieldname='barcodes'),Row(options='UOM Conversion Detail',fieldname='uoms')]
  def values(dt,filters,fields,**kw):
   if dt=='Item':return [Row(name=c,item_name=c,stock_uom='UN',owner='agent') for c in codes]
   if dt=='Item Barcode':return [Row(parent=c,barcode='BAR'+c,uom='UN') for c in codes]
   return [Row(parent=c,uom='UN',conversion_factor=1) for c in codes]
  checked=[]
  def construct(data):
   self.assertIsInstance(data,dict)
   def check(permission):
    checked.append(data['name']);self.assertEqual(permission,'read')
    self.assertTrue(data['barcodes']);self.assertTrue(data['uoms'])
    if data['name']==deny:raise Denied('custom Item permission')
   return Row(**data,check_permission=check)
  return codes,tables,values,construct,checked
 def test_two_child_queries_for_200_items_and_each_permission_checked(self):
  codes,tables,values,construct,checked=self.prepare(200)
  with patch.object(fake,'get_list',return_value=[Row(name=c) for c in codes],create=True),patch.object(fake,'get_meta',return_value=Row(get_table_fields=lambda:tables),create=True),patch.object(fake,'db',Mock(get_values=Mock(side_effect=values)),create=True),patch.object(fake,'get_doc',side_effect=construct,create=True):
   data=item_batch.item_documents(codes);self.assertEqual(len(data),200)
   self.assertEqual(fake.db.get_values.call_count,3);self.assertEqual(checked,codes)
   self.assertEqual([c.args[0] for c in fake.db.get_values.call_args_list],['Item','Item Barcode','UOM Conversion Detail'])
 def test_custom_item_permission_still_denies_complete_document(self):
  codes,tables,values,construct,_=self.prepare(3,'I1')
  with patch.object(fake,'get_list',return_value=[Row(name=c) for c in codes],create=True),patch.object(fake,'get_meta',return_value=Row(get_table_fields=lambda:tables),create=True),patch.object(fake,'db',Mock(get_values=Mock(side_effect=values)),create=True),patch.object(fake,'get_doc',side_effect=construct,create=True):
   with self.assertRaises(Denied):item_batch.item_documents(codes)
 def test_unauthorized_name_rejected_before_child_fetch(self):
  with patch.object(fake,'get_list',return_value=[Row(name='Allowed')],create=True),patch.object(fake,'db',Mock(),create=True):
   with self.assertRaises(Denied):item_batch.item_documents(['Allowed','Forbidden'])
   fake.db.get_values.assert_not_called()
 def test_extra_item_child_tables_retained_for_permission_hooks(self):
  codes,tables,values,construct,_=self.prepare(1);tables.append(Row(options='Item Default',fieldname='item_defaults'))
  def rows(dt,*a,**k):return [Row(parent='I0',company='Restricted')] if dt=='Item Default' else values(dt,*a,**k)
  with patch.object(fake,'get_list',return_value=[Row(name='I0')],create=True),patch.object(fake,'get_meta',return_value=Row(get_table_fields=lambda:tables),create=True),patch.object(fake,'db',Mock(get_values=Mock(side_effect=rows)),create=True),patch.object(fake,'get_doc',side_effect=construct,create=True) as build:
   item_batch.item_documents(codes);self.assertEqual(build.call_args.args[0]['item_defaults'][0]['company'],'Restricted')
 def test_stock_uses_batch_loader_and_does_not_read_each_item(self):
  items={'A':Row(item_name='Alpha',barcodes=[],uoms=[Row(uom='UN',conversion_factor=1)],stock_uom='UN')}
  with patch.object(api,'company_doc'),patch.object(api,'read_doc',return_value=Row(company='Co',is_group=0)) as read,patch.object(api,'visible',return_value=[Row(item_code='A',actual_qty=12,reserved_qty=2)]),patch.object(api,'item_documents',return_value=items) as batch:
   result=api.stock('Co','W');batch.assert_called_once_with(['A']);self.assertEqual(read.call_count,1);self.assertEqual(result['rows'][0]['units'][0]['available_qty'],10)

class StatementTests(unittest.TestCase):
 def test_document_grouping_is_before_pagination(self):
  queries=[]
  def query(dt,**kw):queries.append(kw);return []
  with patch.object(api,'company_doc',return_value=Row(default_currency='SAR')),patch.object(api,'read_doc'),patch.object(fake,'get_list',side_effect=query,create=True):
   api.statement('Co','C','2026-01-01','2026-12-31',200)
  rows=queries[-1];self.assertEqual(rows['group_by'],'voucher_type, voucher_no');self.assertEqual(rows['limit_start'],200)
  self.assertIn({'SUM':'debit','as':'debit'},rows['fields']);self.assertIn({'SUM':'credit','as':'credit'},rows['fields'])
if __name__=='__main__':unittest.main()
