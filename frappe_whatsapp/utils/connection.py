from urllib.parse import urlparse, quote
import frappe
import dns.resolver
import base64
import requests
from frappe import _
import re

def get_connection_config(settings=None):
    """
    Get connection configuration based on WhatsApp Settings
    Args:
        settings (Document): WhatsApp Settings document (optional)
    Returns:
        dict: Configuration for requests (verify, proxies, headers)
    """
    try:
        if frappe.conf.developer_mode:
            print("\n" + "="*50)
            print("PROXY DEBUG: Starting get_connection_config")
            
            if not settings:
                settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
                print("\nSettings loaded:")
                print(f"Connection Type: {settings.connection_type}")
                print(f"Proxy URL: {mask_sensitive_data(settings.proxy_url)}")
                print(f"Proxy Username: {mask_sensitive_data(settings.proxy_username)}")
                
        config = {
            'verify': True,
            'proxies': None,
            'headers': {}
        }
        
        if settings.connection_type == 'Custom DNS':
            config['verify'] = False
            config['headers']['Host'] = urlparse(settings.url).hostname
            
        elif settings.connection_type == 'Proxy':
            if frappe.conf.developer_mode:
                print("\nProxy configuration started:")
                print(f"Proxy URL from settings: {mask_sensitive_data(settings.proxy_url)}")
            
            if settings.proxy_url:
                proxy_url = settings.proxy_url.strip()
                
                # Format proxy URL with authentication if credentials provided
                if settings.proxy_username and settings.proxy_password:
                    try:
                        if frappe.conf.developer_mode:
                            print("\nSetting up proxy authentication:")
                        decrypted_password = settings.get_password('proxy_password')
                        if frappe.conf.developer_mode:
                            print("Password decrypted successfully")
                        
                        # Create proxy URL with embedded credentials
                        parsed = urlparse(proxy_url)
                        proxy_url = f"{parsed.scheme}://{settings.proxy_username}:{decrypted_password}@{parsed.netloc}"
                        
                        if frappe.conf.developer_mode:
                            print("Auth configuration completed:")
                            print(f"Username: {mask_sensitive_data(settings.proxy_username)}")
                            print("Proxy URL configured with auth")
                        
                    except Exception as e:
                        if frappe.conf.developer_mode:
                            print(f"\nERROR in proxy auth configuration: {mask_sensitive_data(str(e))}")
                
                config['proxies'] = {
                    'http': proxy_url,
                    'https': proxy_url
                }
                if frappe.conf.developer_mode:
                    print(f"Proxy URLs set: {mask_sensitive_data(str(config['proxies']))}")
        
        if frappe.conf.developer_mode:
            print("\nFinal configuration:")
            print("Proxies: Configured")
            print(f"Headers: {mask_sensitive_data(str(config['headers']))}")
            print("="*50 + "\n")
        return config
        
    except Exception as e:
        if frappe.conf.developer_mode:
            print(f"\nERROR in get_connection_config: {mask_sensitive_data(str(e))}")
            print("="*50 + "\n")
        raise

def get_url(url, settings=None):
    """
    Get resolved URL if using Custom DNS
    Args:
        url (str): Original URL
        settings (Document): WhatsApp Settings document (optional)
    Returns:
        str: Resolved URL if using Custom DNS, original URL otherwise
    """
    if not settings:
        settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
        
    if settings.connection_type != 'Custom DNS':
        return url
        
    try:
        resolver = dns.resolver.Resolver()
        nameservers = []
        if settings.primary_dns:
            nameservers.append(settings.primary_dns)
        if settings.secondary_dns:
            nameservers.append(settings.secondary_dns)
        resolver.nameservers = nameservers
        
        parsed = urlparse(url)
        domain = parsed.netloc
        answers = resolver.resolve(domain, 'A')
        ip = answers[0].address
        return url.replace(domain, ip)
    except Exception as e:
        frappe.log_error(f"DNS Resolution failed: {str(e)}")
        return url

def create_whatsapp_session():
    """Create a configured WhatsApp API session with retries and security settings"""
    session = requests.Session()
    
    # Configure session with retries and security settings
    adapter = requests.adapters.HTTPAdapter(
        max_retries=3,
        pool_connections=1,
        pool_maxsize=3,
        pool_block=True
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    return session

def make_whatsapp_request(method, endpoint, settings=None, data=None, files=None, params=None, timeout=30):
    """
    Make a request to WhatsApp API with proper configuration
    Args:
        method (str): HTTP method (GET, POST, DELETE)
        endpoint (str): API endpoint
        settings (Document): WhatsApp Settings document (optional)
        data (dict): Request data/payload
        files (dict): Files to upload
        params (dict): URL parameters
        timeout (int): Request timeout in seconds
    Returns:
        requests.Response: Response from the API
    """
    if not settings:
        settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
    
    config = get_connection_config(settings)
    token = settings.get_password("token")
    
    # Base headers for WhatsApp API
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }
    
    # Update with headers from config (including proxy headers)
    headers.update(config.get('headers', {}))
    
    # Clean up the URL to avoid double slashes
    base_url = settings.url.rstrip('/')
    endpoint = endpoint.lstrip('/')
    url = get_url(f"{base_url}/{endpoint}", settings)
    
    if frappe.conf.developer_mode:
        print("\nMaking WhatsApp API request:")
        print(f"Method: {method}")
        print(f"URL: {mask_sensitive_data(url)}")
        print(f"Headers: {mask_sensitive_data(str(headers))}")
        print(f"Data: {mask_sensitive_data(str(data))}")
        print(f"Params: {mask_sensitive_data(str(params))}")
        print(f"Proxy config: {mask_sensitive_data(str(config['proxies']))}")
    
    try:
        session = create_whatsapp_session()
        
        response = session.request(
            method=method,
            url=url,
            headers=headers,
            json=data if data and not files else None,
            data=data if files else None,
            files=files,
            params=params,
            timeout=timeout,
            verify=config['verify'],
            proxies=config['proxies'],
            auth=config.get('proxy_auth')
        )
        
        if frappe.conf.developer_mode:
            print(f"\nResponse received:")
            print(f"Status code: {response.status_code}")
            print(f"Response headers: {mask_sensitive_data(str(dict(response.headers)))}")
            print(f"Response text: {mask_sensitive_data(response.text[:500])}")
        
        response.raise_for_status()
        return response
        
    except requests.exceptions.RequestException as e:
        if frappe.conf.developer_mode:
            print(f"\nRequest failed:")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {mask_sensitive_data(str(e))}")
            if hasattr(e, 'response'):
                print(f"Response status: {e.response.status_code if e.response else 'None'}")
                print(f"Response headers: {mask_sensitive_data(str(dict(e.response.headers)) if e.response else 'None')}")
                print(f"Response text: {mask_sensitive_data(e.response.text[:500] if e.response else 'None')}")
        handle_request_error(e)
    finally:
        if 'session' in locals():
            session.close()

def handle_request_error(error):
    """
    Handle request errors in a consistent way
    Args:
        error (requests.exceptions.RequestException): The error to handle
    Raises:
        frappe.ValidationError: With appropriate error message
    """
    error_msg = str(error)
    if hasattr(error, 'response') and error.response:
        try:
            error_data = error.response.json()
            if isinstance(error_data, dict) and "error" in error_data:
                error_msg = error_data["error"].get("error_user_msg") or error_data["error"].get("message", str(error))
        except Exception:
            pass
    
    frappe.throw(
        msg=_("WhatsApp API request failed: {}").format(error_msg),
        title=_("API Error")
    )

# Utility functions for common WhatsApp API operations
def get_media(media_id, settings=None):
    """Get media from WhatsApp API"""
    return make_whatsapp_request("GET", f"{settings.version}/{media_id}/", settings=settings)

def get_media_url(media_id, settings=None):
    """Get media URL and download media content"""
    media_info = get_media(media_id, settings)
    media_data = media_info.json()
    return make_whatsapp_request("GET", media_data.get("url"), settings=settings)

def get_templates(settings=None):
    """Get templates from WhatsApp API"""
    if not settings:
        settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
    return make_whatsapp_request(
        "GET",
        f"{settings.version}/{settings.business_id}/message_templates",
        settings=settings
    )

def create_template(data, settings=None):
    """Create a new template"""
    return make_whatsapp_request(
        "POST",
        f"{settings.version}/{settings.business_id}/message_templates",
        data=data,
        settings=settings
    )

def update_template(template_id, data, settings=None):
    """Update an existing template"""
    return make_whatsapp_request(
        "POST",
        f"{settings.version}/{template_id}",
        data=data,
        settings=settings
    )

def delete_template(template_name, settings=None):
    """Delete a template"""
    return make_whatsapp_request(
        "DELETE",
        f"{settings.version}/{settings.business_id}/message_templates",
        params={"name": template_name},
        settings=settings
    )

def upload_media(file_data, file_type, settings=None):
    """Upload media to WhatsApp"""
    return make_whatsapp_request(
        "POST",
        f"{settings.version}/{settings.app_id}/uploads",
        data={
            'file_length': len(file_data),
            'file_type': file_type,
            'messaging_product': 'whatsapp'
        },
        settings=settings
    )

def mask_sensitive_data(text):
    """Mask sensitive data in text strings"""
    if not text:
        return text
    
    # Mask auth tokens
    text = re.sub(r'Bearer\s+[A-Za-z0-9._-]+', 'Bearer ***', text)
    # Mask Basic auth
    text = re.sub(r'Basic\s+[A-Za-z0-9+/=]+', 'Basic ***', text)
    # Mask passwords in URLs
    text = re.sub(r':[^@/]+@', ':***@', text)
    # Mask phone numbers (7-15 digits)
    text = re.sub(r'\b\d{7,15}\b', '***', text)
    # Mask IP addresses
    text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '***', text)
    # Mask API keys and tokens
    text = re.sub(r'key-[a-zA-Z0-9]+', 'key-***', text)
    text = re.sub(r'token[=:]\s*[a-zA-Z0-9]+', 'token=***', text)
    # Mask usernames
    text = re.sub(r'username["\']?\s*[:=]\s*["\']?[^"\',\s]+', 'username=***', text)
    
    return text 