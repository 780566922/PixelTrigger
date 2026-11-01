#!/bin/bash
# ============================================================================
# 生成并导入「本机自签名代码签名证书」，让 macOS 的屏幕录制 / 辅助功能授权
# 能够跨版本继承。
#
# 为什么需要它：
#   ad-hoc 签名（codesign -s -）的 designated requirement 是 `cdhash H"..."`，
#   与二进制内容绑定。每次重新构建 CDHash 都变，TCC 便认为"这是另一个应用"，
#   于是出现「覆盖安装后权限条目还在、开关也开着，但就是不生效，必须去系统
#   设置里删掉条目再重新授权」的循环。
#   用固定证书签名后，DR 变成
#     identifier "com.pixeltrigger.app" and certificate root = H"<证书>"
#   与内容无关，覆盖安装后 TCC 认得出"还是它"，授权自然继承。
#
# 证书只在本机使用：10 年有效期，私钥存在登录钥匙串里，不联网、不牵涉
# 任何 Apple 账号。换机器时重新跑一次本脚本会生成新证书 —— 新证书意味着
# 新的身份，届时需要再授权一次（之后又会稳定下来）。
#
# 用法：./setup_signing_cert.sh
# 幂等：已经装好就直接报告，不做任何改动。
# ============================================================================
set -u

SIGN_ID="${PIXELTRIGGER_SIGN_ID:-PixelTrigger Local Signing}"
CERT_DIR="${PIXELTRIGGER_SIGN_DIR:-${HOME}/.pixeltrigger-signing}"
KEYCHAIN="${HOME}/Library/Keychains/login.keychain-db"
P12_PASS="ptlocal"          # 仅用于导入本机临时 p12，非机密

say() { printf '%s\n' "$*"; }

# ---------------------------------------------------------------- 0. 判据函数
# 注意：不能用 `security find-certificate -c <名>` 判断"已导入"——它在找不到
# 证书时**同样返回 0**（只是没有输出），会误判成"已存在"从而跳过 import，
# 结果只导入了信任设置、没导入私钥，find-identity 里永远没有这个身份。
have_identity() {   # 证书 + 私钥都进了钥匙串（未必要被信任）
    security find-identity -p codesigning 2>/dev/null | grep -qF "${SIGN_ID}"
}
is_trusted() {      # 既齐全又被信任 —— build_app.sh 认的就是这个
    security find-identity -v -p codesigning 2>/dev/null | grep -qF "${SIGN_ID}"
}

# ---------------------------------------------------------------- 1. 已就绪？
if is_trusted; then
    say "✅ 已存在可用的代码签名身份：「${SIGN_ID}」"
    security find-identity -v -p codesigning 2>/dev/null | grep -F "${SIGN_ID}"
    say ""
    say "直接构建即可：./build_app.sh --dmg"
    exit 0
fi

mkdir -p "${CERT_DIR}" && chmod 700 "${CERT_DIR}"
cd "${CERT_DIR}" || exit 1

# ---------------------------------------------------------------- 2. 私钥/证书
if [[ ! -f pixeltrigger.key || ! -f pixeltrigger.crt || ! -f pixeltrigger.p12 ]]; then
    say "==> 生成本机自签名代码签名证书（10 年有效）"
    rm -f pixeltrigger.key pixeltrigger.crt pixeltrigger.p12
    openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
        -keyout pixeltrigger.key -out pixeltrigger.crt \
        -subj "/CN=${SIGN_ID}/O=PixelTrigger Local/C=CN" \
        -addext "basicConstraints=critical,CA:false" \
        -addext "keyUsage=critical,digitalSignature" \
        -addext "extendedKeyUsage=critical,codeSigning" >/dev/null 2>&1 || {
            say "❌ openssl 生成证书失败"; exit 1; }
    openssl pkcs12 -export -inkey pixeltrigger.key -in pixeltrigger.crt \
        -out pixeltrigger.p12 -name "${SIGN_ID}" -passout "pass:${P12_PASS}" \
        >/dev/null 2>&1 || { say "❌ 打包 p12 失败"; exit 1; }
    chmod 600 pixeltrigger.key pixeltrigger.p12
    say "    证书指纹：$(openssl x509 -in pixeltrigger.crt -noout -fingerprint -sha1 \
        | sed 's/^.*=//')"
fi

# ---------------------------------------------------------------- 3. 导入钥匙串
if ! have_identity; then
    say "==> 导入到登录钥匙串（证书 + 私钥，私钥 ACL 只放行 codesign）"
    IMP_OUT="$(security import pixeltrigger.p12 -k "${KEYCHAIN}" -P "${P12_PASS}" \
        -T /usr/bin/codesign -T /usr/bin/security 2>&1)"
    [[ -n "${IMP_OUT}" ]] && say "    ${IMP_OUT}"
    # securityd 对新建身份有缓存，给它两秒
    for _ in 1 2 3; do have_identity && break; sleep 1; done
    if ! have_identity; then
        say "❌ 导入后钥匙串里仍没有「${SIGN_ID}」的代码签名身份。"
        say "   常见原因：登录钥匙串处于锁定状态。"
        say "   请打开「钥匙串访问」→ 左侧选「登录」→ 右键「解锁钥匙串」，再重跑本脚本。"
        exit 1
    fi
fi

# ---------------------------------------------------------------- 4. 设为可信
# 自签名证书必须被标记为代码签名信任，否则 codesign 不把它当有效身份，
# Security 框架评估签名时也会因"无法建立信任链"而失败（权限照样不生效）。
if ! is_trusted; then
    say "==> 把证书标记为「代码签名」信任"
    TRUST_OUT="$(security add-trusted-cert -r trustRoot -p codeSign -k "${KEYCHAIN}" \
        pixeltrigger.crt 2>&1)"
    [[ -n "${TRUST_OUT}" ]] && say "    ${TRUST_OUT}"
    for _ in 1 2 3; do is_trusted && break; sleep 1; done
fi

# ---------------------------------------------------------------- 5. 复核
if is_trusted; then
    say "✅ 完成。签名身份已就绪："
    security find-identity -v -p codesigning 2>/dev/null | grep -F "${SIGN_ID}"
    say ""
    say "证书与私钥目录：${CERT_DIR}"
    say "  （换机器时把整个目录拷过去重跑本脚本，签名身份就能保持一致，"
    say "    也就不会再次触发「更新后要重新授权」）"
    say "接下来：./build_app.sh --dmg"
else
    say "❌ 证书已在钥匙串里，但还不是「受信任的代码签名身份」，请手动收尾："
    say "   打开「钥匙串访问」→ 找到「${SIGN_ID}」→ 双击 → 展开「信任」→"
    say "   把「代码签名」设为「始终信任」→ 关闭窗口（会要求输入登录密码）。"
    exit 1
fi
