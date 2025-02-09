frappe.provide("frappe_whatsapp");

/**
 * Get WhatsApp DocTypes with proper site isolation
 * @returns {Promise} Promise that resolves with list of DocTypes
 */
frappe_whatsapp.get_doctypes = function() {
	return frappe.call({
		method: "frappe_whatsapp.api.get_whatsapp_doctypes",
		callback: function(r) {
			if (r.message) {
				return r.message;
			}
		}
	});
};

// Function to show WhatsApp send dialog
frappe_whatsapp.show_send_dialog = function(frm) {
	let fields = [
		{
			label: __("To"),
			fieldtype: "Data",
			fieldname: "to",
			reqd: 1,
			description: __("Mobile number with country code")
		},
		{
			label: __("Template"),
			fieldtype: "Link",
			fieldname: "template",
			options: "WhatsApp Templates",
			reqd: 1,
			get_query: function() {
				return {
					filters: { 
						"for_doctype": frm.doc.doctype 
					}
				};
			}
		}
	];

	let dialog = new frappe.ui.Dialog({
		title: __("Send WhatsApp Message"),
		fields: fields,
		primary_action_label: __("Send"),
		primary_action: function(values) {
			dialog.disable_primary_action();
			frappe.call({
				method: "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_message.whatsapp_message.send_template",
				args: {
					to: values.to,
					template: values.template,
					reference_doctype: frm.doc.doctype,
					reference_name: frm.doc.name
				},
				callback: function(r) {
					dialog.hide();
					if (r.message) {
						frappe.show_alert({
							message: __("WhatsApp message queued for sending"),
							indicator: 'blue'
						});
						// Start checking message status
						check_message_status(r.message);
					}
				},
				error: function(r) {
					dialog.enable_primary_action();
					frappe.show_alert({
						message: __("Failed to queue WhatsApp message"),
						indicator: 'red'
					});
				}
			});
		}
	});
	dialog.show();
};

// Add WhatsApp button to forms
frappe.ui.form.on('*', {
	refresh: function(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('Send WhatsApp'), function() {
				frappe_whatsapp.show_send_dialog(frm);
			});
		}
	}
});

function check_message_status(message_id) {
	frappe.call({
		method: 'frappe.client.get_value',
		args: {
			doctype: 'WhatsApp Message',
			filters: { name: message_id },
			fieldname: 'status'
		},
		callback: function(r) {
			if (r.message && r.message.status) {
				const status = r.message.status;
				if (status === 'Success') {
					frappe.show_alert({
						message: __("WhatsApp message sent successfully"),
						indicator: 'green'
					});
				} else if (status === 'Failed') {
					frappe.show_alert({
						message: __("Failed to send WhatsApp message"),
						indicator: 'red'
					});
				} else if (status === 'Queued') {
					// Check again after 5 seconds
					setTimeout(() => check_message_status(message_id), 5000);
				}
			}
		}
	});
}