"""
Security module for authentication, authorization, and encryption.
"""
from .crypto import encrypt_data, decrypt_data, generate_key

__all__ = ["encrypt_data", "decrypt_data", "generate_key"]