"""Batch-load complete Item documents, then retain document-level read checks.

Permission-filter the Item names first. Internal db.get_values loads complete
parent/child rows as get_doc would; nothing is returned before each complete
Item passes check_permission('read'), including custom hooks and User Permissions.
Barcode and UOM tables are each fetched once per batch. Other child tables are
also fetched once to preserve permission hooks that inspect Item Defaults, etc.
"""
import frappe
from frappe import _


def item_documents(codes):
    codes = list(dict.fromkeys(codes))
    if not codes:
        return {}
    if len(codes) > 200:
        frappe.throw(_('طلب الأصناف كبير؛ حدّث الصفحة'))
    allowed = frappe.get_list('Item', fields=['name'], filters={'name': ['in', codes]},
                              limit_page_length=0)
    if set(codes) != {row['name'] for row in allowed}:
        frappe.throw(_('لا تملك صلاحية قراءة أحد أصناف المخزون'), frappe.PermissionError)
    parents = frappe.db.get_values('Item', {'name': ['in', codes]}, '*', as_dict=True)
    data = {row['name']: dict(row, doctype='Item') for row in parents}
    if set(data) != set(codes):
        frappe.throw(_('تغيرت بيانات الأصناف؛ أعد المزامنة'))
    for field in frappe.get_meta('Item').get_table_fields():
        children = frappe.db.get_values(field.options,
            {'parent': ['in', codes], 'parenttype': 'Item', 'parentfield': field.fieldname},
            '*', as_dict=True, order_by='parent, idx')
        for row in data.values():
            row[field.fieldname] = []
        for child in children:
            if child['parent'] in data:
                data[child['parent']][field.fieldname].append(dict(child))
    result = {}
    for code in codes:
        item = frappe.get_doc(data[code])  # dict construction does not reload from DB
        item.check_permission('read')
        result[code] = item
    return result
