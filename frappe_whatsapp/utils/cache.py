"""Cache utility functions for Frappe WhatsApp."""

import frappe


def clear_doctype_cache(doc, method=None):
    """Clear cache when DocType is modified.
    
    This function is triggered by doc_events hook when a DocType is modified
    or deleted. It ensures that the cached DocType list is updated.
    
    Args:
        doc: The DocType document being modified
        method: The trigger method (not used)
    """
    if doc.module == "Frappe Whatsapp":
        cache_key = f"whatsapp_doctypes:{frappe.local.site}"
        frappe.cache().delete_key(cache_key) 