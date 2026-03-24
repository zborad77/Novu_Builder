// Dynamická konfigurace — přečte URL z prostředí, pokud je nastavena.
//
// Produkce:
//   EXPO_PUBLIC_API_URL=https://api.zborad.cz/api/v1 npx expo start
//
// Dev (lokální IP):
//   npx expo start   (použije hodnotu z app.json → extra.apiUrl)
//
// app.json je stále zdrojem pravdy pro veškerou ostatní konfiguraci.

const base = require('./app.json');

module.exports = {
  ...base,
  expo: {
    ...base.expo,
    extra: {
      ...base.expo.extra,
      apiUrl: process.env.EXPO_PUBLIC_API_URL ?? base.expo.extra.apiUrl,
    },
  },
};
