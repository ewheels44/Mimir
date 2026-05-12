#!/usr/bin/env python3
"""
End-to-end test for Mimir MCP server + Jcode bridge.
Tests: server startup, tool listing, knowledge search, and query.
"""
import json
import os
import subprocess
import sys
import time
import select

MIMIR_ROOT = "/Users/ethanwheeler/Documents/Mimir"
PYTHON = sys.executable

def read_line(proc, timeout=5):
    """Read a line from proc.stdout with timeout."""
    if select.select([proc.stdout], [], [], timeout)[0]:
        return proc.stdout.readline().decode("utf-8", errors="replace")
    return None

def send(proc, msg):
    """Send a JSON-RPC message to the MCP server."""
    data = json.dumps(msg).encode()
    proc.stdin.write(data + b"\n")
    proc.stdin.flush()

def main():
    env = {**os.environ, "PROJECT_ROOT": MIMIR_ROOT, "PYTHONPATH": MIMIR_ROOT + "/src"}

    print("=" * 60)
    print("Mimir MCP Server — End-to-End Test")
    print("=" * 60)

    # Start server
    print("\n[1] Starting MCP server...")
    proc = subprocess.Popen(
        [PYTHON, MIMIR_ROOT + "/mcp_server_llamaindex.py"],
        cwd=MIMIR_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
    )
    time.sleep(4)

    if proc.poll() is not None:
        print("❌ Server crashed on startup")
        stderr = proc.stderr.read().decode()
        print(f"   stderr: {stderr[:500]}")
        return 1

    print("   ✅ Server process started (PID {})".format(proc.pid))

    # Initialize
    print("\n[2] Sending initialize request...")
    send(proc, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"processId": None, "rootPath": MIMIR_ROOT, "capabilities": {}},
    })
    resp = read_line(proc, 5)
    if not resp:
        print("❌ No response to initialize")
        proc.terminate()
        return 1
    print("   ✅ Response received")

    # List tools
    print("\n[3] Listing available tools...")
    send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    resp = read_line(proc, 5)
    if resp:
        data = json.loads(resp)
        tools = data.get("result", {}).get("tools", [])
        print("   Found {} tools:".format(len(tools)))
        for t in tools[:10]:
            print(f"   - {t['name']}: {t.get('description', '')[:60]}")
        if len(tools) > 10:
            print(f"   ... and {len(tools) - 10} more")
    else:
        print("❌ No tools listed")

    # Test search tool
    print("\n[4] Testing mimir-knowledge_search...")
    send(proc, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "mimir-knowledge_search",
            "arguments": {"query": "How does the indexing pipeline work?", "top_k": 3},
        },
    })

    # Collect results (may be multiple lines for streaming)
    results = []
    deadline = time.time() + 10
    while time.time() < deadline:
        line = read_line(proc, 2)
        if line:
            results.append(line)
            if '"content"' in line:
                break
        elif proc.poll() is not None:
            break

    if results:
        # Find the last complete response with "result"
        for r in reversed(results):
            try:
                data = json.loads(r)
                if "result" in data:
                    content = data["result"].get("content", "")
                    print("   ✅ Result (first 300 chars):")
                    print("   " + content[:300].replace("\n", "\n   "))
                    break
            except json.JSONDecodeError:
                continue
    else:
        print("❌ No results from search")

    # Test query tool
    print("\n[5] Testing mimir-knowledge_query...")
    send(proc, {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "mimir-knowledge_query",
            "arguments": {"question": "What is the architecture of the Mimir knowledge system?"},
        },
    })

    results = []
    deadline = time.time() + 15
    while time.time() < deadline:
        line = read_line(proc, 2)
        if line:
            results.append(line)
            try:
                data = json.loads(line)
                if "result" in data and "content" in data.get("result", {}):
                    content = data["result"]["content"]
                    if len(content) > 50:
                        break
            except:
                pass
        elif proc.poll() is not None:
            break

    if results:
        for r in reversed(results):
            try:
                data = json.loads(r)
                if "result" in data and len(data["result"].get("content", "")) > 50:
                    content = data["result"]["content"]
                    print("   ✅ Result (first 300 chars):")
                    print("   " + content[:300].replace("\n", "\n   "))
                    break
            except json.JSONDecodeError:
                continue
    else:
        print("❌ No results from query")

    # Test stats tool
    print("\n[6] Testing health_check tool...")
    send(proc, {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "mimir-health_check",
            "arguments": {},
        },
    })

    results = []
    deadline = time.time() + 5
    while time.time() < deadline:
        line = read_line(proc, 2)
        if line:
            results.append(line)
        elif proc.poll() is not None:
            break

    for r in reversed(results):
        try:
            data = json.loads(r)
            if "result" in data and "content" in data["result"]:
                content = data["result"]["content"]
                parsed = json.loads(content)
                print(f"   ✅ Status: {parsed.get('status')}")
                print(f"   ✅ Has index: {parsed.get('has_index')}")
                print(f"   ✅ Document count: {parsed.get('document_count')}")
                break
        except:
            continue

    # Cleanup
    print("\n[7] Shutting down...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())