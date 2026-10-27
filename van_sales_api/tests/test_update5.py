import base64
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from test_update1 import fake,Row
from van_sales_api.amount_words import amount_words
from van_sales_api.thermal_data import invoice_qr,enrich_ticket

class ThermalTests(unittest.TestCase):
 def setUp(self):
  patcher=patch.object(fake,"db",SimpleNamespace(get_value=Mock(return_value=None)),create=True);patcher.start();self.addCleanup(patcher.stop)
 def doc(self,**values):
  d=Row(doctype='Sales Invoice',name='INV-1',docstatus=1,meta=Row(has_field=lambda f:f in values),**values)
  return d
 def test_arabic_rounding_currency_and_negative(self):
  self.assertEqual(amount_words('2.995'),'فقط ثلاثة ريالات سعودية لا غير')
  self.assertIn('ريالان سعوديان',amount_words(2));self.assertIn('خمسون هللة',amount_words('1.50'))
  self.assertIn('سالب',amount_words('-15.25'));self.assertIn('دينار كويتي',amount_words('1.001','KWD'))
  self.assertIn('ألف',amount_words('1000'));self.assertIn('مليون',amount_words('1000000'))
 def test_invalid_amounts(self):
  for n in ['NaN','Infinity','1000000000000']:
   with self.subTest(n=n),self.assertRaises(ValueError):amount_words(n)
 def test_draft_has_no_compliance_qr(self):
  d=self.doc();d.docstatus=0;self.assertEqual(invoice_qr(d),{})
 def test_foreign_attached_file_and_traversal_rejected(self):
  with patch.object(fake.db,'get_value',return_value=Row(name='FILE',attached_to_doctype='Sales Invoice',attached_to_name='OTHER')):
   self.assertIn('qr_warning',invoice_qr(self.doc(custom_qr_code='/files/qr.png')))
  with patch.object(fake.db,'get_value',return_value=None) as lookup:
   invoice_qr(self.doc(custom_qr_code='/private/files/../secret.png'))
   self.assertFalse(any(c.args[1].get('file_url')=='/private/files/../secret.png' for c in lookup.call_args_list))
 def test_existing_attached_png_is_preserved_exactly(self):
  content=b'\x89PNG\r\n\x1a\nexact image bytes'
  with patch.object(fake.db,'get_value',return_value=Row(name='FILE',attached_to_doctype='Sales Invoice',attached_to_name='INV-1')),patch.object(fake,'get_doc',return_value=Row(get_content=lambda:content),create=True):
   result=invoice_qr(self.doc());self.assertEqual(base64.b64decode(result['qr_image']),content)
 def test_missing_qr_does_not_invent_url_or_tlv(self):
  with patch.object(fake.db,'get_value',return_value=None):
   result=invoice_qr(self.doc());self.assertNotIn('qr_image',result);self.assertIn('qr_warning',result)
 def test_receipt_words_separate_from_reference(self):
  d=Row(doctype='Payment Entry',reference_date='2026-10-24',payment_type='Receive')
  result=enrich_ticket({'currency':'SAR','amount':115,'reference_no':'BANK-1'},d)
  self.assertIn('خمسة عشر',result['amount_words_ar']);self.assertEqual(result['reference_date'],'2026-10-24');self.assertNotIn('qr_image',result)
