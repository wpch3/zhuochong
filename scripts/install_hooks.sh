#!/usr/bin/env bash
# 把提交前保险装成 git 钩子（只对本仓库生效，可随时删 .git/hooks/pre-commit）
set -e
cd "$(dirname "$0")/.."
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
exec bash scripts/precommit.sh
HOOK
chmod +x .git/hooks/pre-commit
echo "已装 .git/hooks/pre-commit（跳过一次：git commit --no-verify）"
