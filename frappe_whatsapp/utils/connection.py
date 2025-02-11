from urllib.parse import urlparse
import frappe
import dns.resolver

def get_connection_config(settings=None):
    """
    Get connection configuration based on WhatsApp Settings
    Args:
        settings (Document): WhatsApp Settings document (optional)
    Returns:
        dict: Configuration for requests (verify, proxies, headers)
    """
    if not settings:
        settings = frappe.get_doc("WhatsApp Settings", "WhatsApp Settings")
        
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
            if settings.proxy_username and settings.proxy_password:
                scheme = proxy_url.split('://')[0]
                remaining = proxy_url.split('://')[1]
                proxy_url = f"{scheme}://{settings.proxy_username}:{settings.proxy_password}@{remaining}"
            
            config['proxies'] = {
                'http': proxy_url,
                'https': proxy_url
            }
    
    return config

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