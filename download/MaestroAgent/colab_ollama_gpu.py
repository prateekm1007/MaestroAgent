"""
Google Colab Notebook — GPU-Powered Ollama for Maestro

INSTRUCTIONS:
1. Open https://colab.research.google.com
2. Create a new notebook
3. Set Runtime → Change runtime type → T4 GPU
4. Paste this entire script into a cell
5. Run the cell
6. Copy the PUBLIC URL it prints
7. On your Maestro server, run:
   export OLLAMA_HOST=https://your-ngrok-url.io
   python -m maestro_personal_shell.api

This gives you a FREE T4 GPU running llama3:8b (or gemma2:9b) —
40x faster than CPU inference on a 4GB RAM server.
"""

# ═══════════════════════════════════════════════════════════════
# CELL 1: Install Ollama + ngrok, pull model, expose
# ═══════════════════════════════════════════════════════════════

import subprocess
import os
import time
import json

# Step 1: Install Ollama
print("Installing Ollama...")
subprocess.run(["curl", "-fsSL", "https://ollama.com/install.sh", "-o", "/tmp/install.sh"])
subprocess.run(["bash", "/tmp/install.sh"], check=True)
print("✅ Ollama installed")

# Step 2: Start Ollama server
print("Starting Ollama server...")
os.environ["OLLAMA_HOST"] = "0.0.0.0:11434"
proc = subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)

# Step 3: Pull a GPU-optimized model
# Choose one — llama3:8b is the best balance of quality and speed
MODEL = "llama3:8b"  # 4.7GB, ~1s inference on T4 GPU
# MODEL = "gemma2:9b"  # 5.4GB, slightly better quality
# MODEL = "qwen2.5:7b"  # 4.7GB, excellent for reasoning
# MODEL = "phi3:14b"    # 7.9GB, best reasoning (might be tight on T4)

print(f"Pulling {MODEL} (this takes ~2 minutes)...")
subprocess.run(["ollama", "pull", MODEL], check=True)
print(f"✅ {MODEL} pulled")

# Step 4: Test the model
print("Testing model...")
import urllib.request
data = json.dumps({
    "model": MODEL,
    "messages": [{"role": "user", "content": "What is 2+2? Just the number."}],
    "stream": False,
}).encode()
req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=data, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=30)
result = json.loads(resp.read())
print(f"✅ Model responds: {result['message']['content'][:50]}")
print(f"   Eval time: {result.get('eval_duration', 0)/1e9:.1f}s")

# Step 5: Install ngrok and expose
print("\nInstalling ngrok...")
subprocess.run(["pip", "install", "-q", "pyngrok"], check=True)

from pyngrok import ngrok

# Kill any existing tunnels
ngrok.kill()

# Set your ngrok authtoken (get one free at https://ngrok.com)
# Uncomment and replace with your token:
# ngrok.set_auth_token("YOUR_NGROK_TOKEN_HERE")

# Create tunnel
print("Creating ngrok tunnel...")
try:
    tunnel = ngrok.connect(11434, "http")
    public_url = tunnel.public_url
    print(f"\n{'='*60}")
    print(f"🚀 OLLAMA IS LIVE ON GPU!")
    print(f"{'='*60}")
    print(f"Public URL: {public_url}")
    print(f"Model: {MODEL}")
    print(f"\nOn your Maestro server, run:")
    print(f"  export OLLAMA_HOST={public_url}")
    print(f"  export OLLAMA_MODEL={MODEL}")
    print(f"{'='*60}")
    print(f"\nThe tunnel stays active as long as this notebook runs.")
    print(f"Colab free tier: ~12 hours of GPU time.")
except Exception as e:
    print(f"ngrok failed: {e}")
    print("\nAlternative: use Cloudflare tunnel")
    print("Run: !wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /tmp/cloudflared")
    print("Then: !chmod +x /tmp/cloudflared && /tmp/cloudflared tunnel --url http://127.0.0.1:11434 &")
    print("\nOr try localtunnel: !npx localtunnel --port 11434")

# ═══════════════════════════════════════════════════════════════
# The notebook will print a URL like:
#   https://abc123.ngrok.io
#
# On the Maestro server:
#   export OLLAMA_HOST=https://abc123.ngrok.io
#   export OLLAMA_MODEL=llama3:8b
#
# Maestro's _OllamaDirectRouter will automatically use this URL.
# ═══════════════════════════════════════════════════════════════
