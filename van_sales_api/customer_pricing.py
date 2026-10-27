"""Customer-owned selling lists and explicit, fail-closed mobile discount policy."""
import frappe
from frappe import _
from frappe.utils import cint
from van_sales_api.settings import get_settings

MANUAL_FIELD = "custom_mobile_manual_discount"

def can_discount():
    config = get_settings()
    return bool(config and cint(config.get("allow_manual_discount")))

def require_discount():
    if not can_discount():
        frappe.throw(_("صلاحية الخصم اليدوي موقوفة لهذا المستخدم. راجع مسؤول النظام"), frappe.PermissionError)

def customer_price_list(customer):
    # Caller must read/check the Customer first. Never accept a client's fallback.
    name = customer.get("default_price_list")
    if not name:
        frappe.throw(_("حدد قائمة أسعار البيع على بطاقة العميل {0} في ERPNext أولًا").format(customer.name))
    doc = frappe.get_doc("Price List", name)
    doc.check_permission("read")
    if not doc.enabled or not doc.selling:
        frappe.throw(_("قائمة أسعار العميل غير مفعلة للبيع"))
    return name

def permitted_price_lists():
    from van_sales_api.customer_scope import customer_filters
    rows = frappe.get_list("Customer", fields=["default_price_list"],
        filters={"disabled": 0, **customer_filters()}, limit_page_length=0)
    return sorted({r.default_price_list for r in rows if r.default_price_list})

def validate_sale_policy(doc):
    if doc.doctype not in ("Sales Invoice", "Quotation") or doc.get("is_return"):
        return
    if doc.get(MANUAL_FIELD):
        require_discount()
    from van_sales_api.api import read_doc
    customer = read_doc("Customer", doc.get("customer") or doc.get("party_name"))
    if doc.selling_price_list != customer_price_list(customer):
        frappe.throw(_("تغيرت قائمة أسعار العميل. افتح المسودة للتعديل وأعد التسعير قبل الاعتماد"))
