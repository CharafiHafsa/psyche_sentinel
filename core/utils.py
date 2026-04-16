import logging
from ldap3 import Server, Connection, ALL, SUBTREE, Tls
from ldap3.core.exceptions import LDAPBindError, LDAPSocketOpenError, LDAPException
from django.db import transaction
import ssl
from .models import LDAPConfiguration, Employee

# Set up logging so you can see technical errors in your terminal, without showing them to the user
logger = logging.getLogger(__name__)

def perform_ldap_sync():
    """
    Connects to Active Directory, extracts employee data securely, 
    and updates the local database.
    """
    # 3. LDAP Configuration (Dynamic, not hardcoded)
    config = LDAPConfiguration.objects.first()
    if not config:
        return {"success": False, "error": "LDAP configuration not found."}

    # 1. Connection & Security (Handling VirtualBox Self-Signed Certs)
    # NOTE: For production, validate=ssl.CERT_REQUIRED. For your VM, CERT_NONE is needed.
    tls_config = Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLSv1_2)
    use_ssl = True if config.port == 636 else False

    try:
        server = Server(
            config.server_ip, 
            port=config.port, 
            use_ssl=use_ssl, 
            tls=tls_config, 
            get_info=ALL,
            connect_timeout=10 # Prevent hanging if server is down
        )

        # 2. Authentication (Bind)
        # Using the read-only credentials from the database
        conn = Connection(server, user=config.bind_dn, password=config.bind_password, auto_bind=True)

    except LDAPBindError:
        logger.error(f"LDAP Bind Failed for user: {config.bind_dn}")
        return {"success": False, "error": "Authentication failed. Check your Service Account credentials."}
    except LDAPSocketOpenError:
        logger.error(f"Cannot reach LDAP server at {config.server_ip}:{config.port}")
        return {"success": False, "error": "Connection timed out. Ensure the server IP is correct and reachable."}
    except Exception as e:
        logger.error(f"Unexpected LDAP Connection Error: {str(e)}")
        return {"success": False, "error": "An unexpected network error occurred."}

    # 4. Search & Filtering
    # This specific filter ensures we only get active human users (no computers, no disabled accounts)
    # userAccountControl:1.2.840.113556.1.4.803:=2 is the AD flag for 'Account Disabled'
    search_filter = '(&(objectClass=user)(objectCategory=person)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))'
    
    # 6. Data Minimization (Legal)
    # We explicitly request ONLY the exact 4 attributes we need. Nothing else leaves the server.
    attributes_to_retrieve = ['sAMAccountName', 'cn', 'mail', 'department']

    try:
        conn.search(
            search_base=config.base_ou,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=attributes_to_retrieve,
            size_limit=1000 # Prevent pulling millions of records if configured poorly
        )

        users_extracted = 0

        # We extract just the username from the bind input (e.g., gets 'LDAP_Bind' from 'LDAP_Bind@corp.local')
        bind_username = config.bind_dn.split('@')[0] if '@' in config.bind_dn else config.bind_dn.split('\\')[-1]

        with transaction.atomic():
            for entry in conn.entries:
                sam_account = getattr(entry, 'sAMAccountName', None)
                if not sam_account:
                    continue 
                    
                sam_account_val = sam_account.value

                # ---> THE NEW CHECK <---
                # If this user is the service account, skip it entirely
                if sam_account_val.lower() == bind_username.lower():
                    continue
                
                full_name_val = getattr(entry, 'cn', None)
                full_name_val = full_name_val.value if full_name_val else "Unknown Name"
                
                email_val = getattr(entry, 'mail', None)
                email_val = email_val.value if email_val else "no-reply@enterprise.local"
                
                department_val = getattr(entry, 'department', None)
                department_val = department_val.value if department_val else "Unassigned"

                # Save or update the employee in your database
                Employee.objects.update_or_create(
                    sam_account_name=sam_account_val,
                    defaults={
                        'full_name': full_name_val,
                        'email': email_val,
                        'department': department_val,
                    }
                )
                users_extracted += 1

        conn.unbind() # Close the connection securely
        return {"success": True, "count": users_extracted}

    except LDAPException as e:
        logger.error(f"LDAP Search Failed: {str(e)}")
        return {"success": False, "error": "Failed to read the directory. Verify the Base OU is correct."}