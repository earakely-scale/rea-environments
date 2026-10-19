#!/usr/bin/env python3
"""Set the Airbyte instance-admin email and a generated password through `abctl local credentials`, and keep the
admin password plus the default application client id/secret only in ~/capture/airbyte/.admin (mode 600). Prints nothing
secret: abctl output goes to a private temp file that is parsed and removed."""
import os, re, secrets, subprocess, tempfile
DIR = os.path.expanduser("~/capture/airbyte"); ADMIN = os.path.join(DIR, ".admin"); EMAIL = "rea-admin@example.test"
pw = secrets.token_urlsafe(21)
fd, tmp = tempfile.mkstemp(dir=DIR, prefix=".creds-"); os.close(fd); os.chmod(tmp, 0o600)
env = dict(os.environ, DO_NOT_TRACK="1")
with open(tmp, "w") as out:
    rc = subprocess.run([os.path.expanduser("~/.local/bin/abctl"), "local", "credentials", "--email", EMAIL, "--password", pw], stdout=out, stderr=subprocess.STDOUT, env=env).returncode
text = re.sub(r"\x1b\[[0-9;]*m", "", open(tmp).read()); os.remove(tmp)
if rc != 0: raise SystemExit(f"abctl local credentials failed rc={rc}")
cid = re.search(r"Client-Id:\s*(\S+)", text); csec = re.search(r"Client-Secret:\s*(\S+)", text)
if not (cid and csec): raise SystemExit("could not parse client credentials from abctl output")
fd = os.open(ADMIN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write(f"AIRBYTE_ADMIN_EMAIL={EMAIL}\nAIRBYTE_ADMIN_PASSWORD={pw}\nAIRBYTE_CLIENT_ID={cid.group(1)}\nAIRBYTE_CLIENT_SECRET={csec.group(1)}\n")
print(f"wrote {ADMIN} (mode 600); keys: AIRBYTE_ADMIN_EMAIL AIRBYTE_ADMIN_PASSWORD AIRBYTE_CLIENT_ID AIRBYTE_CLIENT_SECRET")
