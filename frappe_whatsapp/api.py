"""API endpoints for Frappe WhatsApp."""

import frappe
from frappe.utils.caching import site_cache


@frappe.whitelist()
def get_whatsapp_doctypes():
    """Get DocTypes for WhatsApp module with proper site isolation.
    
    Returns:
        list: List of DocTypes in the Frappe WhatsApp module with their metadata.
        Each DocType contains name, modified timestamp and single flag.
    """
    cache_key = f"whatsapp_doctypes:{frappe.local.site}"
    
    @site_cache(cache_key)
    def _get_doctypes():
        return frappe.get_all(
            "DocType",
            filters={"module": "Frappe Whatsapp"},
            fields=["name", "modified", "issingle"],
            order_by="name"
        )
    
    return _get_doctypes() 