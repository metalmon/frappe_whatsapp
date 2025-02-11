// Copyright (c) 2022, Shridhar Patil and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Settings', {
	refresh: function(frm) {
		// Add "Test Connection" button
		frm.add_custom_button(__('Test Connection'), function() {
			// Show loading state
			frm.disable_save();
			frappe.dom.freeze(__('Testing connection...'));

			// Call the test_connection method
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_settings.whatsapp_settings.test_connection',
				callback: function(r) {
					frappe.dom.unfreeze();
					frm.enable_save();
					
					if (!r.exc) {
						// Create a formatted message for the dialog
						let message = '<div style="font-family: monospace;">';
						
						// Main Domain Status
						message += '<div style="margin-bottom: 10px;">';
						message += '<strong>Main Domain (graph.facebook.com):</strong><br>';
						if (r.message.main_domain.success) {
							message += `✓ Connected (Status: ${r.message.main_domain.status_code})`;
							if (r.message.main_domain.resolved_url) {
								message += `<br>Using resolved URL: ${r.message.main_domain.resolved_url}`;
							}
							message += '</div>';
						} else {
							message += `✗ Failed: ${r.message.main_domain.error}`;
							if (r.message.main_domain.resolved_url) {
								message += `<br>Attempted resolved URL: ${r.message.main_domain.resolved_url}`;
							}
							message += '</div>';
						}
						
						// Templates Endpoint Status
						message += '<div style="margin-bottom: 10px;">';
						message += '<strong>Templates Endpoint:</strong><br>';
						if (r.message.templates_endpoint.success) {
							message += `✓ Connected (Status: ${r.message.templates_endpoint.status_code})`;
							if (r.message.templates_endpoint.resolved_url) {
								message += `<br>Using resolved URL: ${r.message.templates_endpoint.resolved_url}`;
							}
							message += '</div>';
						} else {
							message += `✗ Failed: ${r.message.templates_endpoint.error}`;
							if (r.message.templates_endpoint.resolved_url) {
								message += `<br>Attempted resolved URL: ${r.message.templates_endpoint.resolved_url}`;
							}
							message += '</div>';
						}
						
						message += '</div>';
						
						// Show results dialog
						frappe.msgprint({
							title: __('Connection Test Results'),
							indicator: 'blue',
							message: message
						});
						
						// Reload the form to get latest timestamp
						frm.reload_doc();
					}
				}
			});
		}, __('Actions'));
	},

	connection_type: function(frm) {
		if(frm.doc.connection_type == 'Custom DNS') {
			frappe.msgprint({
				title: __('Security Warning'),
				indicator: 'orange',
				message: __('Using custom DNS will disable SSL certificate verification. This may pose security risks. Use this feature only if you understand the implications.')
			});
		}
	},

});
