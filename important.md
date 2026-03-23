
# FOR ACCESS TOKEN GENERATION
curl -X POST https://api.sinric.pro/api/v1/auth \
  -H "Authorization: Basic $(echo -n 'abilbiju2004@gmail.com:Paul@@7295' | base64)" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=android-app"

