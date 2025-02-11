frappe.listview_settings['WhatsApp Templates'] = {

	onload: function(listview) {
		listview.page.add_menu_item(__("Fetch templates from meta"), function() {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.fetch',
				freeze: true,
				freeze_message: __("Fetching templates from Meta..."),
				callback: function(res) {
					if (res.message) {
						let indicator = res.message.status === 'success' ? 'green' : 'red';
						
						frappe.show_alert({
							message: res.message.message,
							indicator: indicator
						});
						
						if (res.message.status === 'success') {
							listview.refresh();
						}
					}
				}
			});
		});
	}
};