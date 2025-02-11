# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password
import requests
import dns.resolver
from urllib.parse import urlparse
import base64
import re
from frappe import _

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

def mask_sensitive_data(text, mask_char='*'):
	"""Mask sensitive data in text strings"""
	if not text:
		return text
	
	# Mask auth tokens
	text = re.sub(r'Bearer\s+[A-Za-z0-9._-]+', 'Bearer ' + mask_char * 8, text)
	# Mask Basic auth
	text = re.sub(r'Basic\s+[A-Za-z0-9+/=]+', 'Basic ' + mask_char * 8, text)
	# Mask passwords in URLs
	text = re.sub(r':[^@/]+@', ':' + mask_char * 8 + '@', text)
	
	return text

def validate_proxy_url(url):
	"""Validate proxy URL for security"""
	if not url:
		return
		
	parsed = urlparse(url)
	
	# Check scheme
	if parsed.scheme not in ('http', 'https', 'socks4', 'socks5'):
		frappe.throw(_('Invalid proxy protocol. Only http, https, socks4, and socks5 are allowed.'))
	
	# Check for suspicious characters
	suspicious_chars = re.compile(r'[<>\'"]')
	if suspicious_chars.search(url):
		frappe.throw(_('Proxy URL contains invalid characters.'))
	
	# Check port range
	if parsed.port and (parsed.port < 1 or parsed.port > 65535):
		frappe.throw(_('Invalid proxy port number.'))

def get_connection_config(settings):
	"""
	Get connection configuration based on settings
	Args:
		settings (Document): WhatsApp Settings document
	Returns:
		dict: Configuration for requests (verify, proxies, etc.)
	"""
	config = {
		'verify': True,  # Always verify SSL by default
		'proxies': None,
		'headers': {}
	}
	
	if settings.connection_type == 'Custom DNS':
		config['verify'] = True  # Force SSL verification for Custom DNS
		config['headers']['Host'] = 'graph.facebook.com'
		
	elif settings.connection_type == 'Proxy':
		if settings.proxy_url:
			# Validate proxy URL
			validate_proxy_url(settings.proxy_url)
			
			# Parse proxy URL
			proxy_url = settings.proxy_url.strip()
			
			# Determine proxy type and format URL
			if proxy_url.startswith(('socks4://', 'socks5://')):
				config['proxies'] = {
					'http': proxy_url,
					'https': proxy_url
				}
			else:
				# Handle HTTP proxy
				if not proxy_url.startswith(('http://', 'https://')):
					proxy_url = 'http://' + proxy_url
				
				# Remove any trailing slashes
				proxy_url = proxy_url.rstrip('/')
				
				# Extract host and port
				proxy_parts = proxy_url.split('://', 1)[1]
				if ':' in proxy_parts:
					proxy_host, proxy_port = proxy_parts.split(':')
				else:
					proxy_host = proxy_parts
					proxy_port = '80'
				
				# Format auth string if credentials are provided
				auth_string = ''
				if settings.proxy_username and settings.proxy_password:
					proxy_pass = settings.get_password('proxy_password')
					# Validate credentials
					if not all(c.isprintable() for c in settings.proxy_username + proxy_pass):
						frappe.throw(_('Proxy credentials contain invalid characters.'))
					auth_string = f"{settings.proxy_username}:{proxy_pass}@"
				
				# Construct proxy URLs
				http_proxy = f"http://{auth_string}{proxy_host}:{proxy_port}"
				https_proxy = http_proxy
				
				config['proxies'] = {
					'http': http_proxy,
					'https': https_proxy
				}
			
			print(f"\nProxy type detection:")
			print(f"Original URL: {mask_sensitive_data(settings.proxy_url)}")
			print(f"Configured proxies: {mask_sensitive_data(str(config['proxies']))}")
			
			# Add required headers for proxy
			config['headers'].update({
				'User-Agent': 'WhatsApp-API-Client',  # Use specific user agent
				'Accept': '*/*',
				'Accept-Encoding': 'gzip, deflate',
				'Connection': 'keep-alive',
				'Proxy-Connection': 'keep-alive'
			})
			
			# Add proxy authentication via header if credentials are provided
			if settings.proxy_username and settings.proxy_password:
				proxy_pass = settings.get_password('proxy_password')
				auth_string = f"{settings.proxy_username}:{proxy_pass}"
				auth_bytes = auth_string.encode('ascii')
				base64_auth = base64.b64encode(auth_bytes).decode('ascii')
				config['headers']['Proxy-Authorization'] = f'Basic {base64_auth}'
	
	return config

@frappe.whitelist()
def test_connection():
	"""Test connection to different Meta endpoints using configured connection method."""
	print("\n" + "="*50)
	print("WHATSAPP CONNECTION TEST - START")
	
	settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
	print("\nSettings loaded:")
	print(f"Connection Type: {settings.connection_type}")
	print(f"Proxy URL: {mask_sensitive_data(settings.proxy_url)}")
	print(f"Proxy Username: {settings.proxy_username}")
	
	token = get_decrypted_password("WhatsApp Settings", "WhatsApp Settings", "token", raise_exception=False)
	print(f"Token loaded: {'Yes' if token else 'No'}")
	
	if not token:
		print("Error: Token is not configured")
		return {
			"success": False,
			"message": "Token is not configured"
		}
	
	# Configure session with retries and security
	session = requests.Session()
	
	# Set secure TLS options
	session.mount('https://', requests.adapters.HTTPAdapter(
		max_retries=3,
		pool_connections=1,
		pool_maxsize=3,
		pool_block=True
	))
	
	print("\nSession configured with security settings")
	
	# Get connection configuration
	config = get_connection_config(settings)
	print("\nConnection configuration:")
	print(f"Proxies: {mask_sensitive_data(str(config['proxies']))}")
	print(f"Headers: {mask_sensitive_data(str(config['headers']))}")
	print(f"Verify SSL: {config['verify']}")
	
	headers = {
		"authorization": f"Bearer {token}",
		"content-type": "application/json"
	}
	headers.update(config['headers'])
	print(f"\nFinal request headers: {mask_sensitive_data(str(headers))}")
	
	results = {}
	
	# Test main domain connectivity
	main_url = 'https://graph.facebook.com'
	if settings.connection_type == 'Custom DNS':
		main_url = get_url(main_url, settings)
	
	print(f"\nTesting main domain: {main_url}")
	try:
		print("Making request to main domain...")
		print(f"Using proxies: {mask_sensitive_data(str(config['proxies']))}")
		print(f"Using headers: {mask_sensitive_data(str(headers))}")
		
		r = session.get(
			main_url, 
			headers=headers, 
			timeout=15,
			verify=config['verify'],
			proxies=config['proxies']
		)
		print(f"Response received:")
		print(f"Status code: {r.status_code}")
		print(f"Response headers: {dict(r.headers)}")
		print(f"Response text: {r.text[:500]}")
		
		results['main_domain'] = {
			"success": True,
			"status_code": r.status_code,
			"connection_type": settings.connection_type,
			"resolved_url": main_url if settings.connection_type == 'Custom DNS' else None
		}
	except requests.exceptions.SSLError as e:
		print(f"\nSSL verification failed:")
		print(f"Error: {str(e)}")
		results['main_domain'] = {
			"success": False,
			"error": "SSL certificate verification failed. Please check your SSL settings.",
			"connection_type": settings.connection_type
		}
	except requests.exceptions.RequestException as e:
		print(f"\nError during main domain request:")
		print(f"Error type: {type(e).__name__}")
		print(f"Error message: {str(e)}")
		
		if hasattr(e, 'response') and e.response:
			print(f"Error response details:")
			print(f"Status code: {e.response.status_code}")
			print(f"Headers: {dict(e.response.headers)}")
			print(f"Text: {e.response.text}")
		
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
	
	print(f"\nTesting templates endpoint: {templates_url}")
	try:
		print("Making request to templates endpoint...")
		r = session.get(
			templates_url, 
			headers=headers, 
			timeout=15,
			verify=config['verify'],
			proxies=config['proxies']
		)
		print(f"Response received:")
		print(f"Status code: {r.status_code}")
		print(f"Response headers: {dict(r.headers)}")
		print(f"Response text: {r.text[:500]}")
		
		results['templates_endpoint'] = {
			"success": r.status_code == 200,
			"status_code": r.status_code,
			"connection_type": settings.connection_type,
			"resolved_url": templates_url if settings.connection_type == 'Custom DNS' else None
		}
	except requests.exceptions.RequestException as e:
		print(f"\nError during templates request:")
		print(f"Error type: {type(e).__name__}")
		print(f"Error message: {str(e)}")
		
		if hasattr(e, 'response') and e.response:
			print(f"Error response details:")
			print(f"Status code: {e.response.status_code}")
			print(f"Headers: {dict(e.response.headers)}")
			print(f"Text: {e.response.text}")
		
		results['templates_endpoint'] = {
			"success": False,
			"error": str(e),
			"connection_type": settings.connection_type,
			"resolved_url": templates_url if settings.connection_type == 'Custom DNS' else None
		}
	
	print("\nWHATSAPP CONNECTION TEST - END")
	print("="*50 + "\n")
	return results
