"""
Encryption and decryption utilities for sensitive data.

This module provides functions to securely encrypt and decrypt sensitive data
using industry standard encryption algorithms.
"""
import base64
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Environment variables should be used in production
# This is a fallback for development only
DEFAULT_KEY = os.environ.get("ENCRYPTION_KEY", "qiH_h_dmAJHm0E3pP2Wg2sByJakF4mJDNpSUYaFGLbY=")
DEFAULT_SALT = os.environ.get("ENCRYPTION_SALT", "XVQ2BtyDx89bBrXl").encode()

# Cache the initialized Fernet instance for better performance
_fernet = None


def _get_fernet():
    """Get or initialize a Fernet cipher instance."""
    global _fernet
    if _fernet is None:
        # Use PBKDF2 to derive a secure key from the provided key and salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            iterations=100000,
        )
        
        # If the key is base64 encoded, use it directly, otherwise derive it
        try:
            key = base64.urlsafe_b64decode(DEFAULT_KEY)
            if len(key) != 32:  # Fernet requires a 32-byte key
                key = base64.urlsafe_b64encode(kdf.derive(DEFAULT_KEY.encode()))
        except Exception:
            # If key is not valid base64, derive a key
            key = base64.urlsafe_b64encode(kdf.derive(DEFAULT_KEY.encode()))
            
        _fernet = Fernet(key)
    return _fernet


def encrypt_data(data: str) -> str:
    """
    Encrypt a string value.
    
    Args:
        data: The string to encrypt
        
    Returns:
        Base64 encoded encrypted string
    """
    if not data:
        return ""
    
    fernet = _get_fernet()
    encrypted_data = fernet.encrypt(data.encode())
    return base64.urlsafe_b64encode(encrypted_data).decode()


def decrypt_data(encrypted_data: str) -> str:
    """
    Decrypt an encrypted string value.
    
    Args:
        encrypted_data: The encrypted string to decrypt
        
    Returns:
        Decrypted string or empty string if decryption fails
    """
    if not encrypted_data:
        return ""
    
    try:
        fernet = _get_fernet()
        decoded_data = base64.urlsafe_b64decode(encrypted_data)
        decrypted_data = fernet.decrypt(decoded_data)
        return decrypted_data.decode()
    except Exception:
        # Log error in production
        return ""


def generate_key() -> str:
    """
    Generate a new random encryption key.
    
    Returns:
        Base64 encoded encryption key
    """
    return base64.urlsafe_b64encode(Fernet.generate_key()).decode()