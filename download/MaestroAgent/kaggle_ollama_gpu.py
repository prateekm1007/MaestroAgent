"""
Kaggle Notebook — P100 GPU-Powered Ollama for Maestro
STRONGER than Colab T4. 30h/week free, 16GB VRAM.

INSTRUCTIONS:
1. Go to https://www.kaggle.com/code
2. Create a new notebook
3. Settings → Accelerator → GPU P100
4. Settings → Internet → ON
5. Paste this into a cell and RUN
6. Copy the PUBLIC URL it prints
7. On Maestro server: export OLLAMA_HOST=<url> OLLAMA_MODEL=<model>
"""

import subprocess, os, time, json, urllib.request, sys

def safe_json_parse(resp):
    """Safely parse JSON from urllib response."""
    raw = resp.read()
    if not raw:
        raise ValueError("Empty response from server")
    text = raw.decode('utf-8', errors='replace')
    if text.startswith('<!') or text.startswith('<html'):
        raise ValueError(f"Got HTML instead of JSON (first 100 chars): {text[:100]}")
    return json.loads(text)

def wait_for_ollama(max_wait=60):
    """Wait for Ollama to be ready."""
    for i in range(max_wait):
        try:
            resp = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3)
            data = safe_json_parse(resp)
            if data:
                return True
        except Exception as e:
            if i % 5 == 0:
                print(f"  Waiting for Ollama... ({i}s) — {str(e)[:60]}")
        time.sleep(1)
    return False

print("=" * 60)
print("KAGGLE P100 GPU — OLLAMA FOR MAESTRO")
print("=" * 60)

# Step 1: Install Ollama
print("\n1. Installing Ollama...")
# Try the official install script first
install_ok = False
try:
    subprocess.run(["curl", "-fsSL", "https://ollama.com/install.sh", "-o", "/tmp/install.sh"], timeout=30)
    result = subprocess.run(["bash", "/tmp/install.sh"], capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        install_ok = True
        print("  ✅ Installed via official script")
except Exception as e:
    print(f"  Official script failed: {e}")

# Fallback: download binary directly
if not install_ok:
    print("  Trying direct binary download...")
    try:
        subprocess.run(["wget", "-q", 
            "https://github.com/ollama/ollama/releases/download/v0.1.48/ollama-linux-amd64",
            "-O", "/usr/local/bin/ollama"], timeout=60, check=True)
        subprocess.run(["chmod", "+x", "/usr/local/bin/ollama"], check=True)
        install_ok = True
        print("  ✅ Installed via direct binary (v0.1.48)")
    except Exception as e:
        print(f"  Binary download failed: {e}")
        # Try latest release
        try:
            subprocess.run(["wget", "-q",
                "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64",
                "-O", "/usr/local/bin/ollama"], timeout=60, check=True)
            subprocess.run(["chmod", "+x", "/usr/local/bin/ollama"], check=True)
            install_ok = True
            print("  ✅ Installed via latest binary")
        except Exception as e2:
            print(f"  All install methods failed: {e2}")
            sys.exit(1)

# Step 2: Find the ollama binary
ollama_bin = "ollama"
if not os.path.exists("/usr/local/bin/ollama") and not subprocess.run(["which", "ollama"], capture_output=True).stdout:
    ollama_bin = "/usr/local/bin/ollama"
print(f"  Ollama binary: {ollama_bin}")

# Step 3: Start Ollama server
print("\n2. Starting Ollama server on 0.0.0.0:11434...")
os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
proc = subprocess.Popen(
    [ollama_bin, "serve"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    start_new_session=True,
)

# Step 4: Wait for Ollama to be ready
print("\n3. Waiting for Ollama to be ready...")
if not wait_for_ollama(60):
    print("  ❌ Ollama failed to start after 60s")
    # Print stderr for debugging
    proc.stderr.seek(0)
    stderr = proc.stderr.read(2000).decode()
    print(f"  stderr: {stderr[:500]}")
    sys.exit(1)
print("  ✅ Ollama server is running")

# Step 5: Choose model
MODEL = "llama3:8b"          # Best balance — 4.7GB, ~0.15s on P100
# MODEL = "qwen2.5:7b"       # Excellent reasoning
# MODEL = "gemma2:9b"        # Better quality
# MODEL = "phi3:14b"          # BEST reasoning (7.9GB — fits P100!)
# MODEL = "mistral:7b"        # Fast + good

print(f"\n4. Pulling {MODEL} (P100 GPU)...")
try:
    result = subprocess.run([ollama_bin, "pull", MODEL], capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  Pull stderr: {result.stderr[:200]}")
        # Try another model if this one fails
        print(f"  Trying fallback: qwen2.5:1.5b")
        MODEL = "qwen2.5:1.5b"
        subprocess.run([ollama_bin, "pull", MODEL], capture_output=True, text=True, timeout=120)
    print(f"  ✅ {MODEL} pulled")
except subprocess.TimeoutExpired:
    print(f"  Pull timed out, trying smaller model...")
    MODEL = "qwen2.5:0.5b"
    subprocess.run([ollama_bin, "pull", MODEL], capture_output=True, text=True, timeout=60)
    print(f"  ✅ {MODEL} pulled (fallback)")

# Step 6: Test the model
print(f"\n5. Testing {MODEL} on P100 GPU...")
data = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "What is 2+2? Just the number."}],
    "stream": False,
}).encode()

try:
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=data, headers={"Content-Type": "application/json"})
    start = time.time()
    resp = urllib.request.urlopen(req, timeout=60)
    result = safe_json_parse(resp)
    elapsed = time.time() - start
    eval_time = result.get("eval_duration", 0) / 1e9
    print(f"  ✅ Response: {result['message']['content'][:50]}")
    print(f"  Eval: {eval_time:.2f}s | Total: {elapsed:.2f}s")
except Exception as e:
    print(f"  ❌ Test failed: {e}")
    sys.exit(1)

# Step 7: Expose via ngrok or Cloudflare
print("\n6. Creating public tunnel...")

# Try ngrok first (requires token)
NGROK_TOKEN = ""  # Paste your token from https://dashboard.ngrok.com/get-started/your-authtoken
public_url = None

if NGROK_TOKEN:
    try:
        subprocess.run(["pip", "install", "-q", "pyngrok"], check=True)
        from pyngrok import ngrok
        ngrok.kill()
        ngrok.set_auth_token(NGROK_TOKEN)
        tunnel = ngrok.connect(11434, "http")
        public_url = tunnel.public_url
        print(f"  ✅ ngrok tunnel: {public_url}")
    except Exception as e:
        print(f"  ngrok failed: {e}")

# Fallback: Cloudflare tunnel (no token needed)
if not public_url:
    print("  Trying Cloudflare tunnel (no token needed)...")
    try:
        subprocess.run(["wget", "-q",
            "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64",
            "-O", "/tmp/cloudflared"], timeout=30, check=True)
        subprocess.run(["chmod", "+x", "/tmp/cloudflared"], check=True)
        
        cf_proc = subprocess.Popen(
            ["/tmp/cloudflared", "tunnel", "--url", "http://127.0.0.1:11434"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        
        # Wait for Cloudflare to print the URL
        import threading
        found_url = [None]
        
        def read_cf_output():
            for line in cf_proc.stdout:
                text = line.decode('utf-8', errors='replace')
                if "trycloudflare.com" in text:
                    # Extract URL
                    import re
                    urls = re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', text)
                    if urls:
                        found_url[0] = urls[0]
                        return
                # Also check for the tunnel URL in other formats
                if "https://" in text and ".cloudflare" in text:
                    urls = re.findall(r'https://[a-zA-Z0-9-]+\.[a-zA-Z]+\.com', text)
                    if urls:
                        found_url[0] = urls[0]
                        return
        
        t = threading.Thread(target=read_cf_output, daemon=True)
        t.start()
        t.join(timeout=20)
        
        if found_url[0]:
            public_url = found_url[0]
            print(f"  ✅ Cloudflare tunnel: {public_url}")
        else:
            # Read the full output to find the URL
            cf_proc.stdout.seek(0) if hasattr(cf_proc.stdout, 'seek') else None
            print("  Could not auto-detect Cloudflare URL.")
            print("  Check the cell output above for a trycloudflare.com URL.")
            print("  Or sign up for ngrok (free) and paste your token in NGROK_TOKEN.")
    except Exception as e:
        print(f"  Cloudflare failed: {e}")

# Step 8: Print final instructions
if public_url:
    print(f"\n{'='*60}")
    print(f"🚀 OLLAMA LIVE ON P100 GPU!")
    print(f"{'='*60}")
    print(f"Public URL: {public_url}")
    print(f"Model: {MODEL}")
    print(f"Speed: {eval_time:.2f}s per LLM call")
    print(f"{'='*60}")
    print(f"\nOn your Maestro server, run:")
    print(f"  export OLLAMA_HOST={public_url}")
    print(f"  export OLLAMA_MODEL={MODEL}")
    print(f"{'='*60}")
    print(f"\nTunnel stays active while this cell runs.")
    print(f"Kaggle: 30h/week free, ~12h sessions.")
else:
    print(f"\n⚠ No tunnel URL detected.")
    print(f"Options:")
    print(f"  1. Get a free ngrok token: https://dashboard.ngrok.com/get-started/your-authtoken")
    print(f"     Paste it in NGROK_TOKEN above and re-run")
    print(f"  2. Check cell output for Cloudflare URL")
    print(f"  3. Use localtunnel: !npx localtunnel --port 11434")

# Step 9: Keep alive
print(f"\n{'='*60}")
print(f"KEEP-ALIVE — DO NOT STOP THIS CELL")
print(f"{'='*60}")
print(f"Running {MODEL} on P100 GPU. Will test every 5 min.")

for i in range(144):  # 12 hours at 5min intervals
    time.sleep(300)
    try:
        data = json.dumps({
            "model": MODEL,
            "messages": [{"role": "user", "content": "Say OK"}],
            "stream": False,
        }).encode()
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        result = safe_json_parse(resp)
        print(f"  [{(i+1)*5}min] ✅ {result['message']['content'][:20]} | eval={result.get('eval_duration',0)/1e9:.2f}s")
    except Exception as e:
        print(f"  [{(i+1)*5}min] ❌ {str(e)[:60]}")
