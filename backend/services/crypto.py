import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# Ensure we have a key (32 bytes for AES-256)
ENV_KEY = os.getenv('ENCRYPTION_KEY', 'default_insecure_key_please_change_me_to_32_chars!!')

def get_key():
    # Pad or truncate to 32 bytes
    if isinstance(ENV_KEY, str):
        k = ENV_KEY.encode()
    else:
        k = ENV_KEY
    return k[:32].ljust(32, b'0')

def encrypt_stream_to_file(input_stream, output_path, key=None):
    """
    Read from input_stream (file-like) and write encrypted data to output_path.
    Uses AES-CTR mode.
    Prepends 16-byte IV to the file.
    """
    key = key or get_key()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    
    with open(output_path, 'wb') as f_out:
        f_out.write(iv)
        while True:
            chunk = input_stream.read(64*1024)
            if not chunk:
                break
            f_out.write(encryptor.update(chunk))
        f_out.write(encryptor.finalize())

def decrypt_file_generator(input_path, key=None, chunk_size=64*1024):
    """
    Generator that yields decrypted chunks from an encrypted file.
    Useful for streaming to other services (FFmpeg, Telegram).
    """
    key = key or get_key()
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Encrypted file not found: {input_path}")
        
    with open(input_path, 'rb') as f_in:
        # Read IV
        iv = f_in.read(16)
        if len(iv) < 16:
            return # Empty or corrupt
            
        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        
        while True:
            chunk = f_in.read(chunk_size)
            if not chunk:
                break
            yield decryptor.update(chunk)
        yield decryptor.finalize()

class DecryptedReader:
    """
    File-like object that decrypts on-the-fly.
    """
    def __init__(self, path, key=None):
        self.path = path
        self.f = open(path, 'rb')
        self.key = key or get_key()
        
        # Read IV
        self.iv = self.f.read(16)
        if len(self.iv) < 16:
            raise ValueError("File too short or corrupt")
            
        self.cipher = Cipher(algorithms.AES(self.key), modes.CTR(self.iv), backend=default_backend())
        self.decryptor = self.cipher.decryptor()
        self.buffer = b''

    def read(self, size=-1):
        # We need to read from file and decrypt
        if size == -1:
            # Read all remaining
            raw = self.f.read()
            return self.decryptor.update(raw) + self.decryptor.finalize()
        
        raw = self.f.read(size)
        if not raw:
            return b''
            
        return self.decryptor.update(raw)
    
    def close(self):
        self.f.close()
        
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
