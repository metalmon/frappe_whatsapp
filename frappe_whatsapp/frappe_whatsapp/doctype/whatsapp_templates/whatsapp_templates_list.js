frappe.listview_settings['WhatsApp Templates'] = {

	onload: function(listview) {
		listview.page.add_menu_item(__("Fetch templates from meta"), function() {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.fetch',
				freeze: true,
				freeze_message: __("Fetching templates from Meta..."),
				callback: function(res) {
					if (res.message) {
						// Check if it's an error message
						if (res.message.startsWith('Error:')) {
							// Error already shown via msgprint
						} else {
							frappe.show_alert({
								message: res.message,
								indicator: res.message.includes('Successfully') ? 'green' : 'yellow'
							});
						}
						listview.refresh();
					}
				},
				error: function(err) {
					frappe.show_alert({
						message: __("Failed to fetch templates. Please try again."),
						indicator: 'red'
					});
				}
			});
		});
	}
};