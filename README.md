# Van Sales API 0.8.3 — API8

Paired with Android 0.8.3 (versionCode9). Maintain the existing app name van_sales_api.

Authenticated diagnostic: /api/method/van_sales_api.connection.status. This module does not import the business API. It reports deployed app/API versions, missing package files/columns, and schema inspection failures without exposing SQL, passwords, CSRF or session tokens.

Incomplete bootstrap returns configured=false and a server_status report without querying business data. Financial save/submit/update routes enforce server readiness before mutation. There is no automatic DDL, data deletion, permission bypass, TLS bypass or CSRF bypass in the request path. The existing installation/migration hooks remain the only additive schema mechanism.

Upload the complete source tree. pyproject.toml belongs at repository root; preserve van_sales_api/van_sales_api/doctype and the controller/JSON files. Deploy the selected commit and migrate the site. Install the new APK first for partial-bootstrap cache protection. See GITHUB_UPLOAD_AR.md for Arabic recovery instructions and limits.

Existing features retained: per-user admin-controlled manual discount; Customer.default_price_list; quotations; encrypted local Android SQLite with UUID-preserving draft queue; print/barcode integrations.

راجع HOTFIX_0.8.3_AR.md لإصلاح bootstrap. التطبيق المتوافق: 0.8.2 / API 8.
