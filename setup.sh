#!/usr/bin/env bash
#
# iPad tracker - ek command me poora setup
#
#   chmod +x setup.sh && ./setup.sh
#
# Token kabhi screen pe nahi dikhega, kabhi kisi file me nahi jayega,
# aur kabhi shell history me nahi aayega.

set -euo pipefail

BOLD=$'\e[1m'; DIM=$'\e[2m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; OFF=$'\e[0m'
ok(){ echo "${GREEN}✓${OFF} $1"; }
info(){ echo "${DIM}·${OFF} $1"; }
warn(){ echo "${YELLOW}!${OFF} $1"; }
die(){ echo "${RED}✗ $1${OFF}" >&2; exit 1; }
step(){ echo; echo "${BOLD}$1${OFF}"; }

echo "${BOLD}iPad 11 price tracker - setup${OFF}"
echo "${DIM}Token screen pe nahi dikhega aur kisi file me save nahi hoga.${OFF}"

# ---------------------------------------------------------------- checks
step "1/7  Zaroori cheezein check kar rahe hain"

command -v git >/dev/null || die "git nahi mila. Install karo phir dobara chalao."
command -v python3 >/dev/null || die "python3 nahi mila."
command -v gh >/dev/null || die "GitHub CLI nahi mili. https://cli.github.com se install karo."
ok "git, python3, gh - teeno maujood"

gh auth status >/dev/null 2>&1 || die "GitHub me login nahi ho. Pehle chalao:  gh auth login"
GH_USER=$(gh api user --jq .login)
ok "GitHub login: $GH_USER"

for f in tracker.py index.html requirements.txt price_history.json .github/workflows/track.yml; do
  [ -f "$f" ] || die "$f missing hai. Zip poori extract hui thi?"
done
ok "saari project files maujood"

# ---------------------------------------------------------------- creds
step "2/7  Telegram credentials"
echo "${DIM}Type karte waqt kuch dikhega nahi - ye normal hai.${OFF}"
echo

printf "Bot token (BotFather se): "
read -rs BOT_TOKEN; echo
[ -n "$BOT_TOKEN" ] || die "token khali hai"

info "token verify kar rahe hain..."
BOT_INFO=$(curl -s --max-time 15 "https://api.telegram.org/bot${BOT_TOKEN}/getMe" || true)
echo "$BOT_INFO" | grep -q '"ok":true' \
  || die "Telegram ne token reject kiya. Revoke ke baad wala naya token use karo."
BOT_NAME=$(echo "$BOT_INFO" | sed -n 's/.*"username":"\([^"]*\)".*/\1/p')
ok "bot mil gaya: @${BOT_NAME}"

echo
echo "Ab @${BOT_NAME} ko Telegram pe kholo aur ${BOLD}/start${OFF} bhejo."
read -rp "Bhej diya? [Enter dabao] " _

info "chat ID dhoondh rahe hain..."
UPDATES=$(curl -s --max-time 15 "https://api.telegram.org/bot${BOT_TOKEN}/getUpdates" || true)
CHAT_ID=$(echo "$UPDATES" | sed -n 's/.*"chat":{"id":\(-\?[0-9]*\).*/\1/p' | head -1)

if [ -z "$CHAT_ID" ]; then
  warn "apne aap nahi mila - bot ko koi bhi message bhejo aur ye number khud daal do"
  printf "Chat ID: "; read -r CHAT_ID
  [ -n "$CHAT_ID" ] || die "chat ID chahiye hi chahiye"
else
  ok "chat ID mil gaya: $CHAT_ID"
fi

info "test message bhej rahe hain..."
SENT=$(curl -s --max-time 15 -X POST \
  "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "text=Setup chal raha hai. Ye message dikha matlab sab sahi hai." || true)
echo "$SENT" | grep -q '"ok":true' \
  || die "Message nahi gaya. @${BOT_NAME} ko /start bheja tha?"
ok "Telegram pe message pahunch gaya - phone check karo"

# ---------------------------------------------------------------- local test
step "3/7  Local test"
python3 -m pip install -q -r requirements.txt 2>/dev/null || pip3 install -q -r requirements.txt
python3 tracker.py --dry-run || die "tracker.py crash ho gaya"
ok "script chal gayi (kuch stores 403 dein to normal hai)"

# ---------------------------------------------------------------- git
step "4/7  Git repo taiyaar kar rahe hain"
printf "Repo ka naam [ipad-tracker]: "; read -r REPO_NAME
REPO_NAME=${REPO_NAME:-ipad-tracker}

[ -f .gitignore ] || die ".gitignore missing hai - secrets leak ho sakte the"
grep -q "^\.env\.local$" .gitignore || die ".gitignore me .env.local nahi hai"

[ -d .git ] || git init -q
git add -A

# Aakhri safety check: kahin galti se koi secret to stage nahi hua
if git diff --staged --name-only | grep -qE '^\.env(\.local)?$|^state\.json$'; then
  die "Ek secret file stage ho gayi thi. Ruk gaye. .gitignore check karo."
fi
if git diff --staged | grep -qE '[0-9]{8,10}:[A-Za-z0-9_-]{30,}'; then
  die "Kisi file me bot token jaisa text mila. Ruk gaye - use hatao pehle."
fi
ok "koi secret commit me nahi ja raha"

git diff --staged --quiet || git commit -qm "iPad price tracker"
ok "commit ho gaya"

# ---------------------------------------------------------------- push
step "5/7  GitHub pe bhej rahe hain"
if gh repo view "$GH_USER/$REPO_NAME" >/dev/null 2>&1; then
  info "repo pehle se hai, usi me push kar rahe hain"
  git remote get-url origin >/dev/null 2>&1 || \
    git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
  git branch -M main
  git push -qu origin main
else
  gh repo create "$REPO_NAME" --public --source=. --remote=origin --push -d "iPad 11 price tracker"
fi
ok "push ho gaya"

gh api "repos/$GH_USER/$REPO_NAME/contents/.github/workflows/track.yml" >/dev/null 2>&1 \
  || die "workflow file GitHub pe nahi pahunchi. .github folder push nahi hua."
ok "workflow file GitHub pe maujood hai"

# ---------------------------------------------------------------- secrets
step "6/7  Secrets set kar rahe hain"
printf '%s' "$BOT_TOKEN" | gh secret set TELEGRAM_BOT_TOKEN --repo "$GH_USER/$REPO_NAME"
printf '%s' "$CHAT_ID"   | gh secret set TELEGRAM_CHAT_ID   --repo "$GH_USER/$REPO_NAME"
unset BOT_TOKEN
ok "TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID set ho gaye"
info "ab token is machine ki memory me bhi nahi hai"

# ---------------------------------------------------------------- pages + run
step "7/7  Dashboard live kar rahe hain"
gh api -X POST "repos/$GH_USER/$REPO_NAME/pages" \
  -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1 \
  && ok "GitHub Pages on ho gaya" \
  || warn "Pages apne aap on nahi hua - Settings > Pages > main / root se on kar lena"

gh workflow run "Track iPad price" --repo "$GH_USER/$REPO_NAME" >/dev/null 2>&1 \
  && ok "pehla run chalu kar diya" \
  || warn "workflow manually chala lena: Actions tab > Run workflow"

# ---------------------------------------------------------------- done
cat <<EOF

${BOLD}${GREEN}Ho gaya.${OFF}

  Repo       https://github.com/$GH_USER/$REPO_NAME
  Dashboard  https://$GH_USER.github.io/$REPO_NAME/   ${DIM}(1-2 min lagenge)${OFF}
  Actions    https://github.com/$GH_USER/$REPO_NAME/actions

  Har 4 ghante price check hoga. Telegram ping tab aayega jab:
    price ₹40,000 ya neeche jaye · 3%+ girawat ho · naya all-time low bane

  ${BOLD}Ab bhi karna hai:${OFF} Amazon aur Flipkart bots ko block karte hain, wo bot se
  cover nahi honge. Dashboard ke "Backup trackers" section se Pricehistory aur
  BuyHatke pe bhi ₹40,000 ka alert laga do.

EOF
