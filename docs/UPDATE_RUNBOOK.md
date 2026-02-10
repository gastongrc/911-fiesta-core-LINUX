# 911 Fiesta V7 - Update & Rollback Runbook

## Overview

This runbook covers updating 911 Fiesta on Ubuntu 22.04.5 Desktop, including
routine updates, tagged releases, and rollback procedures.

---

## Routine Update

Pull the latest code from the current branch, re-sync dependencies, restart,
and verify:

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh
```

This single command:
1. Saves the current commit as a rollback point
2. Pulls latest code from the tracked branch
3. Re-installs Python dependencies from the lock file
4. Updates the systemd unit if changed
5. Restarts the service
6. Runs the healthcheck
7. On success, marks the new commit as last-known-good

---

## Update a Specific Branch

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --branch release/v7.1
```

---

## Deploy a Tagged Release

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --tag v7.1.0
```

---

## Update with SHOW Profile

If running the full SHOW profile (GUI + vision + audio):

```bash
# CPU PyTorch
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show

# GPU PyTorch (NVIDIA CUDA 12.1)
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --profile show --torch-gpu
```

---

## Rollback

### Automatic Rollback

If a healthcheck fails after update, the script exits with code 1.
The service may be running on the new code. To rollback:

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --rollback
```

This checks out the commit stored in `/etc/911fiesta/last-known-good-commit`,
re-syncs dependencies, restarts the service, and runs the healthcheck.

### Manual Rollback to a Specific Commit

```bash
cd /opt/911fiesta
sudo -u fiesta911 git log --oneline -20          # Find the target commit
sudo -u fiesta911 git checkout <commit-hash>     # Checkout
sudo bash scripts/update_911fiesta.sh --skip-healthcheck  # Re-sync and restart
bash scripts/healthcheck_911fiesta.sh         # Verify
```

### Manual Rollback to a Tag

```bash
sudo bash /opt/911fiesta/scripts/update_911fiesta.sh --tag v7.0.5
```

---

## Pre-Update Checklist

Before updating a production system:

1. **Check current state:**
   ```bash
   systemctl status 911fiesta
   bash /opt/911fiesta/scripts/healthcheck_911fiesta.sh
   ```

2. **Note the current commit** (for manual rollback):
   ```bash
   git -C /opt/911fiesta log --oneline -1
   ```

3. **Review what will change:**
   ```bash
   cd /opt/911fiesta
   sudo -u fiesta911 git fetch origin
   sudo -u fiesta911 git log --oneline HEAD..origin/baseline/linux-foja-cero
   ```

4. **Schedule downtime if needed** - the service restarts during update,
   causing a brief interruption to the API and vision pipeline.

---

## Post-Update Verification

After any update:

```bash
# 1. Service is running
systemctl status 911fiesta

# 2. Healthcheck passes
bash /opt/911fiesta/scripts/healthcheck_911fiesta.sh

# 3. API responds
curl -s http://127.0.0.1:8000/docs | head -5

# 4. Check logs for errors
journalctl -u 911fiesta -n 30 --no-pager

# 5. Verify commit
git -C /opt/911fiesta log --oneline -1
```

---

## Dependency Updates

When `requirements/server.lock.txt` or `requirements/show.lock.txt` changes
in the repo, the update script automatically re-syncs via pip.

To manually regenerate lock files (development workflow):

```bash
cd /opt/911fiesta
source .venv/bin/activate
pip-compile requirements/server.in -o requirements/server.lock.txt --resolver=backtracking
pip-compile requirements/show.in   -o requirements/show.lock.txt   --resolver=backtracking
```

---

## Systemd Service Management

```bash
# Status
systemctl status 911fiesta

# Start / Stop / Restart
sudo systemctl start 911fiesta
sudo systemctl stop 911fiesta
sudo systemctl restart 911fiesta

# View logs (live)
journalctl -u 911fiesta -f

# View logs (last 100 lines)
journalctl -u 911fiesta -n 100 --no-pager

# Reload unit file after manual edit
sudo systemctl daemon-reload
sudo systemctl restart 911fiesta

# Disable auto-start
sudo systemctl disable 911fiesta
```

---

## Troubleshooting Updates

### Update script fails on git pull

```bash
# Check for local modifications
cd /opt/911fiesta
sudo -u fiesta911 git status

# If there are local changes, stash them
sudo -u fiesta911 git stash
sudo bash scripts/update_911fiesta.sh
sudo -u fiesta911 git stash pop  # Re-apply if needed
```

### Pip install fails

```bash
# Check disk space
df -h /opt

# Try with verbose output
/opt/911fiesta/.venv/bin/pip install -r requirements/server.lock.txt -v

# Rebuild venv from scratch
rm -rf /opt/911fiesta/.venv
sudo bash scripts/install_911fiesta.sh --skip-healthcheck
```

### Service crashes after update

```bash
# Check the error
journalctl -u 911fiesta -n 50 --no-pager

# Rollback immediately
sudo bash scripts/update_911fiesta.sh --rollback

# Or rollback manually
cat /etc/911fiesta/last-known-good-commit
cd /opt/911fiesta
sudo -u fiesta911 git checkout <commit-from-above>
sudo systemctl restart 911fiesta
```

### Healthcheck fails but service is running

The healthcheck tests more than just the service (cameras, imports, API).
Read the healthcheck output to identify specific failures:

```bash
bash /opt/911fiesta/scripts/healthcheck_911fiesta.sh 2>&1 | grep FAIL
```

Common post-update failures:
- **Import error**: New dependency not in lock file. Regenerate locks.
- **Camera unreachable**: Network issue, not a code problem.
- **API not responding**: Service still starting. Wait 10 seconds and retry.

---

## Emergency Recovery

If the system is completely broken:

```bash
# 1. Stop the service
sudo systemctl stop 911fiesta

# 2. Rebuild from scratch
sudo rm -rf /opt/911fiesta/.venv
sudo bash scripts/bootstrap_linux.sh
sudo bash scripts/install_911fiesta.sh --branch baseline/linux-foja-cero

# 3. Restore configs (if they were overwritten)
# Configs in /etc/911fiesta/ are NOT overwritten by install if they exist.
```

---

## Version History Tracking

Each successful install/update writes the commit hash to
`/etc/911fiesta/last-known-good-commit`. To maintain a history:

```bash
# View update history via git reflog
cd /opt/911fiesta
git reflog --date=short | head -20
```

For production environments, consider tagging releases:

```bash
git tag -a v7.1.0 -m "Production release 7.1.0"
git push origin v7.1.0
```

Then deploy by tag:

```bash
sudo bash scripts/update_911fiesta.sh --tag v7.1.0
```
