---
name: system-health-check
description: Execute a comprehensive system health check that tests OS info, disk space, memory, CPU, network connectivity, installed utilities, and directory permissions, producing a formatted diagnostic report.
---

# System Health Check

This skill provides a reusable pattern for executing comprehensive system health checks that validate multiple system components and produce a clear diagnostic report identifying any failures.

## When to Use

- Validating a new environment before starting work
- Troubleshooting system issues or debugging deployment problems
- Performing routine system diagnostics
- Verifying prerequisites for a project or application
- Generating a system status report for documentation

## Key Components to Check

A comprehensive health check should validate:

1. **OS Information**: OS type, version, architecture
2. **Disk Space**: Available storage on critical mount points
3. **Memory**: Total, available, and used memory
4. **CPU**: Count and current load
5. **Network Connectivity**: Ping test to verify internet/network access
6. **System Utilities**: Presence and versions of key tools (git, python, pip, etc.)
7. **Directory Permissions**: Read/write access to working directories
8. **System Uptime**: How long the system has been running

## Implementation Pattern

### Step 1: Structure the Health Check Script

Use Python with the `platform`, `psutil`, and `subprocess` modules for cross-platform compatibility:

```python
#!/usr/bin/env python3
import platform
import psutil
import subprocess
import os
import sys
from pathlib import Path

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def check_status(name, status, details=""):
    """Print a status line with pass/fail indicator"""
    symbol = "✓" if status else "✗"
    status_text = "PASS" if status else "FAIL"
    print(f"[{symbol}] {name}: {status_text}")
    if details:
        print(f"    {details}")
    return status
```

### Step 2: Implement Individual Health Checks

Create modular check functions that return boolean status and details:

```python
def check_os_info():
    """Check operating system information"""
    print_section("Operating System")
    try:
        info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        return check_status("OS Info", True, info)
    except Exception as e:
        return check_status("OS Info", False, str(e))

def check_disk_space(min_gb=1):
    """Check disk space availability"""
    print_section("Disk Space")
    try:
        usage = psutil.disk_usage('/')
        free_gb = usage.free / (1024**3)
        status = free_gb >= min_gb
        details = f"{free_gb:.2f} GB free (min: {min_gb} GB)"
        return check_status("Disk Space", status, details)
    except Exception as e:
        return check_status("Disk Space", False, str(e))

def check_memory():
    """Check memory availability"""
    print_section("Memory")
    try:
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024**3)
        avail_gb = mem.available / (1024**3)
        details = f"{avail_gb:.2f} GB available / {total_gb:.2f} GB total"
        return check_status("Memory", True, details)
    except Exception as e:
        return check_status("Memory", False, str(e))

def check_cpu():
    """Check CPU information"""
    print_section("CPU")
    try:
        count = psutil.cpu_count()
        load = psutil.cpu_percent(interval=1)
        details = f"{count} cores, {load}% load"
        return check_status("CPU", True, details)
    except Exception as e:
        return check_status("CPU", False, str(e))
```

### Step 3: Check Network Connectivity

```python
def check_network(host="8.8.8.8", timeout=5):
    """Check network connectivity via ping"""
    print_section("Network Connectivity")
    try:
        # Use appropriate ping command based on OS
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", "-W" if platform.system().lower() != "windows" else "-w", str(timeout), host]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        status = result.returncode == 0
        details = f"Ping to {host}: {'Success' if status else 'Failed'}"
        return check_status("Network", status, details)
    except Exception as e:
        return check_status("Network", False, str(e))
```

### Step 4: Check Required Utilities

```python
def check_utility(name, version_flag="--version"):
    """Check if a utility is installed and get its version"""
    try:
        result = subprocess.run([name, version_flag], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              timeout=5,
                              text=True)
        version = result.stdout.split('\n')[0] if result.returncode == 0 else result.stderr.split('\n')[0]
        return check_status(name, result.returncode == 0, version[:100])
    except FileNotFoundError:
        return check_status(name, False, "Not installed")
    except Exception as e:
        return check_status(name, False, str(e))

def check_utilities():
    """Check for required system utilities"""
    print_section("System Utilities")
    results = []
    utilities = [
        ("git", "--version"),
        ("python3", "--version"),
        ("pip3", "--version"),
    ]
    for util, flag in utilities:
        results.append(check_utility(util, flag))
    return all(results)
```

### Step 5: Check Directory Permissions

```python
def check_directory_permissions(path="."):
    """Check read/write permissions for a directory"""
    print_section("Directory Permissions")
    try:
        test_path = Path(path)
        can_read = os.access(test_path, os.R_OK)
        can_write = os.access(test_path, os.W_OK)
        status = can_read and can_write
        details = f"Read: {can_read}, Write: {can_write} ({test_path.absolute()})"
        return check_status("Permissions", status, details)
    except Exception as e:
        return check_status("Permissions", False, str(e))
```

### Step 6: Aggregate Results and Report

```python
def main():
    """Run all health checks and report overall status"""
    print("\n" + "="*60)
    print("  SYSTEM HEALTH CHECK")
    print("="*60)
    
    checks = []
    
    # Run all checks
    checks.append(check_os_info())
    checks.append(check_disk_space(min_gb=1))
    checks.append(check_memory())
    checks.append(check_cpu())
    checks.append(check_network(host="8.8.8.8"))
    checks.append(check_utilities())
    checks.append(check_directory_permissions())
    
    # Summary
    print_section("SUMMARY")
    passed = sum(checks)
    total = len(checks)
    print(f"Checks Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All system checks PASSED")
        sys.exit(0)
    else:
        print(f"\n✗ {total - passed} check(s) FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## Usage Pattern

### Direct Execution

Use `shell_agent` to execute the health check:

```python
shell_agent("Create and run a comprehensive system health check that validates: OS info, disk space (min 1GB), memory, CPU, network connectivity (ping 8.8.8.8), installed utilities (git, python3, pip3), and directory permissions. Format the output clearly with pass/fail indicators.")
```

### Customization

Adapt the checks to your specific needs:

- **Add utility checks**: Include project-specific tools (docker, node, java, etc.)
- **Adjust thresholds**: Modify minimum disk space, memory requirements
- **Custom network checks**: Test specific hosts or ports relevant to your environment
- **Additional checks**: Database connectivity, API endpoints, file existence, etc.

## Best Practices

1. **Use `psutil` for cross-platform compatibility** instead of parsing shell commands
2. **Handle exceptions gracefully** to ensure all checks run even if some fail
3. **Provide clear, actionable error messages** with specific failure details
4. **Return appropriate exit codes** (0 for success, non-zero for failures)
5. **Make thresholds configurable** via command-line arguments or environment variables
6. **Log results** to a file for historical tracking if needed
7. **Group related checks** logically for better report organization

## Output Example

```
============================================================
  SYSTEM HEALTH CHECK
============================================================

============================================================
  Operating System
============================================================
[✓] OS Info: PASS
    Linux 5.15.0 (x86_64)

============================================================
  Disk Space
============================================================
[✓] Disk Space: PASS
    47.32 GB free (min: 1 GB)

============================================================
  Memory
============================================================
[✓] Memory: PASS
    5.23 GB available / 7.68 GB total

============================================================
  SUMMARY
============================================================
Checks Passed: 7/7

✓ All system checks PASSED
```

## Troubleshooting

- **Import errors**: Install `psutil` with `pip install psutil`
- **Permission errors**: Run with appropriate privileges or adjust check paths
- **Network timeout**: Increase timeout value or check firewall rules
- **Cross-platform issues**: Use `platform.system()` to conditionally adjust commands