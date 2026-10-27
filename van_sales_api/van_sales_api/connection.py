"""Small authenticated diagnostic, independent of the business API imports."""
from pathlib import Path
import frappe
from frappe import _
from van_sales_api import API_VERSION, __version__

REQUIRED_COLUMNS = {
    "Mobile Request": ("request_key", "request_user", "payload_hash", "document_type", "document_name", "abandoned"),
    "Mobile Sales Settings": ("user", "company", "customer_group", "warehouse", "allow_manual_discount", "target_warehouse", "price_list", "tax_template", "mode_of_payment", "update_stock", "latitude_field", "longitude_field", "settings_pin"),
    "Sales Invoice": ("custom_mobile_quotation", "custom_mobile_manual_discount"),
    "Quotation": ("custom_mobile_manual_discount",),
}
REQUIRED_FILES = ("api.py", "settings.py", "customer_scope.py", "customer_pricing.py",
    "mobile_documents.py", "sales_features.py", "install.py", "item_batch.py", "validation.py",
    "mobile_reports.py", "thermal_data.py", "amount_words.py", "hooks.py", "modules.txt",
    "van_sales_api/doctype/mobile_request/mobile_request.py",
    "van_sales_api/doctype/mobile_sales_settings/mobile_sales_settings.py",
    "van_sales_api/doctype/mobile_request/mobile_request.json",
    "van_sales_api/doctype/mobile_sales_settings/mobile_sales_settings.json")

def schema_readiness():
    missing = []
    unavailable = []
    for doctype, fields in REQUIRED_COLUMNS.items():
        try:
            if not frappe.db.exists("DocType", doctype):
                missing.append(doctype)
                continue
            for field in fields:
                if not frappe.db.has_column(doctype, field):
                    missing.append(doctype + "." + field)
        except Exception:
            # Inspection failure cannot grant readiness; return no SQL or private paths.
            unavailable.append(doctype)
    root = Path(__file__).resolve().parent
    files = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    return {"ready": not missing and not files and not unavailable, "missing_schema": missing, "missing_files": files, "unavailable_schema": unavailable}

def require_server_ready():
    if not schema_readiness()["ready"]:
        frappe.throw(_("إضافة السيرفر غير مكتملة أو لم يكتمل Migrate. افتح فحص الاتصال لمعرفة العناصر الناقصة"))

@frappe.whitelist(methods=["GET"])
def status():
    if frappe.session.user == "Guest":
        frappe.throw(_("يرجى تسجيل الدخول"), frappe.AuthenticationError)
    return {"user": frappe.session.user, "api_version": API_VERSION,
            "app_version": __version__, **schema_readiness()}
