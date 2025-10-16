#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[32m'
RESET='\033[0m'
YELLOW='\033[33m'
RED='\033[31m'
ask_yn() {
  # $1=提示语  $2=默认值 y|n
  local prompt="$1"
  local def="${2:-n}"
  local show="[y/N]"
  [ "$def" = "y" ] && show="[Y/n]"

  while :; do
    printf "%s %s " "$prompt" "$show" >/dev/tty
    IFS= read -r ans </dev/tty || return 1
    [ -z "$ans" ] && ans="$def"
    case "$ans" in
    [Yy] | [Yy][Ee][Ss]) return 0 ;;
    [Nn] | [Nn][Oo]) return 1 ;;
    *) echo "Please answer y or n." >/dev/tty ;;
    esac
  done
}

#--- 小工具：取当前 backend.ip ---
get_current_ip() {
  if command -v ip >/dev/null 2>&1; then
    ip -4 route get 1.1.1.1 2>/dev/null |
      awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' |
      grep -E '^[0-9]+(\.[0-9]+){3}$' && return 0
    # 次选：hostname -I
    hostname -I 2>/dev/null |
      awk '{print $1}' |
      grep -E '^[0-9]+(\.[0-9]+){3}$' && return 0
  fi

  # 2) macOS: ipconfig
  if [ "$(uname -s)" = "Darwin" ]; then
    for i in en0 en1 en2; do
      ipconfig getifaddr "$i" 2>/dev/null |
        grep -E '^[0-9]+(\.[0-9]+){3}$' && return 0
    done
  fi

  # 3) 通用回退：ifconfig 解析
  if command -v ifconfig >/dev/null 2>&1; then
    ifconfig 2>/dev/null |
      awk '/inet (addr:)?([0-9]+\.){3}[0-9]+/ {
               ip=$2; sub("addr:","",ip);
               if (ip!="127.0.0.1" && ip !~ /^127\./) {print ip; exit}
             }' |
      grep -E '^[0-9]+(\.[0-9]+){3}$' && return 0
  fi

  # 4) 实在拿不到
  return 1
}

#--- 简单 IPv4 校验（也可接受主机名；如只要 IPv4，保留第一个分支即可） ---
is_valid_host() {
  local s=${1:-}

  # 先判 IPv4 形状
  if [[ $s =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
    IFS=. read -r a b c d <<<"$s" || return 1
    for o in "$a" "$b" "$c" "$d"; do
      [[ $o =~ ^[0-9]{1,3}$ ]] || return 1
      ((o >= 0 && o <= 255)) || return 1
    done
    return 0
  fi

  # 再判主机名（RFC1123 宽松版：标签 1-63，允许中划线但不能以 - 开头/结尾）
  [[ $s =~ ^([A-Za-z0-9]([-A-Za-z0-9]{0,61}[A-Za-z0-9])?\.)*([A-Za-z0-9]([-A-Za-z0-9]{0,61}[A-Za-z0-9])?)$ ]]
}

update_frontend_ip() {
  local IP=$1
  local ROOT_DIR=$2
  if [ "$(uname -s)" = "Darwin" ]; then
    sed -E -i '' "s/(host[[:space:]]*:[[:space:]]*['\"])([^'\"]*)(['\"])/\1$NEW_IP\3/" frontend/api.js
  else
    sed -E -i.bak "s/(host[[:space:]]*:[[:space:]]*['\"])([^'\"]*)(['\"])/\1$NEW_IP\3/" frontend/api.js

  fi
}

need_sudo() {
  if [ "$EUID" -ne 0 ]; then echo "sudo"; else echo ""; fi
}

detect_distro() {
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    echo "${ID:-unknown}|${ID_LIKE:-}"
  else
    echo "unknown|"
  fi
}

install_debian() {
  local package=$1
  local SUDO=$(need_sudo)
  if [ "$package" = "python" ]; then
    $SUDO apt-get update -y
    # python3-venv 是 Debian/Ubuntu 系 venv 必需包
    $SUDO apt-get install -y python3 python3-venv python3-pip build-essential
  elif [[ "$package" = "redis" ]]; then
    $SUDO apt-get install -y redis-server redis-cli
    $SUDO systemctl enable --now redis-server
  fi

}

install_arch() {
  local package=$1
  local SUDO=$(need_sudo)
  # Arch 的 python 包自带 venv 模块
  if [[ "$package" = "python" ]]; then
    $SUDO pacman -Sy --needed --noconfirm python python-pip base-devel
  elif [[ "$package" = "redis" ]]; then
    $SUDO pacman -Sy --needed --noconfirm valkey
    $SUDO systemctl enable --now valkey
  fi
}

install_rhel() {
  local package=$1
  local SUDO=$(need_sudo)
  # 优先 dnf；旧版用 yum。RHEL/CentOS/Fedora 的 python3 自带 venv
  if command -v dnf >/dev/null 2>&1; then
    if [[ "$package" = "python" ]]; then
      $SUDO dnf -y install python3 python3-pip
      # 开发工具组（可选）
    elif [[ "$package" = "redis" ]]; then
      $SUDO dnf -y install redis
    fi
    $SUDO dnf -y groupinstall "Development Tools" || true
  else
    if [[ "$package" = "python" ]]; then
      $SUDO yum -y install python3 python3-pip || true
    elif [[ "$package" = "redis" ]]; then
      $SUDO yum install -y redis
    fi
    $SUDO yum -y groupinstall "Development Tools" || true
  fi
}

install_python_venv() {
  local info
  info=$(detect_distro)
  local id="${info%%|*}"
  local like="${info#*|}"
  echo "Detected: id=$id, like=$like"

  case "$id" in
  arch | manjaro)
    install_arch
    ;;
  ubuntu | debian | linuxmint | pop | elementary | neon | kali | raspbian)
    install_debian
    ;;
  fedora | centos | rhel | rocky | almalinux | ol)
    install_rhel
    ;;
  *)
    # 用 ID_LIKE 兜底
    if echo "$like" | grep -qi "debian"; then
      install_debian "python"
    elif echo "$like" | grep -Eiq "rhel|fedora|centos"; then
      install_rhel "python"
    elif echo "$like" | grep -qi "arch"; then
      install_arch "python"
    else
      echo "Unknown Linux distro: $id. Please install it manualy"
      echo "  Debian/Ubuntu: sudo apt-get install -y python3 python3-venv python3-pip"
      echo "  Arch/Manjaro:  sudo pacman -S python python-pip"
      echo "  RHEL/CentOS:   sudo dnf/yum install -y python3 python3-pip"
      exit 1
    fi
    ;;
  esac

  # 验证 venv 可用
  if python3 - <<'PY'; then
import sys, subprocess, tempfile, os
try:
    d = tempfile.mkdtemp(prefix="venv_test_")
    subprocess.check_call([sys.executable, "-m", "venv", os.path.join(d, "v")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("OK")
except Exception as e:
    print("ERR", e)
    raise
PY
    echo "✅ python3 venv usable"
  else
    echo "❌ venv not usable Please check whether it's installed (Debian/Ubuntu: python3-venv)" >&2
    exit 1
  fi
}

install_redis() {
  local info
  info=$(detect_distro)
  local id="${info%%|*}"
  local like="${info#*|}"
  echo "Detected: id=$id, like=$like"

  case "$id" in
  arch | manjaro)
    install_arch "redis"
    ;;
  ubuntu | debian | linuxmint | pop | elementary | neon | kali | raspbian)
    install_debian "redis"
    ;;
  fedora | centos | rhel | rocky | almalinux | ol)
    install_rhel "redis"
    ;;
  *)
    # 用 ID_LIKE 兜底
    if echo "$like" | grep -qi "debian"; then
      install_debian "redis"
    elif echo "$like" | grep -Eiq "rhel|fedora|centos"; then
      install_rhel "redis"
    elif echo "$like" | grep -qi "arch"; then
      install_arch "redis"
    else
      echo "Unknown Linux distro: $id. Please install it manualy"
      echo "  Debian/Ubuntu: sudo apt-get install -y redis-server redis-cli"
      echo "  Arch/Manjaro:  sudo pacman -S valkey"
      echo "  RHEL/CentOS:   sudo dnf/yum install -y redis"
      exit 1
    fi
    ;;
  esac

}

#if [ -n "$NO_COLOR" ]; then
#  GREEN=''
#  RESET=''
#fi

root=$(git rev-parse --show-toplevel 2>/dev/null) || root=""
if [ -n "$root" ]; then
  echo -e "${GREEN}==>${RESET} ✅Inside a git repo, root: ${root}"
  echo -e "${GREEN}==>${RESET} Checking for update..."
  git pull origin master
else
  echo -e "${YELLOW}==>${RESET} Repo enviroment not found"
  if ask_yn "Do you wish to clone it from github?" y; then
    echo "${GREEN}==>${RESET} Cloning from remote..."
    git clone https://github.com/ClovertaTheTrilobita/cellpose-web.git

    if ! cd cellpose-web; then
      echo -e "${RED}==>${RESET} directory 'cellpose-web' not found or inaccessible, did git clone run successfully?" >&2
      exit 1
    fi
  fi
fi

root=$(pwd)
echo -e "${GREEN}==>${RESET} STARTING DEPLOY..."

if command -v valkey-server >/dev/null 2>&1 || command -v redis-cli >/dev/null 2>&1 || command -v redis-server >/dev/null 2>&1; then
  # 打印版本（有哪个用哪个）
  ver="$(redis-cli --version 2>/dev/null || redis-server --version 2>/dev/null)"
  echo -e "${GREEN}==>${RESET} Redis installed: $ver"
else
  echo -e "${YELLOW}==>${RESET} Redis not detected."
  if ask_yn "Do you like to install redis on your machine?" y; then
    install_redis
  fi
fi

FILE="${root}/backend/config.yaml"
DEFAULT_IP="$(get_current_ip || true)"
echo -e "${GREEN}==>${RESET} Enter IP address of your machine (empty: default ${DEFAULT_IP}):"
prompt=${prompt:-"Enter server IP/host"} # 先初始化 prompt
curr_ip=${curr_ip:-}
[ -n "${curr_ip:-}" ] && prompt="$prompt (current: $curr_ip)"
printf "%s: " "$prompt" >/dev/tty
IFS= read -r NEW_IP </dev/tty

# 默认回车使用探测到的 IP
if [ -z "${NEW_IP}" ]; then
  if [ -n "${DEFAULT_IP:-}" ]; then
    NEW_IP="$DEFAULT_IP"
    echo -e "${GREEN}==>${RESET} Using detected IP: $NEW_IP"
  else
    echo -e "${RED}==>${RESET} No input and no IP detected. Aborted." >&2
    exit 1
  fi
fi

if ! is_valid_host "$NEW_IP"; then
  echo -e "${RED}==>${RESET} Invalid IP/hostname: $NEW_IP" >&2
  if ask_yn "Do you wish to use default ip (${DEFAULT_IP})?" y; then
    echo -e "${GREEN}==>${RESET} Using detected IP: $NEW_IP"
  else
    exit 1
  fi
fi

#cp -a -- "$FILE" "$FILE.bak.$(date +%Y%m%d%H%M%S)"

if command -v yq >/dev/null 2>&1; then
  NEW_IP_ENV="$NEW_IP" yq -i '.backend.ip = strenv(NEW_IP_ENV)' "$FILE"
else
  awk -v newip="$NEW_IP" '
    BEGIN { inblk=0; base=-1; done=0 }
    /^[[:space:]]*backend:[[:space:]]*$/ { inblk=1; base=indent($0); print; next }
    {
      if (inblk && !done) {
        ind = indent($0)
        if (ind <= base) { inblk=0 }
        else if ($0 ~ /^[[:space:]]*ip:[[:space:]]*/) {
          match($0, /^[[:space:]]*/); sp = substr($0, 1, RLENGTH)
          print sp "ip: " newip
          done=1; next
        }
      }
      print
    }
    function indent(s,    n) {
      match(s, /^[[:space:]]*/)
      return RLENGTH
    }
  ' "$FILE" >"$FILE.tmp" && mv "$FILE.tmp" "$FILE"
fi

echo -e "${GREEN}==>${RESET} Updated backend.ip -> $NEW_IP in $FILE"

update_frontend_ip $NEW_IP $root

echo -e "${GREEN}==>${RESET} Update host -> $NEW_IP in frontend/api.js"

if command -v conda >/dev/null 2>&1; then
  echo "Conda already installed: $(conda --version)"
  CONDA_EXE="${CONDA_EXE:-$(command -v conda)}"
  CONDA_BASE="$("$CONDA_EXE" info --base)"
  eval "$("$CONDA_EXE" shell.bash hook)"
  conda create -n cpweb python=3.12
  conda activate cpweb
else
  echo -e "${YELLOW}==>${RESET} Conda enviroment NOT FOUND"
  echo "We highly recommend you to use Conda to manage python enviroments"
  if ask_yn "Do you wish to install miniconda?" y; then
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
    bash miniconda.sh -b -p $HOME/miniconda3
    rm miniconda.sh
    eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
    conda init
    conda create -n cpweb python=3.12 || true
    conda activate cpweb
  else
    echo -e "${GREEN}==>${RESET} Creating Python venv..."
    if [ "$(uname -s)" = "Darwin" ]; then
      if ! command -v brew >/dev/null 2>&1; then
        echo -e "${RED}==>${RESET} You are using macOS/BSD with no homebrew, we don't recommend you to use system python on macOS, aborting..."
        exit 1
      fi
      if ! brew install python >/dev/null 2>&1; then
        echo -e "${RED}==>${RESET} Failed to install Python via Homebrew.\n"
        exit 1
      fi
    else
      install_python_venv "$@"
      python3 -m venv .venv
      . .venv/bin/activate
      python -V
      echo -e "${GREEN}==>${RESET} Successfully created venv"
    fi
  fi
fi

if ! cd "${root}/backend"; then
  echo -e "${RED}==>${RESET} dir backend/ missing, did you edit project structre?"
  exit 1
fi

echo -e "${GREEN}==>${RESET} Preparing to install dependencies..."
if ask_yn "Do you want to install it now?" y; then
  if ! cd "${root}"; then
    echo -e "${RED}==>${RESET} unable to access ${root}, did you edit project structre?"
    exit 1
  fi

  python -m pip install -r requirements.txt
else
  echo -e "${YELLOW}==>${RESET} Operation canceled, exiting..."
  exit 1
fi

echo -e "${GREEN}==>${RESET} Deployment successfull"
if ask_yn "Do you wish to start cellpose server now?" y; then
  python ${root}/backend/main.py
fi
