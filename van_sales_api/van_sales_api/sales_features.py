"""Manual item discounts and customer quotations; business docs keep normal permissions."""
import hashlib
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate
from van_sales_api.validation import clean_lines

LINK_FIELD = "custom_mobile_quotation"

def api():
    from van_sales_api import api as module
    return module

def apply_discounts(doc, requested):
    inputs = clean_lines(requested)
    from van_sales_api.customer_pricing import require_discount
    if any("discount_percentage" in row for row in inputs):
        require_discount()
    expected = []
    for i, row in enumerate(inputs):
        if "discount_percentage" not in row:
            continue
        item = doc.items[i]
        if item.item_code != row["item_code"] or item.uom != row["uom"]:
            frappe.throw(_("تغير ترتيب الأصناف بسبب التسعير. أعد المراجعة"))
        allowed = item.meta.get_permitted_fieldnames(parenttype=doc.doctype, permission_type="write")
        if "discount_percentage" not in allowed:
            frappe.throw(_("لا تملك صلاحية تعديل خصم الصنف"), frappe.PermissionError)
        if flt(item.price_list_rate) <= 0:
            frappe.throw(_("يتطلب الخصم سعر قائمة صالحًا للصنف {0}").format(item.item_code))
        item.discount_percentage = row["discount_percentage"]
        item.discount_amount = 0
        item.rate = 0  # ERPNext calculates from its trusted price-list/margin, never a client rate.
        expected.append((i, item.item_code, item.uom, row["discount_percentage"]))
    doc.flags.mobile_discount_expectations = expected
    doc.custom_mobile_manual_discount = 1 if expected else 0
    return bool(expected)

def verify_discounts(doc):
    for i, code, uom, percentage in doc.flags.get("mobile_discount_expectations", []):
        row = doc.items[i]
        if row.item_code != code or row.uom != uom or abs(flt(row.discount_percentage)-percentage) > 0.0001:
            frappe.throw(_("غيرت قواعد ERPNext الخصم المطلوب للصنف {0}. راجع التسعير أو اترك الخصم تلقائيًا").format(code))

def quotation(payload):
    return api().invoice(payload, as_quotation=True)

def quotation_history(company, customer=None, query="", start=0):
    a=api();a.auth();a.company_doc(company)
    start=int(start)
    if start<0:frappe.throw(_("صفحة غير صالحة"))
    filters={"company":company,"docstatus":1,"quotation_to":"Customer"}
    if customer:
        a.read_doc("Customer",customer);filters["party_name"]=customer
    from van_sales_api.customer_scope import customer_names
    allowed=customer_names()
    if allowed is not None and not customer:filters["party_name"]=["in",allowed or ["__NO_CUSTOMERS__"]]
    query=str(query or "").strip()[:140]
    if query:filters["name"]=["like","%"+query+"%"]
    rows=frappe.get_list("Quotation",fields=["name","transaction_date","party_name","customer_name","grand_total","currency","modified"],filters=filters,order_by="transaction_date desc, modified desc, name desc",limit_start=start,limit_page_length=50)
    for row in rows:row.update(doctype="Quotation",customer=row.party_name,posting_date=row.transaction_date)
    return {"rows":rows,"next_start":start+50 if len(rows)==50 else None}

quotation_history = frappe.whitelist()(quotation_history)

def convert_quotation(payload, request_key, fingerprint):
    """Called under the normal request lock; another UUID cannot duplicate an active conversion."""
    a=api();source=a.read_doc("Quotation",payload.get("quotation"))
    if source.docstatus != 1:frappe.throw(_("اعتمد عرض السعر قبل تحويله إلى فاتورة"))
    config=a.transaction_defaults({"kind":"invoice","company":source.company})
    if config.get("company") != source.company:frappe.throw(_("اختر شركة عرض السعر الأصلية في الإعدادات"))
    company=a.validate_settings(config)
    if source.get("currency") and source.currency != company.default_currency:
        frappe.throw(_("التحويل يدعم عروض الأسعار بعملة الشركة فقط"))
    if not frappe.get_meta("Sales Invoice").has_field(LINK_FIELD):
        frappe.throw(_("نفذ Migrate لإضافة رابط عرض السعر على الفاتورة"))
    lock="van-sales:quotation:"+hashlib.sha256(source.name.encode()).hexdigest()
    with frappe.cache.lock(lock,timeout=600,blocking_timeout=5):
        # This route has performed reads only. Refresh the DB snapshot after acquiring
        # the shared quotation lock, so another request's committed invoice is visible
        # even when the database uses REPEATABLE READ isolation.
        frappe.db.commit()
        source=a.read_doc("Quotation",source.name)
        if source.docstatus!=1:frappe.throw(_("عرض السعر غير معتمد أو ملغى"))
        existing=frappe.db.get_value("Sales Invoice",{LINK_FIELD:source.name,"docstatus":["!=",2]},"name")
        if existing:
            doc=a.read_doc("Sales Invoice",existing)
            if doc.customer != source.party_name or doc.company != source.company:
                frappe.throw(_("الفاتورة المرتبطة لا تطابق عميل وشركة عرض السعر"))
        else:
            if source.get("valid_till") and getdate(source.valid_till)<getdate(nowdate()):
                frappe.throw(_("انتهت صلاحية عرض السعر. حدّثه في ERPNext قبل التحويل"))
            from erpnext.selling.doctype.quotation.quotation import make_sales_invoice
            doc=make_sales_invoice(source.name)  # Standard mapper; no ignore_permissions or client prices.
            if doc.customer != source.party_name or doc.company != source.company:
                frappe.throw(_("تحقق من تطابق عميل وشركة الفاتورة مع عرض السعر"))
            doc.check_permission("create")
            doc.posting_date=nowdate()
            doc.update_stock=1 if config.get("update_stock") else 0
            doc.set_warehouse=config.get("warehouse")
            if doc.update_stock and not doc.set_warehouse:frappe.throw(_("اختر مستودع المندوب أولًا"))
            for row in doc.items:
                a.read_doc("Item",row.item_code)
                if doc.set_warehouse:row.warehouse=doc.set_warehouse
            from van_sales_api.customer_pricing import MANUAL_FIELD, validate_sale_policy
            doc.set(MANUAL_FIELD, 1 if source.get(MANUAL_FIELD) else 0)
            validate_sale_policy(doc)
            doc.set(LINK_FIELD,source.name)
            doc.calculate_taxes_and_totals()
            doc.insert()
        frappe.get_doc({"doctype":"Mobile Request","request_key":request_key,"request_user":frappe.session.user,"payload_hash":fingerprint,"document_type":"Sales Invoice","document_name":doc.name}).insert(ignore_permissions=True)
        frappe.db.commit()
        return a.summary(doc)


def validate_quotation_link(doc):
    name=doc.get(LINK_FIELD)
    if doc.doctype!="Sales Invoice" or not name:return
    source=api().read_doc("Quotation",name)
    if source.docstatus!=1 or source.party_name!=doc.customer or source.company!=doc.company:
        frappe.throw(_("عميل وشركة الفاتورة يجب أن يطابقا عرض السعر المعتمد المرتبط بها"))
