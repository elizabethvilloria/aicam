#!/bin/bash
# DuckDNS IP update script for etrikegerweiss.duckdns.org

DOMAIN="etrikegerweiss"
TOKEN="YOUR-DUCKDNS-TOKEN"  # Get this from duckdns.org after signup

# Update DuckDNS with current IP
curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip="

echo "DNS updated for ${DOMAIN}.duckdns.org"
