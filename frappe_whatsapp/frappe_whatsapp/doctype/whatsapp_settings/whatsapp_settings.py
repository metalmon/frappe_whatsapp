# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import requests
import dns.resolver
from urllib.parse import urlparse

class WhatsAppSettings(Document):
	def validate(self):
		pass

def get_url(url, settings):
	"""
	Resolve domain using custom DNS servers if enabled
	Args:
		url (str): Original URL to resolve
		settings (Document): WhatsApp Settings document
	Returns:
		str: URL with resolved IP if custom DNS is enabled, original URL otherwise
	"""
	if not settings.connection_type:
		return url

	try:
		# Parse the URL to get the domain
		parsed = urlparse(url)
		domain = parsed.netloc
		
		# Configure custom DNS resolver
		resolver = dns.resolver.Resolver()
		nameservers = []
		if settings.primary_dns:
			nameservers.append(settings.primary_dns)
		if settings.secondary_dns:
			nameservers.append(settings.secondary_dns)
		resolver.nameservers = nameservers

		# Resolve domain to IP
		answers = resolver.resolve(domain, 'A')
		ip = answers[0].address

		# Replace domain with IP in URL
		resolved_url = url.replace(domain, ip)
		return resolved_url
	except Exception as e:
		frappe.log_error(f"DNS Resolution failed: {str(e)}")
		return url  # Fallback to original URL if resolution fails

def get_connection_config(settings):
	"""
	Get connection configuration based on settings
	Args:
		settings (Document): WhatsApp Settings document
	Returns:
		dict: Configuration for requests (verify, proxies, etc.)
	"""
	config = {
		'verify': True,
		'proxies': None,
		'headers': {}
	}
	
	if settings.connection_type == 'Custom DNS':
		config['verify'] = False
		config['headers']['Host'] = 'graph.facebook.com'
		
	elif settings.connection_type == 'Proxy':
		if settings.proxy_url:
			proxy_url = settings.proxy_url
			# Add authentication if provided
			if settings.proxy_username and settings.proxy_password:
				# Extract scheme and remaining URL parts
				scheme = proxy_url.split('://')[0]
				remaining = proxy_url.split('://')[1]
				proxy_url = f"{scheme}://{settings.proxy_username}:{settings.proxy_password}@{remaining}"
			
			config['proxies'] = {
				'http': proxy_url,
				'https': proxy_url
			}
	
	return config

@frappe.whitelist()
def test_connection():
	"""Test connection to different Meta endpoints using configured connection method."""
	settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
	token = get_decrypted_password("WhatsApp Settings", "WhatsApp Settings", "token", raise_exception=False)
	
	if not token:
		return {
			"success": False,
			"message": "Token is not configured"
		}
		
	# Configure session with retries
	session = requests.Session()
	retries = requests.adapters.Retry(
		total=3,
		backoff_factor=1,
		status_forcelist=[408, 429, 500, 502, 503, 504]
	)
	session.mount('https://', requests.adapters.HTTPAdapter(max_retries=retries))
	
	# Get connection configuration
	config = get_connection_config(settings)
	
	headers = {
		"authorization": f"Bearer {token}",
		"content-type": "application/json"
	}
	headers.update(config['headers'])
	
	results = {}
	
	# Test main domain connectivity
	main_url = 'https://graph.facebook.com'
	if settings.connection_type == 'Custom DNS':
		main_url = get_url(main_url, settings)
		
	try:
		r = session.get(
			main_url, 
			headers=headers, 
			timeout=15,
			verify=config['verify'],
			proxies=config['proxies']
		)
		results['main_domain'] = {
			"success": True,
			"status_code": r.status_code,
			"connection_type": settings.connection_type,
			"resolved_url": main_url if settings.connection_type == 'Custom DNS' else None
		}
	except Exception as e:
		results['main_domain'] = {
			"success": False,
			"error": str(e),
			"connection_type": settings.connection_type,
			"resolved_url": main_url if settings.connection_type == 'Custom DNS' else None
		}

	# Test templates endpoint
	templates_url = f"{settings.url}/{settings.version}/{settings.business_id}/message_templates"
	if settings.connection_type == 'Custom DNS':
		templates_url = get_url(templates_url, settings)
		
	try:
		r = session.get(
			templates_url, 
			headers=headers, 
			timeout=15,
			verify=config['verify'],
			proxies=config['proxies']
		)
		results['templates_endpoint'] = {
			"success": r.status_code == 200,
			"status_code": r.status_code,
			"connection_type": settings.connection_type,
			"resolved_url": templates_url if settings.connection_type == 'Custom DNS' else None
		}
	except Exception as e:
		results['templates_endpoint'] = {
			"success": False,
			"error": str(e),
			"connection_type": settings.connection_type,
			"resolved_url": templates_url if settings.connection_type == 'Custom DNS' else None
		}
	
	return results
