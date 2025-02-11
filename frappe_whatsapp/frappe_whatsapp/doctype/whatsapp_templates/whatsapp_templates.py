"""Create whatsapp template."""

# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import os
import json
import frappe
import magic
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request, make_request
from frappe.desk.form.utils import get_pdf_link
from frappe.utils.password import get_decrypted_password
from frappe import _
from frappe_whatsapp.utils.connection import get_connection_config, get_url, make_whatsapp_request

class WhatsAppTemplates(Document):
    """WhatsApp Templates."""

    def validate(self):
        """Validate."""
        if not self.language_code or self.has_value_changed("language"):
            lang_code = frappe.db.get_value("Language", self.language) or "en"
            self.language_code = lang_code.replace("-", "_")

        if self.header_type in ["IMAGE", "DOCUMENT"]:
            # Only get new media ID if sample file changed or doesn't exist
            if self.has_value_changed("sample") or not hasattr(self, '_media_id'):
                self.get_session_id()
                self.get_media_id()

        # Track which fields have changed for update
        self._changed_components = []
        if self.has_value_changed("template"):
            self._changed_components.append("BODY")
        if self.has_value_changed("header") or self.has_value_changed("header_type") or self.has_value_changed("sample"):
            self._changed_components.append("HEADER")
        if self.has_value_changed("footer"):
            self._changed_components.append("FOOTER")

        # If document exists and components changed, update template
        if not self.is_new() and self._changed_components:
            self.get_settings()
            self.update_template()

    def update_template(self):
        """Update template to meta."""
        data = {
            "components": []
        }

        # Add body component with sample values if changed
        if "BODY" in self._changed_components:
            body = {
                "type": "BODY",
                "text": self.template,
            }
            if self.sample_values:
                body.update({"example": {"body_text": [self.sample_values.split(",")]}})
            data["components"].append(body)

        # Add header if changed
        if "HEADER" in self._changed_components and self.header_type:
            data["components"].append(self.get_header())

        # Add footer if changed
        if "FOOTER" in self._changed_components and self.footer:
            data["components"].append({"type": "FOOTER", "text": self.footer})

        if not data["components"]:
            return

        try:
            make_whatsapp_request(
                "POST",
                f"{self._version}/{self.id}",
                settings=self._settings,
                data=data
            )
        except Exception as e:
            frappe.throw(str(e))

    def before_save(self):
        """Before save."""
        if not self.actual_name:
            self.actual_name = self.template_name.lower().replace(" ", "_")
        
        # Track which fields have changed for update
        self._changed_components = []
        if self.has_value_changed("template"):
            self._changed_components.append("BODY")
        if self.has_value_changed("header") or self.has_value_changed("header_type") or self.has_value_changed("sample"):
            self._changed_components.append("HEADER")
        if self.has_value_changed("footer"):
            self._changed_components.append("FOOTER")

    def get_session_id(self):
        """Upload media."""
        self.get_settings()
        file_path = self.get_absolute_path(self.sample)
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)

        payload = {
            'file_length': os.path.getsize(file_path),
            'file_type': file_type,
            'messaging_product': 'whatsapp'
        }

        try:
            response = make_whatsapp_request(
                "POST",
                f"{self._version}/{self._app_id}/uploads",
                settings=self._settings,
                data=payload
            )
            self._session_id = response.json()['id']
        except Exception as e:
            frappe.throw(str(e))

    def get_media_id(self):
        """Get media ID after uploading file."""
        self.get_settings()
        file_name = self.get_absolute_path(self.sample)
        
        try:
            with open(file_name, mode='rb') as file:
                file_content = file.read()
                
            response = make_whatsapp_request(
                "POST",
                f"{self._version}/{self._session_id}",
                settings=self._settings,
                data=file_content,
                headers={"Content-Type": "application/octet-stream"}
            )
            self._media_id = response.json()['h']
            # Store media_id in db for future reference
            self.media_id = self._media_id
        except Exception as e:
            frappe.throw(str(e))

    def get_absolute_path(self, file_name):
        """Get absolute path of file."""
        if not file_name:
            return None
            
        if file_name.startswith('/files/'):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}/public{file_name}'
        if file_name.startswith('/private/'):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}{file_name}'
        return file_path

    def after_insert(self):
        """After insert."""
        self.get_settings()
        data = {
            "name": self.actual_name,
            "language": self.language_code,
            "category": self.category,
            "components": []
        }

        # Add body component with sample values
        body = {
            "type": "BODY",
            "text": self.template,
        }
        if self.sample_values:
            body.update({"example": {"body_text": [self.sample_values.split(",")]}})
        data["components"].append(body)

        # Add header if specified
        if self.header_type:
            data["components"].append(self.get_header())

        # Add footer if specified
        if self.footer:
            data["components"].append({"type": "FOOTER", "text": self.footer})

        try:
            response = make_whatsapp_request(
                "POST",
                f"{self._version}/{self._business_id}/message_templates",
                settings=self._settings,
                data=data
            )
            template_data = response.json()
            self.id = template_data.get("id")
            self.status = template_data.get("status")
            self.db_update()
        except Exception as e:
            frappe.throw(str(e))

    def get_settings(self):
        """Get whatsapp settings."""
        self._settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
        self._version = self._settings.version
        self._business_id = self._settings.business_id
        self._app_id = self._settings.app_id
        
        # Restore media_id from db if exists
        if hasattr(self, 'media_id') and self.media_id:
            self._media_id = self.media_id

    def on_trash(self):
        """Delete template from Meta."""
        self.get_settings()
        try:
            make_whatsapp_request(
                "DELETE",
                f"{self._version}/{self._business_id}/message_templates",
                settings=self._settings,
                params={"name": self.actual_name}
            )
        except Exception as e:
            if "Message Template Not Found" in str(e):
                frappe.msgprint(_("Deleted locally"), alert=True)
            else:
                frappe.throw(str(e))

    def get_header(self):
        """Get header format."""
        header = {"type": "header", "format": self.header_type}
        if self.header_type == "TEXT":
            header["text"] = self.header
            if self.sample:
                samples = self.sample.split(", ")
                header.update({"example": {"header_text": samples}})
        else:
            if not self.sample and not self.media_id:
                key = frappe.get_doc(self.doctype, self.name).get_document_share_key()
                link = get_pdf_link(self.doctype, self.name)
                pdf_link = f"{frappe.utils.get_url()}{link}&key={key}"
                header.update({"example": {"header_handle": [pdf_link]}})
            else:
                # Use stored media_id
                header.update({"example": {"header_handle": [self._media_id]}})

        return header


@frappe.whitelist()
def fetch():
    """Fetch templates from Meta."""
    settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
    
    try:
        response = make_whatsapp_request(
            "GET",
            f"{settings.version}/{settings.business_id}/message_templates",
            settings=settings
        )
        templates = response.json().get("data", [])
        
        templates_count = 0
        updated_count = 0
        
        for template in templates:
            # set flag to insert or update
            flags = 1
            if frappe.db.exists("WhatsApp Templates", {"actual_name": template["name"]}):
                doc = frappe.get_doc("WhatsApp Templates", {"actual_name": template["name"]})
                updated_count += 1
            else:
                flags = 0
                doc = frappe.new_doc("WhatsApp Templates")
                doc.template_name = template["name"]
                doc.actual_name = template["name"]
                templates_count += 1

            doc.status = template["status"]
            doc.language_code = template["language"]
            doc.category = template["category"]
            doc.id = template["id"]

            # update components
            for component in template["components"]:
                # update header
                if component["type"] == "HEADER":
                    doc.header_type = component["format"]
                    # if format is text update sample text
                    if component["format"] == "TEXT":
                        doc.header = component["text"]
                # Update footer text
                elif component["type"] == "FOOTER":
                    doc.footer = component["text"]
                # update template text
                elif component["type"] == "BODY":
                    doc.template = component["text"]
                    if component.get("example"):
                        doc.sample_values = ",".join(
                            component["example"]["body_text"][0]
                        )

            # if document exists update else insert
            if flags:
                doc.db_update()
            else:
                doc.db_insert()
            frappe.db.commit()
        
        return {
            "status": "success",
            "message": frappe._("Templates synchronized successfully. Added {0} new, updated {1} existing.").format(
                templates_count, 
                updated_count
            )
        }
    except Exception as e:
        return {
            "status": "error",
            "message": frappe._("Error synchronizing templates: {0}").format(str(e))
        }
