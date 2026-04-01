"""
Quick diagnostic: test ACRCloud with both data_type='audio' and data_type='humming'
to see what the server actually responds for each.
"""
import os
import hmac
import hashlib
import base64
import time
import json
import requests
import wave
import struct
import math
from dotenv import load_dotenv

load_dotenv()

HOST          = os.getenv("ACRCLOUD_HOST")
ACCESS_KEY    = os.getenv("ACRCLOUD_ACCESS_KEY")
ACCESS_SECRET = os.getenv("ACRCLOUD_ACCESS_SECRET")

def generate_test_tone(filename="test_tone.wav", duration=5, freq=440):
    """Generate a simple sine wave tone for testing."""
    sample_rate = 16000
    n_samples = sample_rate * duration
    with wave.open(filename, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(n_samples):
            value = int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / sample_rate))
            wf.writeframes(struct.pack("<h", value))
    return filename

def test_acrcloud(file_path, data_type):
    """Send request to ACRCloud and return full response."""
    http_method       = "POST"
    http_uri          = "/v1/identify"
    signature_version = "1"
    timestamp         = str(time.time())

    string_to_sign = "\n".join([
        http_method, http_uri, ACCESS_KEY,
        data_type, signature_version, timestamp,
    ])

    signature = base64.b64encode(
        hmac.new(
            ACCESS_SECRET.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    file_size = os.path.getsize(file_path)

    with open(file_path, "rb") as f:
        resp = requests.post(
            f"https://{HOST}/v1/identify",
            files={"sample": f},
            data={
                "access_key":        ACCESS_KEY,
                "sample_bytes":      str(file_size),
                "timestamp":         timestamp,
                "signature":         signature,
                "data_type":         data_type,
                "signature_version": signature_version,
            },
            timeout=30,
        )

    return resp.json()


if __name__ == "__main__":
    print(f"Host: {HOST}")
    print(f"Access Key: {ACCESS_KEY[:8]}...")
    print()

    # Generate a test tone
    test_file = generate_test_tone()
    print(f"Generated test file: {test_file}\n")

    # Test with data_type = "audio"
    print("=" * 60)
    print("TEST 1: data_type = 'audio' (ambient)")
    print("=" * 60)
    r1 = test_acrcloud(test_file, "audio")
    print(json.dumps(r1, indent=2))

    print()

    # Test with data_type = "humming"
    print("=" * 60)
    print("TEST 2: data_type = 'humming'")
    print("=" * 60)
    r2 = test_acrcloud(test_file, "humming")
    print(json.dumps(r2, indent=2))

    # Cleanup
    os.remove(test_file)

    print("\n" + "=" * 60)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 60)
    s1 = r1.get("status", {})
    s2 = r2.get("status", {})
    print(f"  audio   → code={s1.get('code')}, msg='{s1.get('msg')}'")
    print(f"  humming → code={s2.get('code')}, msg='{s2.get('msg')}'")

    if s2.get("code") == 2004:
        print("\n[WARN] Code 2004 = 'Can not generate fingerprint'. Proiectul ACRCloud")
        print("   NU are Humming Recognition activat, sau bucket-ul nu e de tip humming.")
    elif s2.get("code") == 1001:
        print("\n[OK] Humming functioneaza (code 1001 = No result, normal pt un ton simplu).")
        print("   Testeaza cu o fredonare reala a unei melodii populare.")
    elif s2.get("code") == 0:
        print("\n[OK] Humming functioneaza perfect! A recunoscut ceva.")
    elif s2.get("code") == 3003:
        print("\n[ERR] Code 3003 = Limit exceeded. Ai depasit limita de request-uri.")
    elif s2.get("code") == 3015:
        print("\n[ERR] Code 3015 = 'QpS limit' sau 'data_type invalid for this project'.")
        print("   Proiectul NU suporta humming. Trebuie un proiect separat cu Humming Recognition.")
