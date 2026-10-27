app_name = "van_sales_api"
app_title = "Van Sales API"
app_publisher = "Van Sales contributors"
app_description = "Android sales integration"
app_email = "maintainer@example.com"
app_license = "MIT"
required_apps = ["erpnext"]

after_install = "van_sales_api.install.ensure_mobile_policy"
after_migrate = "van_sales_api.install.ensure_mobile_policy"
