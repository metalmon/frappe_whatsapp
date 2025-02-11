"""Webhook."""
import frappe
import json
import requests
import time
from werkzeug.wrappers import Response
import frappe.utils
from frappe_whatsapp.utils.connection import get_connection_config, get_url, make_whatsapp_request


@frappe.whitelist(allow_guest=True)
def webhook():
	"""Meta webhook."""
	if frappe.request.method == "GET":
		return get()
	return post()


def get():
	"""Get."""
	hub_challenge = frappe.form_dict.get("hub.challenge")
	webhook_verify_token = frappe.db.get_single_value(
		"WhatsApp Settings", "webhook_verify_token"
	)

	if frappe.form_dict.get("hub.verify_token") != webhook_verify_token:
		frappe.throw("Verify token does not match")

	return Response(hub_challenge, status=200)

def post():
	"""Handle incoming webhook POST requests."""
	data = frappe.local.form_dict
	frappe.get_doc({
		"doctype": "WhatsApp Notification Log",
		"template": "Webhook",
		"meta_data": json.dumps(data)
	}).insert(ignore_permissions=True)

	messages = []
	try:
		messages = data["entry"][0]["changes"][0]["value"].get("messages", [])
	except KeyError:
		messages = data["entry"]["changes"][0]["value"].get("messages", [])

	if messages:
		for message in messages:
			message_type = message['type']
			is_reply = True if message.get('context') else False
			reply_to_message_id = message['context']['id'] if is_reply else None
			
			message_doc = frappe.get_doc({
				"doctype": "WhatsApp Message",
				"type": "Incoming",
				"from": message['from'],
				"message_id": message['id'],
				"reply_to_message_id": reply_to_message_id,
				"is_reply": is_reply,
				"content_type": message_type
			})

			if message_type == 'text':
				message_doc.message = message['text']['body']
			elif message_type == 'reaction':
				message_doc.message = message['reaction']['emoji']
				message_doc.reply_to_message_id = message['reaction']['message_id']
			elif message_type == 'interactive':
				message_doc.message = message['interactive']['nfm_reply']['response_json']
			elif message_type == "button":
				message_doc.message = message['button']['text']
			elif message_type in ['image', 'document', 'video', 'audio']:
				# Handle media messages
				try:
					settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
					media_id = message[message_type]['id']
					
					# Get media info
					media_info = make_whatsapp_request(
						"GET",
						f"{settings.version}/{media_id}",
						settings=settings
					).json()
					
					# Download media content
					media_content = make_whatsapp_request(
						"GET",
						media_info['url'],
						settings=settings
					).content
					
					# Get filename from content disposition or use media ID
					file_name = f"{media_id}.{message_type}"
					if message[message_type].get('filename'):
						file_name = message[message_type]['filename']
					
					# Create file attachment
					file = frappe.get_doc({
						"doctype": "File",
						"file_name": file_name,
						"attached_to_doctype": "WhatsApp Message",
						"attached_to_name": message_doc.name,
						"content": media_content,
						"attached_to_field": "attach"
					}).save(ignore_permissions=True)
					
					message_doc.attach = file.file_url
					message_doc.message = message[message_type].get(message_type, "")
				except Exception as e:
					frappe.log_error(f"WhatsApp Media Download Error: {str(e)}")
					message_doc.message = f"Error downloading media: {str(e)}"
			else:
				message_doc.message = message[message_type].get(message_type, "")
			
			message_doc.insert(ignore_permissions=True)
	else:
		changes = None
		try:
			changes = data["entry"][0]["changes"][0]
		except KeyError:
			changes = data["entry"]["changes"][0]
		update_status(changes)
	return

def update_status(data):
	"""Update template status from webhook."""
	if data.get("field") == "message_template_status_update":
		template_name = data["value"].get("message_template_name")
		status = data["value"].get("message_template_status")
		
		if template_name and status:
			if frappe.db.exists("WhatsApp Templates", {"template_name": template_name}):
				frappe.db.set_value(
					"WhatsApp Templates",
					{"template_name": template_name},
					"status",
					status
				)
				frappe.db.commit()
	elif data.get("field") == "messages":
		message_id = data["value"].get("id")
		status = data["value"].get("status")
		
		if message_id and status:
			if frappe.db.exists("WhatsApp Message", {"message_id": message_id}):
				frappe.db.set_value(
					"WhatsApp Message",
					{"message_id": message_id},
					"status",
					status
				)
				frappe.db.commit()