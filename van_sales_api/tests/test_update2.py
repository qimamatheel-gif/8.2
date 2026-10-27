"""Scope and draft lifecycle checks at the mocked Frappe boundary."""
import unittest
from unittest.mock import Mock,patch
from test_update1 import fake,Row,Invalid,Denied,Cache,api,utils
import sys
sys.modules['frappe']=fake
sys.modules['frappe.utils']=utils
sys.modules['van_sales_api.api']=api
from van_sales_api import customer_scope as scope,mobile_documents as docs
from van_sales_api.validation import request_identity
REQUEST='714a3e1d-c66d-431b-877e-1ca028552374'
class ScopeTests(unittest.TestCase):
 def test_unassigned_rep_denied(self):
  with patch.object(scope,'get_settings',return_value=Row()),patch.object(fake,'get_roles',return_value=['Sales User'],create=True):
   with self.assertRaises(Denied):scope.customer_filters()
 def test_admin_can_initialize(self):
  with patch.object(scope,'get_settings',return_value=None),patch.object(fake,'get_roles',return_value=['System Manager'],create=True):self.assertEqual(scope.customer_filters(),{})
 def test_descendants(self):
  group=Row(name='Route A',lft=2,rgt=7,check_permission=Mock())
  with patch.object(scope,'get_settings',return_value=Row(customer_group='Route A')),patch.object(fake,'get_doc',return_value=group,create=True),patch.object(fake,'get_list',return_value=['Route A','Child'],create=True):
   self.assertEqual(scope.group_names(),['Route A','Child']);self.assertEqual(fake.get_list.call_args.kwargs['filters'],{'lft':['>=',2],'rgt':['<=',7]})
 def test_customer_outside_group_denied(self):
  with patch.object(scope,'group_names',return_value=['A']),patch.object(fake,'get_doc',return_value=Row(customer_group='B',check_permission=Mock()),create=True):
   with self.assertRaises(Denied):api.read_doc('Customer','Outside')
 def test_invoice_and_receipt_cannot_bypass_group(self):
  for dt in ['Sales Invoice','Payment Entry']:
   doc=Row(customer='Outside',party='Outside',party_type='Customer',check_permission=Mock());customer=Row(customer_group='B',check_permission=Mock())
   with patch.object(scope,'group_names',return_value=['A']),patch.object(fake,'get_doc',side_effect=lambda d,n:customer if d=='Customer' else doc,create=True):
    with self.subTest(dt=dt),self.assertRaises(Denied):api.read_doc(dt,'DOC')
 def test_cannot_override_invoice_scope(self):
  with patch.object(scope,'customer_names',return_value=['Allowed']):
   with self.assertRaises(Denied):api.visible('Sales Invoice',['name'],{'customer':'Outside'})
 def test_list_filter(self):
  with patch.object(scope,'customer_names',return_value=['Allowed']),patch.object(fake,'get_list',return_value=[],create=True):
   api.visible('Sales Invoice',['name']);self.assertEqual(fake.get_list.call_args.kwargs['filters']['customer'],['in',['Allowed']])
class DraftTests(unittest.TestCase):
 def setUp(self):fake.session=Row(user='agent',sid='s');fake.cache=Cache()
 def test_retirement_is_persisted_before_edit(self):
  db=Mock();db.get_value.return_value=None;ledger=Mock()
  with patch.object(fake,'db',db,create=True),patch.object(fake,'get_doc',return_value=ledger,create=True):
   result=docs.prepare_pending_edit(REQUEST,{'kind':'invoice'});self.assertTrue(result['retired']);self.assertIsNone(result['document']);self.assertEqual(fake.get_doc.call_args.args[0]['abandoned'],1);db.commit.assert_called_once()
 def test_retired_request_never_creates_late_duplicate(self):
  payload={'kind':'invoice'};_,fp=request_identity('agent',REQUEST,payload);db=Mock();db.get_value.return_value=Row(payload_hash=fp,abandoned=1)
  with patch.object(fake,'db',db,create=True),patch.object(api,'invoice') as builder:
   with self.assertRaises(Invalid):api.save_document(REQUEST,payload)
   builder.assert_not_called();db.rollback.assert_called_once()
 def test_reject_stale_revision(self):
  db=Mock();db.get_value.return_value=None
  with patch.object(fake,'db',db,create=True),patch.object(docs,'supported_doc',return_value=Row(docstatus=0,modified='new')),patch.object(api,'invoice') as builder:
   with self.assertRaisesRegex(Invalid,'تعديل المستند'):docs.update_document(REQUEST,'Sales Invoice','INV','old',{'kind':'invoice'})
   builder.assert_not_called()
 def test_reject_edit_after_submit(self):
  db=Mock();db.get_value.return_value=None
  with patch.object(fake,'db',db,create=True),patch.object(docs,'supported_doc',return_value=Row(docstatus=1)):
   with self.assertRaisesRegex(Invalid,'غير المعتمدة'):docs.update_document(REQUEST,'Sales Invoice','INV','old',{'kind':'invoice'})
 def test_update_retry_does_not_save_again(self):
  p={'kind':'invoice'};_,fp=request_identity('agent',REQUEST,docs.request_envelope('Sales Invoice','INV','v',p));db=Mock();db.get_value.return_value=Row(payload_hash=fp,abandoned=0,document_name='INV')
  with patch.object(fake,'db',db,create=True),patch.object(docs,'supported_doc',return_value=Mock()),patch.object(docs,'full_summary',return_value={'name':'INV'}),patch.object(api,'invoice') as builder:
   self.assertEqual(docs.update_document(REQUEST,'Sales Invoice','INV','v',p),{'name':'INV'});builder.assert_not_called()
 def test_reject_submit_after_document_changes(self):
  doc=Row(docstatus=0,modified='new',check_permission=Mock(),submit=Mock());db=Mock()
  with patch.object(fake,'db',db,create=True),patch.object(api,'read_doc',return_value=doc):
   with self.assertRaisesRegex(Invalid,'تغير المستند'):api.submit_document('Sales Invoice','INV','old')
   doc.submit.assert_not_called()
if __name__=='__main__':unittest.main()
