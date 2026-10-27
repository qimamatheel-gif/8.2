"""Install only the additive quotation link, without overwriting existing customization."""
import frappe

def ensure_quotation_link():
    field=frappe.get_meta("Sales Invoice").get_field("custom_mobile_quotation")
    if field:
        if field.fieldtype!="Link" or field.options!="Quotation":
            frappe.throw("custom_mobile_quotation already exists with an incompatible definition")
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Sales Invoice":[{"fieldname":"custom_mobile_quotation","label":"عرض السعر / Quotation","fieldtype":"Link","options":"Quotation","insert_after":"customer","read_only":1,"no_copy":1}]},update=False)


def ensure_mobile_policy():
    ensure_quotation_link()
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    from van_sales_api.customer_pricing import MANUAL_FIELD
    pending = {}
    for doctype in ("Sales Invoice", "Quotation"):
        field = frappe.get_meta(doctype).get_field(MANUAL_FIELD)
        if field and field.fieldtype != "Check":
            frappe.throw(MANUAL_FIELD + " already exists with an incompatible definition")
        if not field:
            pending[doctype] = [{"fieldname": MANUAL_FIELD, "label": "خصم يدوي من تطبيق المندوب",
                "fieldtype": "Check", "default": "0", "read_only": 1, "no_copy": 1}]
    if pending:
        create_custom_fields(pending, update=False)
