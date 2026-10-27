"""Exact existing invoice QR assets, no synthetic compliance QR or remote fetches."""
import base64
import io
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
import frappe
from van_sales_api.amount_words import amount_words

QR_FIELDS=('custom_qr_code','custom_qr_code_image','custom_qr_code_base64','ksa_einv_qr','qr_code','qr_code_image','custom_zatca_qr_code')
def invoice_qr(doc):
 if doc.doctype!='Sales Invoice' or doc.docstatus!=1:return {}
 candidates=[]
 for field in QR_FIELDS:
  if doc.meta.has_field(field):
   value=doc.get(field)
   if value and isinstance(value,str):candidates.append(value.strip())
 candidates.extend(('/private/files/QR-CODE-'+doc.name+'.png','/files/QR_image_'+doc.name+'.png'))
 for value in candidates:
  if value.startswith(('/files/','/private/files/')):
   path=urlsplit(value)
   if path.query or path.fragment or '..' in PurePosixPath(unquote(path.path)).parts:continue
   file=frappe.db.get_value('File',{'file_url':value},['name','attached_to_doctype','attached_to_name'],as_dict=True)
   if not file:continue
   if file.attached_to_name and (file.attached_to_doctype!='Sales Invoice' or file.attached_to_name!=doc.name):continue
   # Only a trusted invoice field can point to an unattached file. Filename fallback must be attached.
   if not file.attached_to_name and not any(doc.get(f)==value for f in QR_FIELDS if doc.meta.has_field(f)):continue
   content=frappe.get_doc('File',file.name).get_content()
   if isinstance(content,str):content=content.encode()
   if len(content)>1024*1024:continue
   if content.startswith(b'\x89PNG\r\n\x1a\n') or content.startswith(b'\xff\xd8\xff'):
    return {'qr_image':base64.b64encode(content).decode('ascii')}
  else:
   try:raw=base64.b64decode(value,validate=True)
   except (ValueError,TypeError):continue
   # A pre-generated image or existing TLV payload, never invoice URL/name.
   if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)<=1024*1024:return {'qr_image':value}
   if len(raw)<10 or len(raw)>8192 or raw[0]!=1:continue
   import qrcode
   image=qrcode.make(value,box_size=6,border=4);stream=io.BytesIO();image.save(stream,format='PNG')
   return {'qr_image':base64.b64encode(stream.getvalue()).decode('ascii')}
 return {'qr_warning':'QR الفاتورة غير متاح على السيرفر. راجع حقل أو ملف QR الخاص بالفاتورة.'}
def enrich_ticket(result,doc):
 currency=result.get('currency') or 'SAR'
 value=doc.get('rounded_total') or result.get('grand_total') if doc.doctype in ('Sales Invoice','Quotation') else result.get('amount')
 if value is not None:result['amount_words_ar']=amount_words(value,currency)
 if doc.doctype=='Sales Invoice':
  result.update(rounded_total=doc.get('rounded_total'),rounding_adjustment=doc.get('rounding_adjustment'),discount_amount=doc.get('discount_amount'))
  result.update(invoice_qr(doc))
 result['reference_date']=str(doc.get('reference_date') or '')
 result['payment_type']=doc.get('payment_type')
 return result
