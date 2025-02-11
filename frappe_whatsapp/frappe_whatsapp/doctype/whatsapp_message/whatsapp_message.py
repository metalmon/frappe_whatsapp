# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import json
import frappe
from frappe.model.document import Document
from frappe_whatsapp.utils.connection import make_whatsapp_request


class WhatsAppMessage(Document):
    """Send whats app messages."""

    def before_insert(self):
        """Send message."""
        if hasattr(self, "flags") and self.flags.skip_before_insert:
            return
            
        if self.type == "Outgoing":
            try:
                # For template messages
                if self.template:  # Simplified condition
                    self.message_type = "Template"
                    if not self.message_id:  # Only send if not already sent
                        self.send_template()
                    return
                
                # For non-template messages
                if not self.message and self.content_type == "text":
                    frappe.throw(_("Message text is required for non-template messages"))
                
                # Set message type based on content type
                self.message_type = "Manual"
                
                if self.attach and not self.attach.startswith("http"):
                    link = frappe.utils.get_url() + "/" + self.attach
                else:
                    link = self.attach

                data = {
                    "messaging_product": "whatsapp",
                    "to": self.format_number(self.to),
                    "type": self.content_type,
                }
                
                if self.is_reply and self.reply_to_message_id:
                    data["context"] = {"message_id": self.reply_to_message_id}
                    
                if self.content_type in ["document", "image", "video"]:
                    data[self.content_type.lower()] = {
                        "link": link,
                        "caption": self.message,
                    }
                elif self.content_type == "reaction":
                    data["reaction"] = {
                        "message_id": self.reply_to_message_id,
                        "emoji": self.message,
                    }
                elif self.content_type == "text":
                    data["text"] = {"preview_url": True, "body": self.message}
                elif self.content_type == "audio":
                    data["audio"] = {"link": link}

                self.notify(data)
                self.status = "Success"
                
            except Exception as e:
                self.status = "Failed"
                frappe.throw(_("Failed to send message: {0}").format(str(e)))

    def send_template(self):
        """Send template."""
        try:
            template = frappe.get_doc("WhatsApp Templates", self.template)
            data = {
                "messaging_product": "whatsapp",
                "to": self.format_number(self.to),
                "type": "template",
                "template": {
                    "name": template.actual_name or template.template_name,
                    "language": {"code": template.language_code},
                    "components": [],
                },
            }

            if template.sample_values:
                field_names = template.field_names.split(",") if template.field_names else template.sample_values.split(",")
                parameters = []
                template_parameters = []

                ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
                for field_name in field_names:
                    value = ref_doc.get_formatted(field_name.strip())

                    parameters.append({"type": "text", "text": value})
                    template_parameters.append(value)

                self.template_parameters = json.dumps(template_parameters)

                data["template"]["components"].append(
                    {
                        "type": "body",
                        "parameters": parameters,
                    }
                )

            if template.header_type and template.sample:
                field_names = template.sample.split(",")
                header_parameters = []
                template_header_parameters = []

                ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
                for field_name in field_names:
                    value = ref_doc.get_formatted(field_name.strip())
                    
                    header_parameters.append({"type": "text", "text": value})
                    template_header_parameters.append(value)

                self.template_header_parameters = json.dumps(template_header_parameters)

                data["template"]["components"].append({
                    "type": "header",
                    "parameters": header_parameters,
                })

            self.notify(data)
            self.status = "Success"
        except Exception as e:
            self.status = "Failed"
            frappe.throw(f"Failed to send template message: {str(e)}")

    def notify(self, data):
        """Send WhatsApp message using base connection method."""
        try:
            settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
            response = make_whatsapp_request(
                "POST",
                f"{settings.version}/{settings.phone_id}/messages",
                settings=settings,
                data=data
            )
            self.message_id = response.json()["messages"][0]["id"]
        except Exception as e:
            frappe.get_doc({
                "doctype": "WhatsApp Notification Log",
                "template": "Text Message",
                "meta_data": {
                    "error": str(e),
                    "request_data": frappe.utils.mask_sensitive_data(str(data)),
                    "response": frappe.utils.mask_sensitive_data(getattr(e, 'response', None) and e.response.text)
                }
            }).insert(ignore_permissions=True)
            raise

    def format_number(self, number):
        """Format number."""
        if number.startswith("+"):
            number = number[1:]
        return number



def on_doctype_update():
    frappe.db.add_index("WhatsApp Message", ["reference_doctype", "reference_name"])


@frappe.whitelist()
def send_template(to, reference_doctype, reference_name, template):
    """Create WhatsApp message and enqueue sending."""
    try:
        doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": to,
            "type": "Outgoing",
            "message_type": "Template",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "content_type": "text",
            "template": template,
            "status": "Queued"
        })
        
        # Save without triggering before_insert
        doc.flags.skip_before_insert = True
        doc.insert(ignore_permissions=True)
        
        # Enqueue the sending task
        frappe.enqueue(
            method="frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message.process_whatsapp_message",
            queue="now",
            timeout=300,
            message_id=doc.name,
            now=True
        )
        return doc.name
    except Exception as e:
        frappe.log_error("WhatsApp Message Creation Error", e)
        raise e

def process_whatsapp_message(message_id):
    """Background job to process and send WhatsApp message."""
    try:
        doc = frappe.get_doc("WhatsApp Message", message_id)
        if doc.status != "Queued":
            return
            
        doc.send_template()
        doc.status = "Success"
        doc.save(ignore_permissions=True)
    except Exception as e:
        frappe.log_error("WhatsApp Message Processing Error", e)
        if frappe.db.exists("WhatsApp Message", message_id):
            frappe.db.set_value("WhatsApp Message", message_id, "status", "Failed", update_modified=False)
