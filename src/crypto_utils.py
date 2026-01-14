import logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# Keys extracted from original TypeScript source
KEY = b"VQZBJ6TD8M9WBUWT"
IV  = b"joiwef08u23j341a"

def encrypt_password(password: str) -> str:
    """
    Encrypts the password using AES-128-CBC with fixed key and IV.
    Matches the TypeScript implementation:
    const key = Buffer.from("VQZBJ6TD8M9WBUWT", 'utf8');
    const iv = Buffer.from("joiwef08u23j341a", 'utf8');
    """
    try:
        cipher = AES.new(KEY, AES.MODE_CBC, IV)
        # TS uses: cipher.update(password, 'utf8', 'hex') + cipher.final('hex')
        # This implies standard PKCS7 padding (default for Node crypto usually, 
        # but let's check behavior. `createCipheriv` usually does padding automatically).
        # We need to pad in Python manually.
        padded_data = pad(password.encode('utf-8'), AES.block_size)
        encrypted_bytes = cipher.encrypt(padded_data)
        return encrypted_bytes.hex()
    except Exception as e:
        logging.error(f"❌ Error encrypting password: {e}")
        raise
