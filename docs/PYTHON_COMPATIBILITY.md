# Python Version Compatibility

## Supported Python Versions

- **Python 3.12.x** - ✅ Fully supported (recommended)
- **Python 3.13.x** - ⚠️ Not tested
- **Python 3.14.x** - ❌ **Not supported** - See issues below

## Python 3.14 Known Issues

### Issue: pip compatibility broken

**Problem:** Python 3.14 on macOS (installed via Homebrew) has a broken pip that fails to install packages.

**Error message:**
```
ImportError: dlopen(...pyexpat.cpython-314-darwin.so, 0x0002): Symbol not found: _XML_SetAllocTrackerActivationThreshold
Referenced from: ...pyexpat.cpython-314-darwin.so
Expected in: /usr/lib/libexpat.1.dylib
```

**Root cause:** Python 3.14 was compiled against a newer version of libexpat than what's available in macOS system libraries. The `pyexpat` module can't load because of missing symbols.

**Impact:**
- `pip install` fails for all packages
- Can't install Mimir dependencies
- Virtual environments created with Python 3.14 will have broken pip

**Workaround:**
1. **Use Python 3.12** (recommended):
   ```bash
   # Create venv with Python 3.12
   python3.12 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Fix pip in Python 3.14** (if you must use 3.14):
   ```bash
   # Bootstrap pip using get-pip.py
   curl https://bootstrap.pypa.io/get-pip.py | python3.14
   ```
   Note: This may still fail for packages that depend on `pyexpat` (like `lxml`, `xmlrpc`, etc.)

**Mimir's approach:**
- The `.venv` directory in Mimir uses Python 3.12.12 (via uv's python distribution)
- `pyproject.toml` specifies `requires-python = ">=3.12,<3.14"` to exclude 3.14
- CI/CD should use Python 3.12 for building and testing

## Checking Your Python Version

```bash
python --version
# If output contains "3.14", consider downgrading to 3.12
```

## Virtual Environment Setup

Mimir includes a `.venv` directory with Python 3.12.12. To use it:

```bash
# Activate the venv
source .venv/bin/activate

# Verify Python version
python --version  # Should show 3.12.x

# Install dependencies (if not already installed)
pip install -r requirements.txt
```

## Adding Python 3.14 Support (Future)

To support Python 3.14 in the future:
1. Wait for Homebrew/Python to fix the libexpat issue
2. Test that all dependencies (llama-index, langchain, etc.) work on 3.14
3. Update `pyproject.toml` to allow 3.14: `requires-python = ">=3.12"`
4. Update this documentation
