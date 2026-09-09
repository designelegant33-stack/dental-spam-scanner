#!/bin/bash
run_one() {
  local idx="${1%%:*}"; local dom="${1#*:}"
  firecrawl search "site:$dom" --limit 50 -o ".firecrawl/spam-check/idx${idx}.json" --json >/dev/null 2>&1
  echo "done idx$idx $dom -> $(jq '.data.web | length' ".firecrawl/spam-check/idx${idx}.json" 2>/dev/null) results"
}
export -f run_one
DOMAINS=(
  "26:ladentalboutique.com" "27:dentist93036.com" "28:brooklyndentist.com"
  "29:dentalofficeinbrooklyn.com" "30:dentistinbrooklynheights.com" "31:jasonacurtisdmd.com"
  "32:newportdentalgroup.org" "33:westwindintegratedhealth.com" "34:allon4teeth.com"
  "35:implantdentistinbrooklyn.com" "36:emergencydentistbrooklyn.com" "37:lancastertotaldentistry.com"
  "38:palmdaletotaldentistry.com" "39:ovaldental.com"
)
printf '%s\n' "${DOMAINS[@]}" | xargs -P 2 -I {} bash -c 'run_one "$@"' _ {}
