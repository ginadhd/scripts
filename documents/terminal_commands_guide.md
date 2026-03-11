# Terminal Commands Reference Guide

## Table of Contents

- [Navigation & File Management](#navigation--file-management)
- [Git](#git)
- [Kubernetes (kubectl)](#kubernetes-kubectl)
- [Azure CLI (az)](#azure-cli-az)
- [Docker](#docker)
- [Package Managers](#package-managers)
- [PostgreSQL (psql)](#postgresql-psql)
- [Python & uv](#python--uv)
- [Text Search & Filtering](#text-search--filtering)
- [Shell Utilities](#shell-utilities)
- [File Editing with vim](#file-editing-with-vim)
- [Creating & Managing Files](#creating--managing-files)

---

## Navigation & File Management

### `cd` — Change Directory

```bash
cd documents/git/web         # Move into a directory (relative path)
cd /Users/georgi/Downloads   # Move into a directory (absolute path)
cd ..                        # Go up one directory
cd ~                         # Go to home directory
```

### `ls` — List Files

```bash
ls                   # List files in current directory
ls -la               # List all files (including hidden) with details
ls -lh               # List with human-readable file sizes
```

### `mv` — Move or Rename Files

```bash
# Move a file from Downloads to Documents/Git, renaming it
mv /Users/georgi/Downloads/referral_register\(Referral\ Register\).csv /Users/georgi/Documents/Git/referral_register.csv
```

- The `\(` and `\ ` escape special characters (parentheses and spaces) in filenames
- If the destination is a directory, the file is moved into it
- If the destination is a file path, the file is moved and renamed

### `rm` — Remove Files

```bash
rm file.txt           # Delete a file
rm -rf .next          # Delete a directory and everything inside it recursively
```

- `-r` = recursive (delete directories)
- `-f` = force (don't ask for confirmation)
- **Be very careful with `rm -rf`** — there is no undo

### `cat` — Display File Contents

```bash
cat .env              # Print the entire file to the terminal
```

### `head` — Show Start of File

```bash
head -c 80 .env       # Show first 80 bytes of a file
head -5 file.txt      # Show first 5 lines
```

### `tail` — Show End of File

```bash
tail -50 file.txt     # Show last 50 lines
history | tail -50     # Show last 50 lines of piped output
```

### `wc` — Word/Line/Byte Count

```bash
wc -c .env            # Count bytes in a file
wc -l file.txt        # Count lines in a file
```

### `tar` — Create/Extract Archives

```bash
# Create a compressed archive (tar.gz), excluding certain file types
tar czf /tmp/bundle.tar.gz --exclude='*.one' -C /path/to source_dir

# Extract an archive
tar xzf /tmp/bundle.tar.gz
```

- `c` = create, `x` = extract, `z` = gzip compression, `f` = filename
- `-C /path` = change to this directory before adding files
- `--exclude='*.one'` = skip files matching the pattern

### `echo` — Print Text

```bash
echo "hello"                        # Print text to terminal
echo 'KEY=value' > .env             # Write text to a file (overwrites)
echo 'MORE=stuff' >> .env           # Append text to a file
```

- `>` overwrites the file
- `>>` appends to the file

---

## Git

### Basic Workflow

```bash
git status            # Show which files are modified/staged/untracked
git pull              # Download and merge latest changes from remote
git pull --all        # Fetch all remote branches then merge current
git fetch origin      # Download remote changes without merging
```

### Branching

```bash
git checkout develop                                    # Switch to existing branch
git checkout feature/82-make-icb-editable-with-fuzzy    # Switch to a feature branch
git checkout -b new-branch                              # Create and switch to new branch
```

### Committing & Pushing

```bash
git add file.txt                    # Stage a specific file
git add .                           # Stage all changes
git commit -m "commit message"      # Commit staged changes with a message
git commit -m "$(pbpaste)"          # Commit with message from clipboard (macOS)
git push                            # Push commits to remote
git push -u origin branch-name      # Push and set upstream tracking
```

### Inspecting

```bash
git log --oneline -10       # Show last 10 commits (short format)
git diff                    # Show unstaged changes
git diff --staged           # Show staged changes
git rev-parse --short HEAD  # Get current short commit hash
```

---

## Kubernetes (kubectl)

### Context & Cluster

```bash
# All commands use --context to specify which cluster to talk to
# and -n to specify the namespace
kubectl --context aks-innovate-adhd-prod -n innovate-adhd-prod ...
```

### Viewing Resources

```bash
# List pods
kubectl get pods -o name

# List deployments
kubectl get deployment -o name

# Get pod details filtered by name
kubectl get pods -o name | grep api
```

### Copying Files To/From Pods

```bash
# Copy local file to pod
kubectl cp documents/seed_patients.sql clinical-system-dbshell-567dfbf89c-mq6sm:/tmp/seed.sql

# Copy file from pod to local
kubectl cp clinical-system-dbshell-567dfbf89c-mq6sm:/tmp/output.csv ./output.csv
```

### Executing Commands Inside Pods

```bash
# Run a single command
kubectl exec <pod-name> -- psql "$DATABASE_URL" -f /tmp/seed.sql

# Run a shell command (use sh -c for pipes/redirects)
kubectl exec <pod-name> -- sh -c 'echo hello > /tmp/test.txt'

# Interactive shell (for debugging)
kubectl exec -it <pod-name> -- sh
```

### Inspecting Deployments & Secrets

```bash
# View env vars injected from secrets/configmaps
kubectl get deployment clinical-system-api \
  -o jsonpath='{.spec.template.spec.containers[0].envFrom}'

# Read a secret (base64-encoded)
kubectl get secret storage-credentials \
  -o jsonpath='{.data.AZURE_STORAGE_CONNECTION_STRING}'

# Decode a base64 secret value
kubectl get secret storage-credentials \
  -o jsonpath='{.data.AZURE_STORAGE_ACCOUNT_NAME}' | base64 -d
```

### Port Forwarding

```bash
# Forward local port 8888 to port 8888 on the pod
kubectl port-forward <pod-name> 8888:8888
```

- Makes a pod's port accessible on your local machine
- Useful for accessing databases, proxies, or internal services
- Runs in the foreground — use `&` or another terminal tab

### Installing Packages on Alpine Pods

```bash
# Alpine Linux uses apk as its package manager
kubectl exec <pod-name> -- apk add --no-cache nodejs npm tinyproxy
```

---

## Azure CLI (az)

```bash
az login                                    # Login to Azure (opens browser)
az logout                                   # Logout

az acr login --name acrinnovateadhdprod     # Login to Azure Container Registry

# Get Kubernetes credentials for a cluster
az aks get-credentials \
  --resource-group rg-innovate-adhd-dev \
  --name aks-innovate-adhd-dev \
  --subscription f39265c0-...

# Delete an Azure AD app registration
az ad app delete --id "c5d1951a-..."

# Delete a specific credential from an app
az ad app credential delete --id "c5d1951a-..." --key-id "ca7bdf51-..."
```

---

## Docker

### Building Images

```bash
docker build -f docker/Dockerfile \
    --secret id=GITHUB_TOKEN,env=GITHUB_TOKEN \
    --build-arg NEXT_PUBLIC_WORKOS_REDIRECT_URI=https://app.innovateadhd.com/callback \
    --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --build-arg VCS_REF=$(git rev-parse --short HEAD) \
    --build-arg VERSION=$(git rev-parse --short HEAD) \
    -t acrinnovateadhdprod.azurecr.io/web:$(git rev-parse --short HEAD) .
```

- `-f` = path to Dockerfile
- `--secret` = pass a secret without baking it into the image
- `--build-arg` = set build-time variables
- `-t` = tag (name) the image
- `.` = build context (current directory)

### Pushing Images

```bash
docker push acrinnovateadhdprod.azurecr.io/web:$(git rev-parse --short HEAD)
```

- Pushes the tagged image to the Azure Container Registry
- Must run `az acr login` first to authenticate

---

## Package Managers

### npm / pnpm

```bash
pnpm install       # Install all dependencies from package.json
npm install        # Same but with npm
npm init -y        # Create a new package.json with defaults
```

### brew (Homebrew — macOS)

```bash
brew install uv    # Install a package
```

### apk (Alpine Linux)

```bash
apk add --no-cache nodejs npm    # Install packages without caching
```

---

## PostgreSQL (psql)

```bash
# Run a SQL file against the database
psql "$DATABASE_URL" -f /tmp/seed.sql

# Run a single SQL query
psql "$DATABASE_URL" -c "SELECT * FROM mhs001_mpi LIMIT 5;"
```

- `$DATABASE_URL` is a connection string like `postgresql://user:pass@host:5432/dbname`
- `-f` runs a SQL file
- `-c` runs an inline SQL command

---

## Python & uv

### uv — Fast Python Package Manager

```bash
uv --version                    # Check uv version
uv add azure-storage-blob       # Add a dependency to the project
uv run script.py                # Run a script with the project's venv
uv run python3 -c "print(1)"   # Run inline Python with project deps
```

- `uv run` automatically creates/uses a virtual environment
- Dependencies are defined in `pyproject.toml`

### Virtual Environments

```bash
source .venv/bin/activate    # Activate a virtual environment manually
```

- After activation, `python` and `pip` use the venv's versions
- The terminal prompt usually shows `(venv-name)` when active

---

## Text Search & Filtering

### `grep` — Search File Contents

```bash
grep AZURE_STORAGE .env                     # Find lines containing "AZURE_STORAGE"
grep -o 'AccountName=[^;]*' .env            # Print only the matching part
grep -i azure .env                          # Case-insensitive search
```

- `-o` = output only the matched text (not the full line)
- `-i` = ignore case
- `[^;]*` = regex: match any characters until a semicolon

### `tr` — Translate Characters

```bash
echo "a b c" | tr ' ' '\n'     # Replace spaces with newlines
```

### `cut` — Extract Parts of Lines

```bash
grep AZURE .env | cut -c1-60    # Show only first 60 characters
cut -d',' -f1,3 file.csv        # Extract columns 1 and 3 (comma-delimited)
```

### Piping (`|`)

```bash
# Chain commands: output of left becomes input of right
kubectl get pods -o name | grep api
history | tail -50
cat file.json | python3 -m json.tool    # Pretty-print JSON
```

---

## Shell Utilities

### Environment Variables

```bash
export GITHUB_TOKEN="ghp_abc123"     # Set a variable for the current session
echo $GITHUB_TOKEN                   # Print its value
printenv GITHUB_TOKEN                # Another way to print it
```

- `export` makes the variable available to child processes
- Variables are lost when the terminal closes

### `clear`

```bash
clear    # Clear the terminal screen
```

### `history`

```bash
history              # Show all command history
history | tail -50   # Show last 50 commands
```

### `base64`

```bash
echo "aGVsbG8=" | base64 -d    # Decode base64 string
echo "hello" | base64           # Encode to base64
```

### `date`

```bash
date                                # Current date and time
date -u +%Y-%m-%dT%H:%M:%SZ        # UTC timestamp in ISO format
```

### `pbpaste` / `pbcopy` (macOS)

```bash
pbpaste                      # Paste clipboard contents to stdout
echo "hello" | pbcopy        # Copy text to clipboard
git commit -m "$(pbpaste)"  # Use clipboard content as commit message
```

### Command Substitution `$(...)`

```bash
echo "Hash: $(git rev-parse --short HEAD)"    # Embed command output in a string
```

- `$(command)` runs the command and substitutes its output inline

---

## File Editing with vim

### Opening Files

```bash
vim file.txt          # Open file in vim (creates it if it doesn't exist)
vim +10 file.txt      # Open and jump to line 10
```

### Modes

| Mode    | How to Enter         | Purpose                    |
|---------|---------------------|----------------------------|
| Normal  | `Esc`               | Navigate, delete, copy     |
| Insert  | `i`, `a`, `o`       | Type text                  |
| Visual  | `v`, `V`, `Ctrl+v`  | Select text                |
| Command | `:`                 | Run commands (save, quit)  |

### Essential Commands (Normal Mode)

| Key          | Action                              |
|-------------|-------------------------------------|
| `i`          | Insert before cursor               |
| `a`          | Insert after cursor                |
| `o`          | Insert new line below              |
| `O`          | Insert new line above              |
| `Esc`        | Return to normal mode              |
| `dd`         | Delete (cut) current line          |
| `yy`         | Copy (yank) current line           |
| `p`          | Paste below cursor                 |
| `u`          | Undo                               |
| `Ctrl+r`     | Redo                               |
| `/pattern`   | Search forward for "pattern"       |
| `n`          | Next search result                 |
| `gg`         | Go to first line                   |
| `G`          | Go to last line                    |
| `:10`        | Jump to line 10                    |

### Saving & Quitting

| Command     | Action                              |
|------------|-------------------------------------|
| `:w`        | Save                               |
| `:q`        | Quit (fails if unsaved changes)    |
| `:wq`       | Save and quit                      |
| `:q!`       | Quit without saving                |
| `:x`        | Save and quit (same as `:wq`)      |

### Search & Replace

```
:%s/old/new/g       # Replace all occurrences in the file
:%s/old/new/gc      # Replace all with confirmation
:10,20s/old/new/g   # Replace only on lines 10-20
```

---

## Creating & Managing Files

### `touch` — Create Empty Files

```bash
touch newfile.txt           # Create an empty file (or update its timestamp)
touch file1.txt file2.txt   # Create multiple files at once
```

- If the file already exists, `touch` updates its modification timestamp without changing contents

### `mkdir` — Create Directories

```bash
mkdir new-folder              # Create a directory
mkdir -p path/to/nested/dir   # Create nested directories (no error if exists)
```

### Common Patterns

```bash
# Create a file and write to it in one step
echo "content" > newfile.txt

# Create a directory structure and a file inside it
mkdir -p project/src && touch project/src/index.js

# Check if a file exists before creating
test -f myfile.txt || touch myfile.txt
```

### `nano` — Simple Terminal Editor (Alternative to vim)

```bash
nano file.txt    # Open file in nano
```

- Simpler than vim — commands shown at the bottom of the screen
- `Ctrl+O` = save, `Ctrl+X` = exit, `Ctrl+W` = search
