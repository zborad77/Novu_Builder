// Dynamic mobile config.
// API URL must be explicit - there is no implicit localhost fallback.
//
// Production / staging:
//   EXPO_PUBLIC_API_URL=https://api.example.com/api/v1 npx expo start
//
// Local network dev:
//   EXPO_PUBLIC_API_URL=http://192.168.x.y:8000/api/v1 npx expo start

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
