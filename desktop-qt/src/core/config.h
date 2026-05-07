#pragma once

namespace Config {

constexpr const char *AppName        = "NOVU Builder";
constexpr const char *OrgName        = "NOVU";
constexpr const char *AppVersion     = "0.1.0";
constexpr const char *BrandLabel     = "NOVU";

// QSettings keys — org + app must match across the entire codebase
constexpr const char *SettingsOrg    = "NOVU";
constexpr const char *SettingsApp    = "NovuBuilder";

// QSettings key paths
constexpr const char *KeyServerUrl          = "server/url";
constexpr const char *KeySessionAccessToken = "session/accessToken";
constexpr const char *KeySessionRefreshToken= "session/refreshToken";

} // namespace Config
