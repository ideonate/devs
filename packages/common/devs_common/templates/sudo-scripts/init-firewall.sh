#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, and pipeline failures
IFS=$'\n\t'       # Stricter word splitting

# Enable debug output if DEVS_DEBUG is set
if [ "${DEVS_DEBUG:-}" = "true" ]; then
    echo "🐛 [DEBUG] init-firewall.sh: Debug mode enabled"
    set -x  # Enable command tracing
fi

# Flush existing rules and delete existing ipsets
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
ipset destroy allowed-domains 2>/dev/null || true

# First allow DNS and localhost before any restrictions
# Allow outbound DNS
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
# Allow inbound DNS responses
iptables -A INPUT -p udp --sport 53 -j ACCEPT
# Allow outbound SSH
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT
# Allow inbound SSH responses
iptables -A INPUT -p tcp --sport 22 -m state --state ESTABLISHED -j ACCEPT
# Allow localhost
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Create ipset with CIDR support
ipset create allowed-domains hash:net

# Fetch GitHub meta information and aggregate + add their IP ranges
echo "Fetching GitHub IP ranges..."
echo "GH_TOKEN available: ${GH_TOKEN:+YES}"

if [ -n "${GH_TOKEN:-}" ]; then
    echo "Using authenticated GitHub API request"
    gh_ranges=$(curl -s -H "Authorization: token $GH_TOKEN" https://api.github.com/meta)
else
    echo "Using unauthenticated GitHub API request"
    gh_ranges=$(curl -s https://api.github.com/meta)
fi
if [ -z "$gh_ranges" ]; then
    echo "ERROR: Failed to fetch GitHub IP ranges"
    exit 1
fi

if ! echo "$gh_ranges" | jq -e '.web and .api and .git' >/dev/null; then
    echo "ERROR: GitHub API response missing required fields"
    exit 1
fi

echo "Processing GitHub IPs..."
while read -r cidr; do
    if [[ ! "$cidr" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[0-9]{1,2}$ ]]; then
        echo "ERROR: Invalid CIDR range from GitHub meta: $cidr"
        exit 1
    fi
    echo "Adding GitHub range $cidr"
    ipset add allowed-domains "$cidr"
done < <(echo "$gh_ranges" | jq -r '(.web + .api + .git)[]' | aggregate -q)

# Function to resolve domain names following CNAME chains
resolve_domain_ips() {
    local domain="$1"
    local max_redirects=10
    local redirect_count=0
    local current_domain="$domain"
    local final_ips=""
    
    while [ $redirect_count -lt $max_redirects ]; do
        # Get all DNS records for the current domain
        local dns_result=$(dig +short "$current_domain")
        
        if [ -z "$dns_result" ]; then
            echo "ERROR: No DNS records found for $current_domain"
            return 1
        fi
        
        # Extract IP addresses (A records)
        local ips=$(echo "$dns_result" | grep -E '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')
        
        if [ -n "$ips" ]; then
            # Found IP addresses, we're done
            final_ips="$ips"
            break
        fi
        
        # Look for CNAME or ALIAS records (non-IP results)
        local cname=$(echo "$dns_result" | grep -v -E '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$' | head -1)
        
        if [ -n "$cname" ]; then
            echo "Following CNAME/ALIAS: $current_domain -> $cname"
            current_domain="$cname"
            redirect_count=$((redirect_count + 1))
        else
            echo "ERROR: Unable to resolve $domain (no IPs or CNAMEs found)"
            return 1
        fi
    done
    
    if [ $redirect_count -eq $max_redirects ]; then
        echo "ERROR: Too many redirects for $domain (max: $max_redirects)"
        return 1
    fi
    
    if [ -z "$final_ips" ]; then
        echo "ERROR: Failed to resolve $domain to IP addresses"
        return 1
    fi
    
    echo "$final_ips"
}

# Collect all unique IPs from domains first
declare -A unique_ips
for domain in \
    "registry.npmjs.org" \
    "pypi.org" \
    "files.pythonhosted.org" \
    "pypi.python.org" \
    "api.anthropic.com" \
    "sentry.io" \
    "statsig.anthropic.com" \
    "statsig.com"; do
    echo "Resolving $domain..."
    ips=$(resolve_domain_ips "$domain")
    if [ $? -ne 0 ]; then
        exit 1
    fi
    
    while read -r ip; do
        if [[ ! "$ip" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
            echo "ERROR: Invalid IP from DNS for $domain: $ip"
            exit 1
        fi
        if [ -z "${unique_ips[$ip]:-}" ]; then
            unique_ips[$ip]="$domain"
            echo "Collected $ip for $domain"
        else
            echo "IP $ip already collected for ${unique_ips[$ip]}, also used by $domain"
        fi
    done < <(echo "$ips")
done

# Now add all unique IPs to ipset
echo "Adding collected IPs to ipset..."
for ip in "${!unique_ips[@]}"; do
    echo "Adding $ip (from ${unique_ips[$ip]})"
    ipset add allowed-domains "$ip"
done

# Get host IP from default route
HOST_IP=$(ip route | grep default | cut -d" " -f3)
if [ -z "$HOST_IP" ]; then
    echo "ERROR: Failed to detect host IP"
    exit 1
fi

HOST_NETWORK=$(echo "$HOST_IP" | sed "s/\.[0-9]*$/.0\/24/")
echo "Host network detected as: $HOST_NETWORK"

# Set up remaining iptables rules
iptables -A INPUT -s "$HOST_NETWORK" -j ACCEPT
iptables -A OUTPUT -d "$HOST_NETWORK" -j ACCEPT

# Set default policies to DROP first
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# First allow established connections for already approved traffic
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Then allow only specific outbound traffic to allowed domains
iptables -A OUTPUT -m set --match-set allowed-domains dst -j ACCEPT

echo "Firewall configuration complete"
echo "Verifying firewall rules..."
if curl --connect-timeout 5 https://example.com >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - was able to reach https://example.com"
    exit 1
else
    echo "Firewall verification passed - unable to reach https://example.com as expected"
fi

# Verify GitHub API access
if ! curl --connect-timeout 5 https://api.github.com/zen >/dev/null 2>&1; then
    echo "ERROR: Firewall verification failed - unable to reach https://api.github.com"
    exit 1
else
    echo "Firewall verification passed - able to reach https://api.github.com as expected"
fi
